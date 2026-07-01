"""
gui_preferences.py — fenêtre Préférences (CTkToplevel modale).

Onglets :
  - Général       : thème, ouverture auto
  - API           : token Vigie-Chiro (save/delete via keyring) + test de validité
  - Nettoyage     : 4 sliders seuils + politique silencieux / taxon inconnu
  - Outils        : chemin ChiroSurf (v2)
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from credentials import delete_token, load_token, save_token, storage_backend
from gui_config import Settings, save_settings
from materiels import (
    Materiel, load_materiels, next_free_id, save_materiels,
)


PORTAIL_URL = "https://vigiechiro.herokuapp.com/"


class PreferencesDialog(ctk.CTkToplevel):
    """Fenêtre modale de préférences."""

    def __init__(self, master, settings: Settings, on_apply):
        super().__init__(master)
        self.settings = settings
        self.on_apply = on_apply

        self.title("Préférences ChiroTool")
        self.geometry("720x680")
        self.minsize(640, 580)

        self.transient(master)
        self.after(50, self.grab_set)   # modal (après affichage pour éviter race)
        self.focus()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # -- UI -----------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(self, corner_radius=8)
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 8))

        self.tabs.add("Général")
        self.tabs.add("API Vigie-Chiro")
        self.tabs.add("Mes matériels")
        self.tabs.add("Nettoyage")
        self.tabs.add("Outils externes")

        self._build_tab_general(self.tabs.tab("Général"))
        self._build_tab_api(self.tabs.tab("API Vigie-Chiro"))
        self._build_tab_materiels(self.tabs.tab("Mes matériels"))
        self._build_tab_cleanup(self.tabs.tab("Nettoyage"))
        self._build_tab_external(self.tabs.tab("Outils externes"))

        # Barre boutons bas
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(footer, text="Annuler", width=120, height=34,
                       fg_color=("gray85", "gray25"),
                       text_color=("gray15", "gray90"),
                       hover_color=("gray75", "gray35"),
                       command=self._on_cancel,
                       ).grid(row=0, column=1, padx=(0, 6))

        ctk.CTkButton(footer, text="Enregistrer", width=140, height=34,
                       font=ctk.CTkFont(weight="bold"),
                       command=self._on_save,
                       ).grid(row=0, column=2)

    # -- Onglet Général -----------------------------------------------------

    def _build_tab_general(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="Apparence",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      anchor="w").grid(row=0, column=0, sticky="ew",
                                        padx=16, pady=(16, 4))

        theme_row = ctk.CTkFrame(tab, fg_color="transparent")
        theme_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        ctk.CTkLabel(theme_row, text="Thème :", width=120,
                      anchor="w").pack(side="left")
        self.theme_var = ctk.StringVar(value=self.settings.appearance)
        self.theme_menu = ctk.CTkOptionMenu(
            theme_row, variable=self.theme_var, width=180,
            values=["system", "light", "dark"],
            command=self._on_theme_change,
        )
        self.theme_menu.pack(side="left")

        ctk.CTkLabel(theme_row, text="  (appliqué à la sauvegarde)",
                      font=ctk.CTkFont(size=10),
                      text_color=("gray50", "gray60")).pack(side="left", padx=8)

        # --- Mises à jour
        ctk.CTkLabel(tab, text="Mises à jour",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      anchor="w").grid(row=2, column=0, sticky="ew",
                                        padx=16, pady=(16, 4))
        self.autoupd_var = ctk.BooleanVar(
            value=getattr(self.settings, "auto_update_check", True))
        ctk.CTkSwitch(
            tab, text="Vérifier les mises à jour au démarrage",
            variable=self.autoupd_var, command=self._on_autoupd_toggle,
        ).grid(row=3, column=0, sticky="w", padx=16, pady=(0, 2))
        ctk.CTkLabel(
            tab, text="Vérification en arrière-plan (sans ralentir le lancement). "
                      "Au plus une fois par jour.",
            font=ctk.CTkFont(size=10), text_color=("gray50", "gray60"),
            anchor="w").grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 8))

        # --- Traitement
        ctk.CTkLabel(tab, text="Traitement",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      anchor="w").grid(row=5, column=0, sticky="ew",
                                        padx=16, pady=(16, 4))
        self.avsafe_var = ctk.BooleanVar(
            value=getattr(self.settings, "av_safe_mode", False))
        ctk.CTkSwitch(
            tab, text="Mode compatible antivirus (préparation ralentie)",
            variable=self.avsafe_var, command=self._on_avsafe_toggle,
        ).grid(row=6, column=0, sticky="w", padx=16, pady=(0, 2))
        ctk.CTkLabel(
            tab, text="Lisse le renommage (petits lots + pauses) pour éviter que "
                      "l'antivirus ne ferme l'application pendant la préparation. "
                      "À n'activer que si tu rencontres ce souci — la préparation "
                      "devient plus lente.",
            font=ctk.CTkFont(size=10), text_color=("gray50", "gray60"),
            anchor="w", justify="left", wraplength=560).grid(
            row=7, column=0, sticky="ew", padx=16, pady=(0, 8))

        ctk.CTkLabel(tab, text="Stockage des préférences",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      anchor="w").grid(row=8, column=0, sticky="ew",
                                        padx=16, pady=(16, 4))

        from gui_config import storage_info
        info = storage_info()
        info_text = (
            f"Mode : {'portable' if info['portable'] else 'installé'}\n"
            f"Dossier config : {info['config_dir']}\n\n"
            "Mode portable activé si 'chirotool.cfg' est posé à côté de l'exécutable.\n"
            "Sinon, les préférences sont stockées dans %APPDATA%."
        )
        ctk.CTkLabel(tab, text=info_text,
                      font=ctk.CTkFont(size=11),
                      text_color=("gray30", "gray70"),
                      justify="left", anchor="w", wraplength=560).grid(
            row=9, column=0, sticky="ew", padx=16, pady=(0, 16))

    def _on_avsafe_toggle(self):
        """Persiste le mode compatible antivirus et l'applique immédiatement via
        la variable d'env lue par rename._av_safe_pace (pas de couplage direct)."""
        import os
        from gui_config import save_settings
        on = bool(self.avsafe_var.get())
        self.settings.av_safe_mode = on
        if on:
            os.environ["CHIROTOOL_AV_SAFE"] = "1"
        else:
            # On retire notre override : le marqueur/variable éventuels
            # reprennent leur comportement propre.
            os.environ.pop("CHIROTOOL_AV_SAFE", None)
        try:
            save_settings(self.settings)
        except Exception:
            pass

    def _on_autoupd_toggle(self):
        """Persiste immédiatement le réglage de vérification auto des MAJ."""
        from gui_config import save_settings
        self.settings.auto_update_check = bool(self.autoupd_var.get())
        # Réactiver le check annule aussi une éventuelle version « ignorée ».
        if self.settings.auto_update_check:
            self.settings.update_skip_version = None
        try:
            save_settings(self.settings)
        except Exception:
            pass

    # -- Onglet API ---------------------------------------------------------

    def _build_tab_api(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="Token Vigie-Chiro",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      anchor="w").grid(row=0, column=0, sticky="ew",
                                        padx=16, pady=(16, 4))

        help_text = (
            "Pour récupérer ton token :\n"
            "  1.  Connecte-toi sur le portail Vigie-Chiro (Google/Facebook).\n"
            "  2.  Ouvre les DevTools du navigateur (F12) → onglet Console.\n"
            "  3.  Colle la commande ci-dessous (bouton 📋) et appuie sur Entrée.\n"
            "  4.  Copie la valeur 32 caractères affichée et colle-la dans le champ Token.\n\n"
            "Le token est stocké chiffré via Windows Credential Manager."
        )
        help_lbl = ctk.CTkLabel(tab, text=help_text,
                                  font=ctk.CTkFont(size=11),
                                  text_color=("gray25", "gray75"),
                                  justify="left", anchor="w",
                                  wraplength=640)
        help_lbl.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        # --- Ligne : "Ouvrir portail" + encart commande JS + bouton Copier
        js_row = ctk.CTkFrame(tab, fg_color="transparent")
        js_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        js_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            js_row, text="🌐 Ouvrir le portail Vigie-Chiro", height=30,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=lambda: webbrowser.open(PORTAIL_URL),
        ).grid(row=0, column=0, padx=(0, 8), sticky="w")

        # Commande JS à copier-coller dans DevTools (encart lecture seule)
        self._js_command = "localStorage.getItem('auth-session-token')"
        js_entry = ctk.CTkEntry(
            js_row,
            font=ctk.CTkFont(family="Consolas", size=11),
            placeholder_text=self._js_command,
        )
        js_entry.insert(0, self._js_command)
        js_entry.configure(state="readonly")  # lecture seule pour éviter l'édition accidentelle
        js_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self._js_entry = js_entry  # référence si besoin

        ctk.CTkButton(
            js_row, text="📋 Copier", width=90, height=30,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._copy_js_command,
        ).grid(row=0, column=2)

        # Champ token
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text="Token :", width=80,
                      anchor="w").grid(row=0, column=0, sticky="w")

        current_token = load_token() or ""
        # Masquage via show="*" natif de CTkEntry : la StringVar contient
        # TOUJOURS le vrai token, seul l'affichage est masqué. Pas de risque
        # de concaténation •••• + vrai token lors d'une frappe.
        self.token_var = ctk.StringVar(value=current_token)
        self._token_visible = False

        self.token_entry = ctk.CTkEntry(
            row, textvariable=self.token_var,
            show="*",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.token_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))

        self.show_btn = ctk.CTkButton(row, text="👁", width=36, height=28,
                                        fg_color=("gray85", "gray25"),
                                        text_color=("gray15", "gray90"),
                                        hover_color=("gray75", "gray35"),
                                        command=self._toggle_show_token)
        self.show_btn.grid(row=0, column=2)

        # Boutons action
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))

        ctk.CTkButton(btn_row, text="Tester la connexion", height=30,
                       command=self._on_test_token,
                       ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(btn_row, text="Effacer le token", height=30,
                       fg_color=("gray85", "gray25"),
                       text_color=("gray15", "gray90"),
                       hover_color=("#eb5c5c", "#b84a4a"),
                       command=self._on_delete_token,
                       ).pack(side="left")

        # Statut
        backend = storage_backend()
        self.token_status_lbl = ctk.CTkLabel(
            tab, text=f"Stockage : {backend}",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"), anchor="w",
        )
        self.token_status_lbl.grid(row=5, column=0, sticky="ew",
                                     padx=16, pady=(0, 16))

    def _on_theme_change(self, value: str):
        """Ne pas appliquer immédiatement : customtkinter 5.2 crash si on
        change l'apparence depuis un callback de widget dans une Toplevel
        modale. On applique seulement à la sauvegarde."""
        # Juste mémoriser le choix, rien d'autre
        pass

    def _toggle_show_token(self):
        """Bascule entre affichage masqué (show='*') et clair (show='')."""
        self._token_visible = not self._token_visible
        try:
            self.token_entry.configure(show="" if self._token_visible else "*")
        except Exception:
            pass

    def _copy_js_command(self):
        """Copie la commande JavaScript d'extraction du token dans le presse-papier.

        Retour visuel : le bouton change brièvement de libellé pour confirmer.
        """
        try:
            self.clipboard_clear()
            self.clipboard_append(self._js_command)
            self.update()  # force le flush du clipboard sur Windows
            # Feedback temporaire dans le label de statut du token
            old = self.token_status_lbl.cget("text") if hasattr(self, "token_status_lbl") else ""
            if hasattr(self, "token_status_lbl"):
                self.token_status_lbl.configure(
                    text="✓ commande copiée — colle-la dans la Console DevTools (F12)",
                    text_color=("#2ea043", "#3fb950"),
                )
                # Restaure l'ancien message après 3 s
                self.after(3000, lambda: self.token_status_lbl.configure(
                    text=old, text_color=("gray40", "gray60")))
        except Exception as e:
            try:
                messagebox.showwarning(
                    "Copie impossible",
                    f"Impossible de copier dans le presse-papier : {e}",
                    parent=self,
                )
            except Exception:
                pass

    def _on_test_token(self):
        token = self.token_var.get().strip()
        if not token:
            messagebox.showwarning("Token absent", "Entre d'abord un token.")
            return
        self.token_status_lbl.configure(text="Test en cours…")

        def _worker():
            try:
                from vigiechiro_api import VigieChiroClient
                client = VigieChiroClient(token)
                if client.ping():
                    me = client.me()
                    pseudo = me.get("pseudo") or me.get("email") or "?"
                    msg = f"✓ token valide — connecté en tant que {pseudo}"
                    color = ("#2ea043", "#2ea043")
                else:
                    msg = "✗ token invalide ou expiré"
                    color = ("#cf222e", "#f85149")
            except Exception as e:
                msg = f"✗ erreur : {e}"
                color = ("#cf222e", "#f85149")

            def _apply():
                if not self.winfo_exists():
                    return
                try:
                    self.token_status_lbl.configure(text=msg, text_color=color)
                except Exception:
                    pass

            try:
                self.after(0, _apply)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_delete_token(self):
        if not messagebox.askyesno(
            "Effacer le token ?",
            "Le token enregistré sera supprimé du stockage sécurisé.\n"
            "Tu devras le recoller au prochain usage de l'API."):
            return
        delete_token()
        self.token_var.set("")
        self.token_status_lbl.configure(
            text=f"Token effacé · stockage : {storage_backend()}",
            text_color=("gray40", "gray60"),
        )

    # -- Onglet Mes matériels ----------------------------------------------

    def _build_tab_materiels(self, tab):
        """Parc d'enregistreurs du BE. Stocké dans materiels.json (APPDATA).

        Chaque ligne représente un matériel identifié par son numéro interne
        (1..27 historique, mais libre). Les infos sont utilisées en priorité
        par les wizards, fallback sur Feuil2 Suivi Excel.
        """
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        # --- Encart d'intro
        intro = ctk.CTkFrame(tab, fg_color=("gray92", "gray20"), corner_radius=6)
        intro.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        ctk.CTkLabel(
            intro,
            text=(
                "Parc d'enregistreurs de ton bureau d'études. Ces infos sont "
                "utilisées en priorité par les wizards lors de la saisie des "
                "métadonnées de session (au lieu de la Feuil2 du Suivi Excel).\n"
                "Stockage : materiels.json dans le dossier de config (persistant "
                "entre sessions, comme le token)."
            ),
            font=ctk.CTkFont(size=11),
            text_color=("gray20", "gray80"),
            wraplength=640, justify="left", anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        # --- Toolbar (ajouter / supprimer)
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 4))
        toolbar.grid_columnconfigure(4, weight=1)

        ctk.CTkButton(
            toolbar, text="➕ Ajouter",
            height=28, width=110,
            command=self._materiels_add,
        ).grid(row=0, column=0, padx=(0, 6))

        ctk.CTkButton(
            toolbar, text="🗑 Supprimer",
            height=28, width=120,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("#eb5c5c", "#b84a4a"),
            command=self._materiels_delete,
        ).grid(row=0, column=1, padx=(0, 6))

        # Export / Import parc — pour partager le parc entre PC / collègues
        ctk.CTkButton(
            toolbar, text="📤 Exporter",
            height=28, width=110,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._materiels_export,
        ).grid(row=0, column=2, padx=(0, 6))

        ctk.CTkButton(
            toolbar, text="📥 Importer",
            height=28, width=110,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._materiels_import,
        ).grid(row=0, column=3, padx=(0, 6))

        self.materiels_status = ctk.CTkLabel(
            toolbar, text="", font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"), anchor="e",
        )
        self.materiels_status.grid(row=0, column=4, sticky="e")

        # --- Liste scrollable des matériels (tableau maison)
        self.materiels_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.materiels_scroll.grid(row=2, column=0, sticky="nsew",
                                      padx=12, pady=(4, 12))
        self.materiels_scroll.grid_columnconfigure(0, weight=1)

        # Charge depuis le disque
        self._materiels: list[Materiel] = load_materiels()
        # Widgets actifs (pour lecture à l'enregistrement)
        self._materiel_rows: list[dict] = []
        self._selected_materiel_idx: int | None = None

        self._refresh_materiels_list()

    def _refresh_materiels_list(self):
        """Redessine la liste des matériels."""
        # Vide les widgets existants
        for w in self.materiels_scroll.winfo_children():
            w.destroy()
        self._materiel_rows.clear()

        if not self._materiels:
            ctk.CTkLabel(
                self.materiels_scroll,
                text="(aucun enregistreur. Clique sur « Ajouter » pour commencer.)",
                font=ctk.CTkFont(size=11, slant="italic"),
                text_color=("gray50", "gray60"),
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=16)
            self.materiels_status.configure(text="0 enregistreur")
            return

        for i, m in enumerate(self._materiels):
            self._build_materiel_row(i, m)
        self.materiels_status.configure(
            text=f"{len(self._materiels)} enregistreur(s)")

    def _build_materiel_row(self, idx: int, m: Materiel):
        """Une ligne éditable par matériel."""
        card = ctk.CTkFrame(
            self.materiels_scroll,
            fg_color=("gray96", "gray17"),
            corner_radius=6,
        )
        card.grid(row=idx, column=0, sticky="ew", padx=2, pady=3)
        card.grid_columnconfigure(1, weight=1)
        card.grid_columnconfigure(3, weight=1)

        # Bind clic = sélection
        def _select(_e=None, i=idx, c=card):
            # Dé-sélectionner les autres
            for j, row in enumerate(self._materiel_rows):
                if j != i:
                    try:
                        row["card"].configure(
                            border_width=0,
                            fg_color=("gray96", "gray17"),
                        )
                    except Exception:
                        pass
            c.configure(
                border_width=2,
                border_color=("#1f6feb", "#58a6ff"),
                fg_color=("#eaf2ff", "#1a2635"),
            )
            self._selected_materiel_idx = i

        card.bind("<Button-1>", _select)

        # Ligne 1 : N° | Marque | Modèle
        ctk.CTkLabel(card, text="N°", width=30, anchor="w",
                      font=ctk.CTkFont(size=11, weight="bold")).grid(
            row=0, column=0, padx=(8, 2), pady=(6, 2), sticky="w")
        id_var = ctk.StringVar(value=str(m.id))
        id_entry = ctk.CTkEntry(card, textvariable=id_var, width=50)
        id_entry.grid(row=0, column=1, sticky="w", padx=(0, 10), pady=(6, 2))

        ctk.CTkLabel(card, text="Marque / Modèle", anchor="w",
                      font=ctk.CTkFont(size=10),
                      text_color=("gray40", "gray60")).grid(
            row=0, column=2, padx=(4, 2), pady=(6, 2), sticky="w")
        mm_frame = ctk.CTkFrame(card, fg_color="transparent")
        mm_frame.grid(row=0, column=3, sticky="ew", padx=(0, 8), pady=(6, 2))
        mm_frame.grid_columnconfigure(0, weight=1)
        mm_frame.grid_columnconfigure(1, weight=2)
        marque_var = ctk.StringVar(value=m.marque or "")
        ctk.CTkEntry(mm_frame, textvariable=marque_var,
                       placeholder_text="Wildlife Acoustics").grid(
            row=0, column=0, sticky="ew", padx=(0, 4))
        modele_var = ctk.StringVar(value=m.modele or "")
        ctk.CTkEntry(mm_frame, textvariable=modele_var,
                       placeholder_text="SM4BAT FS").grid(
            row=0, column=1, sticky="ew")

        # Ligne 2 : Série enregistreur | Notes
        # BUG corrigé : avant on avait columnspan=2 sur le label, mais l'entry
        # venait en col=1 → l'entry recouvrait le label, qui apparaissait
        # tronqué ("Série en" au lieu de "Série enr."). Maintenant le label
        # est en col=0 seul, avec une largeur fixe lisible.
        ctk.CTkLabel(card, text="Série enr.", anchor="w", width=80,
                      font=ctk.CTkFont(size=10),
                      text_color=("gray40", "gray60")).grid(
            row=1, column=0, padx=(8, 2), pady=2, sticky="w")
        serie_var = ctk.StringVar(value=m.serie_enr or "")
        serie_entry = ctk.CTkEntry(
            card, textvariable=serie_var,
            placeholder_text="S4U04784",
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        serie_entry.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=2)

        ctk.CTkLabel(card, text="Notes", anchor="w", width=80,
                      font=ctk.CTkFont(size=10),
                      text_color=("gray40", "gray60")).grid(
            row=1, column=2, padx=(4, 2), pady=2, sticky="w")
        notes_var = ctk.StringVar(value=m.notes or "")
        ctk.CTkEntry(card, textvariable=notes_var,
                       placeholder_text="boîtier rouge, atelier…").grid(
            row=1, column=3, sticky="ew", padx=(0, 8), pady=2)

        # Ligne 3 : Micro modèle | Micro série | Hauteur (même fix)
        ctk.CTkLabel(card, text="Micro mod.", anchor="w", width=80,
                      font=ctk.CTkFont(size=10),
                      text_color=("gray40", "gray60")).grid(
            row=2, column=0, padx=(8, 2), pady=2, sticky="w")
        mic_mod_var = ctk.StringVar(value=m.micro_modele or "")
        ctk.CTkEntry(card, textvariable=mic_mod_var,
                       placeholder_text="SMX-U1").grid(
            row=2, column=1, sticky="ew", padx=(0, 10), pady=2)

        mic_serie_frame = ctk.CTkFrame(card, fg_color="transparent")
        mic_serie_frame.grid(row=2, column=2, columnspan=2, sticky="ew",
                               padx=(4, 8), pady=2)
        mic_serie_frame.grid_columnconfigure(1, weight=1)
        mic_serie_frame.grid_columnconfigure(3, weight=0)
        ctk.CTkLabel(mic_serie_frame, text="série",
                      font=ctk.CTkFont(size=10),
                      text_color=("gray40", "gray60")).grid(
            row=0, column=0, padx=(0, 4), sticky="w")
        mic_serie_var = ctk.StringVar(value=m.micro_serie or "")
        ctk.CTkEntry(mic_serie_frame, textvariable=mic_serie_var,
                       placeholder_text="U1-12345",
                       font=ctk.CTkFont(family="Consolas", size=11)).grid(
            row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkLabel(mic_serie_frame, text="hauteur (m)",
                      font=ctk.CTkFont(size=10),
                      text_color=("gray40", "gray60")).grid(
            row=0, column=2, padx=(0, 4), sticky="w")
        hauteur_var = ctk.StringVar(value=str(m.hauteur_m) if m.hauteur_m is not None else "2")
        ctk.CTkEntry(mic_serie_frame, textvariable=hauteur_var, width=60).grid(
            row=0, column=3, sticky="w")

        # Ligne 4 : Stéréo (optionnel, dépliable)
        stereo_var = ctk.BooleanVar(value=bool(m.stereo))
        mic2_mod_var = ctk.StringVar(value=m.micro2_modele or "")
        mic2_serie_var = ctk.StringVar(value=m.micro2_serie or "")

        stereo_frame = ctk.CTkFrame(card, fg_color="transparent")
        stereo_frame.grid(row=3, column=0, columnspan=4, sticky="ew",
                           padx=8, pady=(2, 6))
        stereo_frame.grid_columnconfigure(2, weight=1)
        stereo_frame.grid_columnconfigure(4, weight=1)

        mic2_mod_entry = ctk.CTkEntry(
            stereo_frame, textvariable=mic2_mod_var,
            placeholder_text="Micro 2 modèle")
        mic2_serie_entry = ctk.CTkEntry(
            stereo_frame, textvariable=mic2_serie_var,
            placeholder_text="Micro 2 série",
            font=ctk.CTkFont(family="Consolas", size=11))

        def _toggle_stereo(*_):
            if stereo_var.get():
                ctk.CTkLabel(stereo_frame, text="Micro 2 :",
                              font=ctk.CTkFont(size=10),
                              text_color=("gray40", "gray60")).grid(
                    row=0, column=1, padx=(6, 4), sticky="w")
                mic2_mod_entry.grid(row=0, column=2, sticky="ew", padx=(0, 6))
                mic2_serie_entry.grid(row=0, column=4, sticky="ew", padx=(0, 4))
            else:
                for w in (mic2_mod_entry, mic2_serie_entry):
                    try:
                        w.grid_forget()
                    except Exception:
                        pass
                # Garder le label Micro 2 ? On le laisse vivre discrètement

        ctk.CTkCheckBox(
            stereo_frame, text="Stéréo (2 micros)",
            variable=stereo_var, command=_toggle_stereo,
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=0, sticky="w")
        _toggle_stereo()

        # Mémorisation des handles pour relecture au save
        self._materiel_rows.append({
            "card": card,
            "id_var": id_var,
            "marque_var": marque_var,
            "modele_var": modele_var,
            "serie_var": serie_var,
            "notes_var": notes_var,
            "mic_mod_var": mic_mod_var,
            "mic_serie_var": mic_serie_var,
            "hauteur_var": hauteur_var,
            "stereo_var": stereo_var,
            "mic2_mod_var": mic2_mod_var,
            "mic2_serie_var": mic2_serie_var,
        })

    def _materiels_add(self):
        """Ajoute un matériel vide à la fin de la liste."""
        # Persist l'état actuel des champs avant d'ajouter (sinon perte saisie)
        self._collect_materiels_from_ui()
        new_id = next_free_id(self._materiels, start=1)
        self._materiels.append(Materiel(id=new_id))
        self._refresh_materiels_list()

    def _materiels_export(self):
        """Exporte le parc matériel en JSON pour partage entre PC/collègues."""
        from datetime import datetime as _dt
        # Persiste d'abord les édits en cours du formulaire
        self._collect_materiels_from_ui()
        if not self._materiels:
            messagebox.showwarning(
                "Export impossible",
                "Aucun matériel à exporter. Ajoute-en d'abord.",
                parent=self,
            )
            return
        ts = _dt.now().strftime("%Y%m%d_%H%M")
        path = filedialog.asksaveasfilename(
            title="Exporter le parc matériel",
            initialfile=f"chirotool_materiels_{ts}.json",
            filetypes=[("JSON", "*.json")],
            defaultextension=".json",
            parent=self,
        )
        if not path:
            return
        try:
            import json
            from dataclasses import asdict
            payload = {
                "schema_version": 1,
                "exported_at": _dt.now().isoformat(timespec="seconds"),
                "materiels": [asdict(m) for m in self._materiels],
            }
            Path(path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            messagebox.showinfo(
                "Export réussi",
                f"✓ {len(self._materiels)} matériel(s) exporté(s)\n   {Path(path).name}",
                parent=self,
            )
        except Exception as e:
            messagebox.showerror("Erreur export", str(e), parent=self)

    def _ask_import_mode(self, n_import: int, n_conflicts: int) -> str | None:
        """Dialogue à boutons explicites : Fusionner / Remplacer / Annuler.

        Retourne "merge", "replace" ou None (annulé).
        """
        dlg = ctk.CTkToplevel(self)
        dlg.title("Mode d'import")
        dlg.geometry("520x260")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.after(50, dlg.grab_set)
        dlg.grid_columnconfigure(0, weight=1)
        result = {"mode": None}

        ctk.CTkLabel(
            dlg,
            text=(
                f"{n_import} matériel(s) à importer  "
                f"({n_conflicts} ont un numéro déjà présent chez toi).\n\n"
                "Comment veux-tu procéder ?"
            ),
            font=ctk.CTkFont(size=12),
            justify="left", anchor="w", wraplength=480,
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 14))

        def _pick(mode):
            result["mode"] = mode
            dlg.destroy()

        ctk.CTkButton(
            dlg, text="🔀  Fusionner  (garde tout, l'import gagne sur les conflits)",
            height=40, anchor="w",
            command=lambda: _pick("merge"),
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=4)

        ctk.CTkButton(
            dlg, text="♻  Remplacer  (vide ton parc puis importe)",
            height=40, anchor="w",
            fg_color=("#cf222e", "#b42318"),
            hover_color=("#b42318", "#961f17"),
            text_color="white",
            command=lambda: _pick("replace"),
        ).grid(row=2, column=0, sticky="ew", padx=20, pady=4)

        ctk.CTkButton(
            dlg, text="Annuler", height=32, width=100,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=dlg.destroy,
        ).grid(row=3, column=0, sticky="e", padx=20, pady=(10, 14))

        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        self.wait_window(dlg)
        return result["mode"]

    def _materiels_import(self):
        """Importe un parc matériel depuis un JSON (avec fusion)."""
        path = filedialog.askopenfilename(
            title="Importer un parc matériel",
            filetypes=[("JSON", "*.json"), ("Tous", "*")],
            parent=self,
        )
        if not path:
            return
        try:
            import json
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            imported_raw = data.get("materiels") or []
        except Exception as e:
            messagebox.showerror("Lecture impossible",
                                 f"Le fichier n'est pas un JSON valide :\n{e}",
                                 parent=self)
            return

        from materiels import Materiel as _M
        new_ms: list[Materiel] = []
        known_fields = {f for f in _M.__dataclass_fields__}
        for raw in imported_raw:
            if not isinstance(raw, dict) or "id" not in raw:
                continue
            try:
                clean = {k: v for k, v in raw.items() if k in known_fields}
                clean["id"] = int(clean["id"])
                new_ms.append(_M(**clean))
            except (TypeError, ValueError):
                continue

        if not new_ms:
            messagebox.showwarning("Import vide",
                                    "Aucun matériel exploitable trouvé.",
                                    parent=self)
            return

        # Persiste les éventuels édits en cours
        self._collect_materiels_from_ui()

        # Choix : Remplacer ou Fusionner ? Dialogue à boutons EXPLICITES
        # (évite l'ambiguïté Oui/Non = Fusionner/Remplacer, dangereuse).
        existing_ids = {m.id for m in self._materiels}
        new_ids = {m.id for m in new_ms}
        conflicts = existing_ids & new_ids
        if not self._materiels:
            mode = "replace"
            if not messagebox.askyesno(
                "Importer",
                f"{len(new_ms)} matériel(s) à importer.\n\n"
                "Ton parc local est vide → import direct.\n\nConfirmer ?",
                parent=self):
                return
        else:
            mode = self._ask_import_mode(len(new_ms), len(conflicts))
            if mode is None:
                return

        if mode == "replace":
            self._materiels = list(new_ms)
        else:  # merge
            # Pour chaque ID, on garde le nouveau (priorité à l'import)
            by_id = {m.id: m for m in self._materiels}
            for m in new_ms:
                by_id[m.id] = m
            self._materiels = sorted(by_id.values(), key=lambda m: m.id)

        self._refresh_materiels_list()
        messagebox.showinfo(
            "Import terminé",
            f"✓ Parc mis à jour ({len(self._materiels)} matériels au total)\n"
            "Pense à cliquer « Enregistrer » pour persister.",
            parent=self,
        )

    def _materiels_delete(self):
        """Supprime le matériel sélectionné (ou le dernier si rien sélectionné)."""
        self._collect_materiels_from_ui()
        if not self._materiels:
            return
        idx = self._selected_materiel_idx
        if idx is None or idx >= len(self._materiels):
            # Confirme la suppression du dernier
            if not messagebox.askyesno(
                "Supprimer ?",
                "Aucune ligne sélectionnée. Supprimer le dernier enregistreur ?",
                parent=self,
            ):
                return
            idx = len(self._materiels) - 1
        else:
            m = self._materiels[idx]
            if not messagebox.askyesno(
                "Supprimer ?",
                f"Supprimer l'enregistreur #{m.id} "
                f"({m.modele or m.marque or 'sans modèle'}) ?",
                parent=self,
            ):
                return
        del self._materiels[idx]
        self._selected_materiel_idx = None
        self._refresh_materiels_list()

    def _collect_materiels_from_ui(self) -> None:
        """Relit les StringVar/BooleanVar des cards vers self._materiels."""
        def _i(v: str) -> int | None:
            try:
                return int(v.strip())
            except (ValueError, AttributeError):
                return None

        def _f(v: str) -> float | None:
            s = (v or "").replace(",", ".").strip()
            if not s:
                return None
            try:
                return float(s)
            except ValueError:
                return None

        def _s(v: str) -> str | None:
            s = (v or "").strip()
            return s or None

        new_list: list[Materiel] = []
        for row in self._materiel_rows:
            mid = _i(row["id_var"].get())
            if mid is None:
                continue  # ligne sans id → ignorée (plutôt que crasher)
            new_list.append(Materiel(
                id=mid,
                marque=_s(row["marque_var"].get()),
                modele=_s(row["modele_var"].get()),
                serie_enr=_s(row["serie_var"].get()),
                notes=_s(row["notes_var"].get()),
                micro_modele=_s(row["mic_mod_var"].get()),
                micro_serie=_s(row["mic_serie_var"].get()),
                hauteur_m=_f(row["hauteur_var"].get()),
                stereo=bool(row["stereo_var"].get()),
                micro2_modele=_s(row["mic2_mod_var"].get()),
                micro2_serie=_s(row["mic2_serie_var"].get()),
            ))
        self._materiels = new_list

    # -- Onglet Nettoyage ---------------------------------------------------

    def _build_tab_cleanup(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        # Encart explicatif : comment marche le cleanup (2 niveaux de décision)
        intro = ctk.CTkFrame(tab, fg_color=("gray92", "gray20"), corner_radius=6)
        intro.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        intro.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            intro,
            text=(
                "Le nettoyage travaille sur le xlsx d'observations téléchargé "
                "depuis Vigie-Chiro (participation-<id>-observations.xlsx). "
                "Il opère à deux niveaux :\n"
                "   • contact par contact  (lignes du xlsx) → seuils ci-dessous\n"
                "   • fichier par fichier  (WAV sur disque) → règle OR : un WAV "
                "est gardé dès qu'au moins 1 de ses contacts est conservé"
            ),
            font=ctk.CTkFont(size=11),
            text_color=("gray20", "gray80"),
            wraplength=640, justify="left", anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        ctk.CTkLabel(tab, text="Seuils de conservation (par groupe)",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      anchor="w").grid(row=1, column=0, sticky="ew",
                                        padx=16, pady=(10, 2))

        ctk.CTkLabel(tab, text=(
            "Un contact est conservé si tadarida_probabilite ≥ seuil du groupe."),
                      font=ctk.CTkFont(size=11),
                      text_color=("gray30", "gray70"),
                      wraplength=640, justify="left", anchor="w").grid(
            row=2, column=0, sticky="ew", padx=16, pady=(0, 8))

        self.threshold_sliders: dict[str, tuple[ctk.CTkSlider, ctk.CTkLabel]] = {}
        groups = [
            ("chiros", "Chiroptères", self.settings.threshold_chiros),
            ("orthos", "Orthoptères (insectes)", self.settings.threshold_orthos),
            ("micromam", "Micromammifères", self.settings.threshold_micromam),
            ("oiseaux", "Oiseaux", self.settings.threshold_oiseaux),
        ]
        for i, (key, label, val) in enumerate(groups):
            row = ctk.CTkFrame(tab, fg_color="transparent")
            row.grid(row=3 + i, column=0, sticky="ew", padx=16, pady=3)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row, text=label, width=160,
                          anchor="w").grid(row=0, column=0, sticky="w")

            val_lbl = ctk.CTkLabel(row, text=f"{val:.2f}", width=48,
                                     font=ctk.CTkFont(family="Consolas", size=12,
                                                        weight="bold"),
                                     anchor="e")
            val_lbl.grid(row=0, column=2, padx=(4, 0))

            def _cb_factory(lbl):
                return lambda v: lbl.configure(text=f"{float(v):.2f}")

            slider = ctk.CTkSlider(row, from_=0.0, to=1.0, number_of_steps=20,
                                    command=_cb_factory(val_lbl))
            slider.set(val)
            slider.grid(row=0, column=1, sticky="ew", padx=(8, 4))

            self.threshold_sliders[key] = (slider, val_lbl)

        # --- Encart "Toujours supprimé" (info-only, non configurable) ---
        always = ctk.CTkFrame(tab, fg_color=("#fff4d6", "#3a2d12"), corner_radius=6)
        always.grid(row=10, column=0, sticky="ew", padx=12, pady=(14, 6))
        always.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            always,
            text=(
                "⚠  Toujours supprimés  (non configurable)\n"
                "   • contacts classés « noise » par Tadarida (bruit identifié "
                "comme tel dans la colonne tadarida_taxon)"
            ),
            font=ctk.CTkFont(size=11),
            text_color=("#7a5a00", "#e8c060"),
            justify="left", anchor="w", wraplength=640,
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=8)

        # --- Politique : WAV pour lesquels Tadarida n'a rien détecté ---
        ctk.CTkLabel(tab, text="WAV sans aucune détection Tadarida",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      anchor="w").grid(row=11, column=0, sticky="ew",
                                        padx=16, pady=(14, 2))
        ctk.CTkLabel(
            tab,
            text=(
                "Fichiers WAV qui n'apparaissent dans AUCUNE ligne du xlsx "
                "(Tadarida n'a détecté ni chiro, ni orthoptère, ni même du "
                "noise). Typiquement : vent fort, pluie, silence absolu."
            ),
            font=ctk.CTkFont(size=11),
            text_color=("gray30", "gray70"),
            wraplength=640, justify="left", anchor="w",
        ).grid(row=12, column=0, sticky="ew", padx=16, pady=(0, 4))

        self.silent_var = ctk.StringVar(value=self.settings.silent_policy)
        silent_row = ctk.CTkFrame(tab, fg_color="transparent")
        silent_row.grid(row=13, column=0, sticky="w", padx=16, pady=(0, 8))
        ctk.CTkRadioButton(silent_row, text="Supprimer (recommandé)",
                            variable=self.silent_var, value="delete"
                            ).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(silent_row, text="Conserver",
                            variable=self.silent_var, value="keep"
                            ).pack(side="left")

        # --- Politique : contacts avec taxon que ChiroTool ne sait pas classer ---
        ctk.CTkLabel(tab, text="Contacts avec taxon non classé par ChiroTool",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      anchor="w").grid(row=14, column=0, sticky="ew",
                                        padx=16, pady=(10, 2))
        ctk.CTkLabel(
            tab,
            text=(
                "Contacts dont le tadarida_taxon n'est ni chiro, ni orthoptère, "
                "ni micromam, ni oiseau, ni noise (nouveaux taxons MNHN, "
                "tadarida_taxon_autre atypique). Ce N'EST PAS du bruit — juste "
                "un taxon que ChiroTool ne sait pas ranger dans un groupe."
            ),
            font=ctk.CTkFont(size=11),
            text_color=("gray30", "gray70"),
            wraplength=640, justify="left", anchor="w",
        ).grid(row=15, column=0, sticky="ew", padx=16, pady=(0, 4))

        self.unknown_var = ctk.StringVar(value=self.settings.unknown_action)
        u_row = ctk.CTkFrame(tab, fg_color="transparent")
        u_row.grid(row=16, column=0, sticky="w", padx=16, pady=(0, 16))
        ctk.CTkRadioButton(u_row, text="Conserver (recommandé)",
                            variable=self.unknown_var, value="keep"
                            ).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(u_row, text="Supprimer",
                            variable=self.unknown_var, value="delete"
                            ).pack(side="left")

    # -- Onglet Outils externes --------------------------------------------

    def _build_tab_external(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="ChiroSurf (validation sonogrammes)",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      anchor="w").grid(row=0, column=0, sticky="ew",
                                        padx=16, pady=(16, 4))

        ctk.CTkLabel(tab, text=(
            "Logiciel portable recommandé pour la validation acoustique.\n"
            "Fonctionnalité prévue en v2 : clic sur un contact → ouverture directe."),
                      font=ctk.CTkFont(size=11),
                      text_color=("gray30", "gray70"),
                      wraplength=640, justify="left", anchor="w").grid(
            row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text="Chemin :", width=80,
                      anchor="w").grid(row=0, column=0, sticky="w")

        self.chirosurf_var = ctk.StringVar(value=self.settings.chirosurf_path or "")
        ctk.CTkEntry(row, textvariable=self.chirosurf_var).grid(
            row=0, column=1, sticky="ew", padx=(8, 8))

        ctk.CTkButton(row, text="Parcourir…", width=100, height=28,
                       fg_color=("gray85", "gray25"),
                       text_color=("gray15", "gray90"),
                       hover_color=("gray75", "gray35"),
                       command=self._on_browse_chirosurf,
                       ).grid(row=0, column=2)

    def _on_browse_chirosurf(self):
        p = filedialog.askopenfilename(
            title="ChiroSurf.exe",
            filetypes=[("Exécutable", "*.exe"), ("Tous fichiers", "*")],
        )
        if p:
            self.chirosurf_var.set(p)

    # -- Save / Cancel ------------------------------------------------------

    def _on_save(self):
        # Token : la StringVar contient toujours la vraie valeur (show="*"
        # ne masque qu'à l'affichage), donc on lit directement et on compare
        # au token actuellement stocké pour éviter une écriture inutile.
        token_value = self.token_var.get().strip()
        if token_value and token_value != (load_token() or ""):
            save_token(token_value)
            self.token_status_lbl.configure(
                text=f"Token enregistré · stockage : {storage_backend()}",
                text_color=("gray40", "gray60"),
            )

        # Settings
        self.settings.appearance = self.theme_var.get()
        self.settings.threshold_chiros = round(self.threshold_sliders["chiros"][0].get(), 2)
        self.settings.threshold_orthos = round(self.threshold_sliders["orthos"][0].get(), 2)
        self.settings.threshold_micromam = round(self.threshold_sliders["micromam"][0].get(), 2)
        self.settings.threshold_oiseaux = round(self.threshold_sliders["oiseaux"][0].get(), 2)
        self.settings.silent_policy = self.silent_var.get()
        self.settings.unknown_action = self.unknown_var.get()
        self.settings.chirosurf_path = self.chirosurf_var.get().strip() or None

        save_settings(self.settings)

        # Matériels : collecte les champs UI puis persiste dans materiels.json
        try:
            self._collect_materiels_from_ui()
            save_materiels(self._materiels)
        except Exception as e:
            messagebox.showwarning(
                "Sauvegarde matériels",
                f"Les matériels n'ont pas pu être enregistrés : {e}",
                parent=self,
            )

        if self.on_apply:
            self.on_apply(self.settings)

        # Ferme d'abord la fenêtre (libère le grab), PUIS applique le thème
        # via after(0) sur le master pour éviter le crash connu de CTk 5.2
        new_theme = self.settings.appearance
        master = self.master

        def _apply_theme_safe():
            try:
                ctk.set_appearance_mode(new_theme)
            except Exception:
                pass  # silencieux : pas de crash si CTk ne peut pas basculer

        self.destroy()
        try:
            master.after(50, _apply_theme_safe)
        except Exception:
            pass

    def _on_cancel(self):
        # On n'applique pas le thème en live → rien à restaurer
        self.destroy()
