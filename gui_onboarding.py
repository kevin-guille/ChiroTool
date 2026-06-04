"""
gui_onboarding.py — wizard d'accueil affiché au premier lancement.

3 étapes pour configurer ChiroTool en moins de 2 minutes :

    1. Token Vigie-Chiro (copie-colle depuis DevTools)
    2. Dossier de travail (workspace racine)
    3. Parc matériel (optionnel : peut être rempli plus tard via Préférences)

À l'issue du wizard, ``Settings.onboarding_done = True`` et l'utilisateur
n'est plus ré-interrogé. Accessible aussi à la demande depuis Préférences
si on voulait le re-déclencher (pas exposé en v1 — keep it simple).

Design :
- CTkToplevel modal, taille ~720×560
- Une étape à la fois, boutons « Précédent / Suivant / Ignorer »
- Tolérant : chaque étape est skippable, rien n'est obligatoire (l'app reste
  utilisable même avec un onboarding 100% zappé)
- Persiste à chaque validation (token via keyring, workspace via settings,
  matériels via materiels.json)
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from credentials import save_token, storage_backend
from gui_config import Settings, save_settings
from materiels import Materiel, load_materiels, save_materiels


PORTAIL_URL = "https://vigiechiro.herokuapp.com/"
JS_COMMAND = "localStorage.getItem('auth-session-token')"


class OnboardingWizard(ctk.CTkToplevel):
    """Wizard 3 étapes au premier lancement."""

    def __init__(self, master, settings: Settings,
                  on_done=None):
        super().__init__(master)
        self.settings = settings
        self.on_done = on_done   # callback à la fermeture (avec settings updated)
        self.title("Bienvenue sur ChiroTool")
        self.geometry("720x560")
        self.resizable(False, False)
        self.transient(master)
        self.after(50, self.grab_set)

        # État wizard
        self.current_step = 0
        self.token_validated = False
        self._workspace_path: str | None = None

        self._build_ui()
        self._render_step(0)

        # Fermeture croix = skip complet (mais on persiste quand même
        # onboarding_done pour ne pas réouvrir au prochain lancement)
        self.protocol("WM_DELETE_WINDOW", self._on_skip_all)

    # -- UI ----------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header : titre + indicateur d'étape
        header = ctk.CTkFrame(self, fg_color=("gray92", "gray20"), corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        self.header_title = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        )
        self.header_title.grid(row=0, column=0, sticky="w", padx=20, pady=(16, 2))

        self.header_sub = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray70"),
            anchor="w",
        )
        self.header_sub.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 16))

        # Contenu central : 1 CTkFrame réutilisé, vidé entre chaque étape
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=20, pady=16)
        self.body.grid_columnconfigure(0, weight=1)

        # Footer : boutons navigation
        footer = ctk.CTkFrame(self, fg_color=("gray92", "gray18"), corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_columnconfigure(1, weight=1)

        self.prev_btn = ctk.CTkButton(
            footer, text="◂ Précédent", width=110, height=34,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_prev,
        )
        self.prev_btn.grid(row=0, column=0, sticky="w", padx=16, pady=14)

        self.skip_btn = ctk.CTkButton(
            footer, text="Ignorer cette étape", width=160, height=34,
            fg_color="transparent",
            text_color=("gray40", "gray60"),
            hover_color=("gray85", "gray25"),
            command=self._on_skip_step,
        )
        self.skip_btn.grid(row=0, column=1, sticky="", padx=8, pady=14)

        self.next_btn = ctk.CTkButton(
            footer, text="Suivant ▸", width=140, height=34,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_next,
        )
        self.next_btn.grid(row=0, column=2, sticky="e", padx=16, pady=14)

    def _clear_body(self):
        for w in self.body.winfo_children():
            w.destroy()

    # -- Navigation --------------------------------------------------------

    def _render_step(self, step: int):
        self.current_step = step
        self._clear_body()
        if step == 0:
            self._render_step_token()
        elif step == 1:
            self._render_step_workspace()
        elif step == 2:
            self._render_step_materiels()
        else:
            self._finish()
            return
        # Boutons prev/next selon l'étape
        self.prev_btn.configure(state="disabled" if step == 0 else "normal")
        if step == 2:
            self.next_btn.configure(text="Terminer ✓")
        else:
            self.next_btn.configure(text="Suivant ▸")

    def _on_prev(self):
        if self.current_step > 0:
            self._render_step(self.current_step - 1)

    def _on_next(self):
        # Pour chaque étape, on peut valider si nécessaire avant de passer
        if self.current_step == 0:
            self._save_token_step()
        elif self.current_step == 1:
            self._save_workspace_step()
        elif self.current_step == 2:
            self._save_materiels_step()
        self._render_step(self.current_step + 1)

    def _on_skip_step(self):
        """Ignore l'étape courante sans sauvegarder (mais avance)."""
        self._render_step(self.current_step + 1)

    def _on_skip_all(self):
        """Croix rouge → on marque onboarding fait pour ne plus l'afficher."""
        self._finish()

    def _finish(self):
        self.settings.onboarding_done = True
        try:
            save_settings(self.settings)
        except Exception:
            pass
        if self.on_done:
            try:
                self.on_done(self.settings)
            except Exception:
                pass
        self.destroy()

    # =========================================================================
    # ÉTAPE 1 : Token Vigie-Chiro
    # =========================================================================

    def _render_step_token(self):
        self.header_title.configure(text="🔑  Étape 1/3 — Token Vigie-Chiro")
        self.header_sub.configure(
            text="Permet à l'app de créer des participations et uploader tes enregistrements.")

        intro = ctk.CTkLabel(
            self.body,
            text=(
                "Récupère ton token personnel depuis le portail Vigie-Chiro :\n\n"
                "   1. Clique sur « Ouvrir le portail » et connecte-toi\n"
                "   2. Ouvre les DevTools du navigateur (F12) → onglet Console\n"
                "   3. Colle la commande JS ci-dessous et appuie sur Entrée\n"
                "   4. Copie la valeur affichée (32 caractères) et colle-la ici"
            ),
            font=ctk.CTkFont(size=12),
            justify="left", anchor="w",
            wraplength=640,
        )
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        # Bouton portail + commande JS
        row1 = ctk.CTkFrame(self.body, fg_color="transparent")
        row1.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        row1.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            row1, text="🌐 Ouvrir le portail", height=30, width=160,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=lambda: webbrowser.open(PORTAIL_URL),
        ).grid(row=0, column=0, padx=(0, 8))

        js_entry = ctk.CTkEntry(
            row1, font=ctk.CTkFont(family="Consolas", size=11),
        )
        js_entry.insert(0, JS_COMMAND)
        js_entry.configure(state="readonly")
        js_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        def _copy_js():
            try:
                self.clipboard_clear()
                self.clipboard_append(JS_COMMAND)
                self.update()
                self.token_status_lbl.configure(
                    text="✓ commande copiée — colle-la dans la Console DevTools (F12)",
                    text_color=("#2ea043", "#3fb950"),
                )
            except Exception:
                pass

        ctk.CTkButton(
            row1, text="📋 Copier", width=90, height=30,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=_copy_js,
        ).grid(row=0, column=2)

        # Champ token (show="*" natif)
        row2 = ctk.CTkFrame(self.body, fg_color="transparent")
        row2.grid(row=2, column=0, sticky="ew", pady=(6, 4))
        row2.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row2, text="Token :", width=70, anchor="w",
                      font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w")

        self.token_var = ctk.StringVar()
        self.token_entry = ctk.CTkEntry(
            row2, textvariable=self.token_var,
            font=ctk.CTkFont(family="Consolas", size=12),
            show="*", placeholder_text="colle ici les 32 caractères A-Z 0-9",
        )
        self.token_entry.grid(row=0, column=1, sticky="ew", padx=(6, 6))

        ctk.CTkButton(
            row2, text="Tester", height=28, width=90,
            command=self._on_test_token_step,
        ).grid(row=0, column=2)

        self.token_status_lbl = ctk.CTkLabel(
            self.body, text=f"(stockage : {storage_backend()})",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self.token_status_lbl.grid(row=3, column=0, sticky="ew", pady=(10, 0))

    def _on_test_token_step(self):
        token = self.token_var.get().strip()
        if not token:
            self.token_status_lbl.configure(
                text="Entre d'abord un token.",
                text_color=("#cf222e", "#f85149"))
            return
        self.token_status_lbl.configure(text="Test en cours…",
                                           text_color=("gray40", "gray70"))

        def _worker():
            try:
                from vigiechiro_api import VigieChiroClient
                client = VigieChiroClient(token)
                if client.ping():
                    me = client.me()
                    pseudo = me.get("pseudo") or me.get("email") or "?"
                    msg = f"✓ token valide — connecté en tant que {pseudo}"
                    color = ("#2ea043", "#3fb950")
                    self.token_validated = True
                else:
                    msg = "✗ token invalide ou expiré"
                    color = ("#cf222e", "#f85149")
                    self.token_validated = False
            except Exception as e:
                msg = f"✗ erreur : {e}"
                color = ("#cf222e", "#f85149")
                self.token_validated = False

            def _apply():
                try:
                    if self.winfo_exists():
                        self.token_status_lbl.configure(text=msg, text_color=color)
                except Exception:
                    pass
            try:
                self.after(0, _apply)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _save_token_step(self):
        """Persiste le token si non vide (valide ou pas — l'utilisateur
        peut vouloir forcer une valeur qui échouera au ping à cause du réseau)."""
        token = self.token_var.get().strip()
        if token:
            try:
                save_token(token)
            except Exception:
                pass

    # =========================================================================
    # ÉTAPE 2 : Dossier de travail
    # =========================================================================

    def _render_step_workspace(self):
        self.header_title.configure(text="📁  Étape 2/3 — Dossier de travail")
        self.header_sub.configure(
            text="Racine des campagnes, là où tu déposes tes dossiers de nuits.")

        explanation = ctk.CTkLabel(
            self.body,
            text=(
                "Un « workspace » est simplement un dossier contenant tes campagnes "
                "(un sous-dossier par contrat). C'est là que ChiroTool ira :\n\n"
                "   • scanner tes sessions existantes\n"
                "   • écrire le registre local  (registry.db)\n"
                "   • ranger les backups et journaux\n\n"
                "Tu peux changer de workspace à tout moment via « Parcourir… »."
            ),
            font=ctk.CTkFont(size=12),
            justify="left", anchor="w", wraplength=640,
        )
        explanation.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        row1 = ctk.CTkFrame(self.body, fg_color="transparent")
        row1.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        row1.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row1, text="Dossier :", width=80, anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self.ws_var = ctk.StringVar(value=self.settings.last_workspace or "")
        self.ws_entry = ctk.CTkEntry(
            row1, textvariable=self.ws_var,
            placeholder_text="ex : E:\\Chiroptere_test",
        )
        self.ws_entry.grid(row=0, column=1, sticky="ew", padx=(6, 6))

        def _browse():
            p = filedialog.askdirectory(title="Dossier racine de travail",
                                          parent=self)
            if p:
                self.ws_var.set(p)

        ctk.CTkButton(
            row1, text="Parcourir…", height=28, width=100,
            command=_browse,
        ).grid(row=0, column=2)

        self.ws_info = ctk.CTkLabel(
            self.body, text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"), anchor="w", wraplength=640,
        )
        self.ws_info.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self._refresh_ws_info()
        self.ws_var.trace_add("write", lambda *_: self._refresh_ws_info())

    def _refresh_ws_info(self):
        try:
            p = Path(self.ws_var.get().strip())
            if not p.exists():
                self.ws_info.configure(
                    text="(ce dossier n'existe pas encore ; il sera créé au 1er scan)",
                    text_color=("gray50", "gray55"))
                return
            if not p.is_dir():
                self.ws_info.configure(
                    text="⚠ ce chemin n'est pas un dossier",
                    text_color=("#cf222e", "#f85149"))
                return
            n_subs = sum(1 for _ in p.iterdir())
            self.ws_info.configure(
                text=f"✓ dossier valide ({n_subs} éléments)",
                text_color=("#2ea043", "#3fb950"))
        except Exception:
            self.ws_info.configure(text="", text_color=("gray50", "gray55"))

    def _save_workspace_step(self):
        ws = self.ws_var.get().strip()
        if ws:
            self.settings.last_workspace = ws
            # Ajout dans recent_workspaces
            recents = list(self.settings.recent_workspaces or [])
            if ws in recents:
                recents.remove(ws)
            recents.insert(0, ws)
            self.settings.recent_workspaces = recents[:5]

    # =========================================================================
    # ÉTAPE 3 : Parc matériel (optionnel)
    # =========================================================================

    def _render_step_materiels(self):
        self.header_title.configure(text="🎛️  Étape 3/3 — Ton parc matériel")
        self.header_sub.configure(
            text="Enregistreurs et micros utilisés — pour pré-remplir les wizards.")

        explanation = ctk.CTkLabel(
            self.body,
            text=(
                "Saisir ici ton parc matériel permet à ChiroTool de pré-remplir "
                "automatiquement le modèle et la série des enregistreurs dès que "
                "tu choisis leur numéro dans un wizard.\n\n"
                "Cette étape est optionnelle : tu peux la compléter plus tard via "
                "Préférences → Mes matériels."
            ),
            font=ctk.CTkFont(size=12),
            justify="left", anchor="w", wraplength=640,
        )
        explanation.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        # Charge les matériels déjà saisis (au cas où l'utilisateur revient
        # sur cette étape après avoir ajouté dans Préférences).
        self._materiels_local: list[Materiel] = load_materiels()

        # Liste compacte des matériels déjà saisis
        self.mat_list_frame = ctk.CTkScrollableFrame(
            self.body, fg_color=("gray95", "gray18"),
            height=220, corner_radius=6,
        )
        self.mat_list_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.mat_list_frame.grid_columnconfigure(0, weight=1)
        self._refresh_materiels_list()

        # Bouton ajouter (ouvre un petit formulaire inline)
        ctk.CTkButton(
            self.body, text="➕ Ajouter un enregistreur",
            height=32, width=220,
            command=self._prompt_add_materiel,
        ).grid(row=2, column=0, sticky="w", pady=(0, 4))

        hint = ctk.CTkLabel(
            self.body,
            text="💡 Tu pourras modifier/supprimer à tout moment depuis les Préférences.",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color=("gray50", "gray60"), anchor="w",
        )
        hint.grid(row=3, column=0, sticky="w", pady=(0, 0))

    def _refresh_materiels_list(self):
        for w in self.mat_list_frame.winfo_children():
            w.destroy()
        if not self._materiels_local:
            ctk.CTkLabel(
                self.mat_list_frame,
                text="(aucun matériel saisi. Tu peux cliquer « Ajouter » ou skip.)",
                font=ctk.CTkFont(size=11, slant="italic"),
                text_color=("gray45", "gray55"), anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=10, pady=16)
            return
        for i, m in enumerate(self._materiels_local):
            self._build_mat_row(i, m)

    def _build_mat_row(self, idx: int, m: Materiel):
        row = ctk.CTkFrame(self.mat_list_frame, fg_color="transparent")
        row.grid(row=idx, column=0, sticky="ew", padx=4, pady=2)
        row.grid_columnconfigure(0, weight=1)

        lbl = ctk.CTkLabel(
            row,
            text=f"  #{m.id}   {m.modele or m.marque or '(sans modèle)'}"
                 + (f"   série {m.serie_enr}" if m.serie_enr else "")
                 + (f"   + {m.micro_modele}" if m.micro_modele else ""),
            font=ctk.CTkFont(size=12), anchor="w",
        )
        lbl.grid(row=0, column=0, sticky="w", pady=2)

        def _delete(_i=idx):
            if 0 <= _i < len(self._materiels_local):
                del self._materiels_local[_i]
                self._refresh_materiels_list()

        ctk.CTkButton(
            row, text="✕", width=28, height=24,
            fg_color="transparent",
            text_color=("gray50", "gray60"),
            hover_color=("#eb5c5c", "#b84a4a"),
            command=_delete,
        ).grid(row=0, column=1, sticky="e", padx=(6, 4))

    def _prompt_add_materiel(self):
        """Petit dialogue pour saisir un nouveau matériel."""
        dlg = _AddMaterielDialog(self)
        self.wait_window(dlg)
        if dlg.result is not None:
            self._materiels_local.append(dlg.result)
            self._materiels_local.sort(key=lambda m: m.id)
            self._refresh_materiels_list()

    def _save_materiels_step(self):
        try:
            save_materiels(self._materiels_local)
        except Exception:
            pass


class _AddMaterielDialog(ctk.CTkToplevel):
    """Mini-dialogue pour ajouter un matériel dans l'onboarding."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Ajouter un enregistreur")
        self.geometry("480x360")
        self.resizable(False, False)
        self.transient(master)
        self.after(50, self.grab_set)
        self.result: Materiel | None = None

        self.grid_columnconfigure(0, weight=1)

        # Récupère un id libre par défaut
        try:
            existing = load_materiels()
        except Exception:
            existing = []
        # Fusion avec ceux déjà saisis dans le wizard parent (si exposé)
        parent_mats = getattr(master, "_materiels_local", []) or []
        all_used = {m.id for m in existing} | {m.id for m in parent_mats}
        free_id = 1
        while free_id in all_used:
            free_id += 1

        frm = ctk.CTkFrame(self, fg_color="transparent")
        frm.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        frm.grid_columnconfigure(1, weight=1)

        def _add_field(row: int, label: str, var: ctk.StringVar,
                        width: int = 260, placeholder: str = ""):
            ctk.CTkLabel(frm, text=label, anchor="w", width=120).grid(
                row=row, column=0, sticky="w", pady=4)
            e = ctk.CTkEntry(frm, textvariable=var, width=width,
                              placeholder_text=placeholder)
            e.grid(row=row, column=1, sticky="ew", pady=4)
            return e

        self.id_var = ctk.StringVar(value=str(free_id))
        _add_field(0, "N° interne", self.id_var, width=80, placeholder="ex : 7")
        self.marque_var = ctk.StringVar()
        _add_field(1, "Marque", self.marque_var,
                    placeholder="Wildlife Acoustics, Audiomoth, …")
        self.modele_var = ctk.StringVar()
        _add_field(2, "Modèle", self.modele_var,
                    placeholder="SM4BAT FS, AudioMoth, …")
        self.serie_var = ctk.StringVar()
        _add_field(3, "Série enregistreur", self.serie_var,
                    placeholder="S4U04784")
        self.micro_var = ctk.StringVar()
        _add_field(4, "Micro (modèle)", self.micro_var,
                    placeholder="SMX-U1")
        self.micro_serie_var = ctk.StringVar()
        _add_field(5, "Série micro", self.micro_serie_var,
                    placeholder="U1-12345")

        # Footer
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            footer, text="Annuler", width=100, height=32,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self.destroy,
        ).grid(row=0, column=1, padx=(0, 6))
        ctk.CTkButton(
            footer, text="Ajouter", width=120, height=32,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_add,
        ).grid(row=0, column=2)

    def _on_add(self):
        try:
            mid = int(self.id_var.get().strip())
        except (ValueError, TypeError):
            messagebox.showwarning("N° invalide",
                                     "Entre un numéro entier.", parent=self)
            return
        m = Materiel(
            id=mid,
            marque=self.marque_var.get().strip() or None,
            modele=self.modele_var.get().strip() or None,
            serie_enr=self.serie_var.get().strip() or None,
            micro_modele=self.micro_var.get().strip() or None,
            micro_serie=self.micro_serie_var.get().strip() or None,
        )
        self.result = m
        self.destroy()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def should_show_onboarding(settings: Settings) -> bool:
    """True si on doit afficher le wizard au démarrage."""
    return not bool(getattr(settings, "onboarding_done", False))
