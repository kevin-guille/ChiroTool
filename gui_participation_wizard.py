"""
gui_participation_wizard.py — wizard de création d'une participation Vigie-Chiro.

Ouvert avant l'upload API pour collecter :
  - météo (températures début/fin entières si renseignées ; vent & couverture
    en enum stricts) — **non bloquante** : le Summary préremplit les T° quand
    il est là ; vent/couverture restent optionnels (saisie terrain, complétable
    plus tard sur le portail web)
  - configuration matériel (détecteur, micro gauche, hauteur)
  - option stéréo (micro droit)
  - commentaire libre

Pré-remplissage :
  1. Log Titley (horaires Recording start/stop, T°) s'il est dans la session
  2. sinon Summary.txt (T°) ; dates WAV si le Summary couvre plusieurs jours
  3. Parc matériel / Feuil2 (modèle enregistreur / micro)
  4. Manifest existant (dates périmées ignorées)

Retour : ``payload`` compatible ``VigieChiroClient.create_participation``.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path

import customtkinter as ctk

from chiro_core import (
    build_participation_configuration,
    collect_wizard_prefill,
    temperatures_are_user_set,
)
from manifest import Manifest
from naming import SessionMeta
from vigiechiro_enums import (
    COUVERTURE_VALUES, DETECTEUR_ENREGISTREUR_TYPES, MICRO_MODELES, VENT_VALUES,
    couverture_from_label, couverture_labels, vent_from_label, vent_labels,
)

# Valeur sentinelle en tête des listes non devinables (météo, matériel) : force
# un choix conscient. Sans elle, les menus défaultaient sur la 1re valeur et une
# participation validée sans y toucher publiait des métadonnées FAUSSES et
# irrécupérables sur le serveur national.
_UNSET = "— à renseigner —"


class ParticipationWizard(ctk.CTkToplevel):
    """Wizard pour collecter les metadata de participation.

    Résultat exploitable après ``wait_window()`` via ``self.result``.
    None si l'utilisateur a annulé.
    """

    def __init__(self, master, *, session_path: Path, meta: SessionMeta):
        super().__init__(master)
        self.title("Nouvelle participation Vigie-Chiro")
        self.geometry("760x720")
        self.minsize(680, 640)

        self.session_path = Path(session_path)
        self.meta = meta
        self.result: dict | None = None
        self._prefill: dict = {}
        self._prefill_ready = False
        self._validate_btn = None

        from gui_windowing import bind_modal
        bind_modal(self, master)
        self.focus()

        # Formulaire d'abord (issue #9) : un Data_k de 4000 WAV sur disque
        # externe ne doit plus laisser une fenêtre noire pendant le scan.
        self._build_ui()
        try:
            self.update_idletasks()
        except Exception:
            pass
        self._set_prefill_busy(True)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        def _worker():
            try:
                pre = self._collect_prefill()
            except Exception as e:
                pre = {"_prefill_error": str(e)}
            try:
                self.after(0, lambda p=pre: self._apply_prefill(p))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    # -- Pré-remplissage ---------------------------------------------------

    def _collect_prefill(self) -> dict:
        """Agrège les valeurs pré-remplies depuis log Titley, Summary, parc, manifest."""
        pre = collect_wizard_prefill(
            self.session_path,
            n_enregistreur=self.meta.n_enregistreur,
            date_debut=self.meta.date_debut,
        )
        if not pre.get("_used_materiels"):
            try:
                from suivi import Suivi, _default_path
                path = _default_path(
                    self.meta.date_debut.year if self.meta.date_debut else None)
                if path and path.is_file() and self.meta.n_enregistreur is not None:
                    suivi = Suivi(path)
                    e = suivi.enregistreur(self.meta.n_enregistreur)
                    if e:
                        if e.modele and not pre.get("detecteur_enregistreur_type"):
                            pre["detecteur_enregistreur_type"] = e.modele
                        if e.serie_micro and not pre.get("micro0_modele"):
                            serie = str(e.serie_micro).strip()
                            guessed = self._guess_micro_model(e.modele or "", serie)
                            if guessed:
                                pre["micro0_modele"] = guessed
            except Exception:
                pass
        return pre

    def _set_prefill_busy(self, busy: bool) -> None:
        hint = getattr(self, "_dates_hint", None)
        if busy and hint is not None:
            try:
                hint.configure(
                    text="Lecture des métadonnées (log Titley / Summary)…")
            except Exception:
                pass
        btn = self._validate_btn
        if btn is not None:
            try:
                btn.configure(state=("disabled" if busy else "normal"))
            except Exception:
                pass

    def _apply_prefill(self, pre: dict) -> None:
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        err = (pre or {}).pop("_prefill_error", None)
        self._prefill = pre or {}
        self._prefill_ready = True
        self._set_prefill_busy(False)
        try:
            self._fill_defaults()
        except Exception as e:
            err = err or str(e)
        if err:
            try:
                self.err_lbl.configure(
                    text=f"Pré-remplissage partiel : {err}")
            except Exception:
                pass

    def _guess_micro_model(self, detecteur: str, serie_micro: str) -> str:
        """Heuristique simple pour deviner le modèle du micro."""
        det = detecteur.upper()
        if "SM4" in det:
            return "SM4 BAT FS"
        if "SMX" in serie_micro.upper():
            return serie_micro   # ex SMX-US, SMX-U1
        if "AUDIOMOTH" in det or det == "MU":
            return "MU (Audiomoth)"
        if "SM MINI" in det or "SMMINI" in det:
            return "SMX-U1"      # typique des SM Mini 2
        return ""

    # -- UI -----------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        ctk.CTkLabel(
            self, text="Nouvelle participation",
            font=ctk.CTkFont(size=16, weight="bold"), anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))

        sub = (
            f"Site {self.meta.n_site_tadarida} · point {self.meta.n_point_fixe} · "
            f"Pass {self.meta.n_passage} · enregistreur #{self.meta.n_enregistreur} "
            f"({self.meta.n_serie})"
        )
        ctk.CTkLabel(
            self, text=sub, anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))

        # Contenu scrollable (formulaire assez long)
        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.grid(row=2, column=0, sticky="nsew", padx=12, pady=0)
        form.grid_columnconfigure(1, weight=1)

        row = 0
        # --- Section dates ---
        row = self._section(form, row, "Dates de pose")

        self._label(form, row, "Début *")
        self.date_debut_var = ctk.StringVar()
        self.date_debut_entry = ctk.CTkEntry(
            form, textvariable=self.date_debut_var,
            placeholder_text="YYYY-MM-DD HH:MM",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.date_debut_entry.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        row += 1

        self._label(form, row, "Fin *")
        self.date_fin_var = ctk.StringVar()
        self.date_fin_entry = ctk.CTkEntry(
            form, textvariable=self.date_fin_var,
            placeholder_text="YYYY-MM-DD HH:MM",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.date_fin_entry.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        row += 1

        self._dates_hint = ctk.CTkLabel(
            form, text="",
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray60"),
            anchor="w", justify="left", wraplength=480,
        )
        self._dates_hint.grid(row=row, column=0, columnspan=2,
                              sticky="ew", padx=16, pady=(0, 4))
        row += 1

        # --- Section météo (optionnelle : ne bloque pas l'upload) ---
        row = self._section(form, row, "Conditions météo (optionnel)")
        ctk.CTkLabel(
            form,
            text=("T° / horaires lus dans le log Titley si présent, sinon dans le Summary.txt. "
                  "Vent / couverture = observation terrain, non mesurées "
                  "par le boîtier, complétables plus tard sur le portail."),
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
            anchor="w",
            justify="left",
            wraplength=680,
        ).grid(row=row, column=0, columnspan=2, sticky="ew",
               padx=16, pady=(0, 4))
        row += 1

        self._label(form, row, "T° début de nuit (°C)",
                      help="Log Titley ou Summary · entier optionnel")
        self.temp_deb_var = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self.temp_deb_var, width=120,
                       placeholder_text="ex: 22",
                       ).grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        self._label(form, row, "T° fin de nuit (°C)",
                      help="Log Titley ou Summary · entier optionnel")
        self.temp_fin_var = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self.temp_fin_var, width=120,
                       placeholder_text="ex: 15",
                       ).grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        self._label(form, row, "Vent",
                      help="Force du vent · optionnel")
        self.vent_label_var = ctk.StringVar(value=_UNSET)
        ctk.CTkOptionMenu(
            form, variable=self.vent_label_var, values=[_UNSET] + vent_labels(),
            width=160,
        ).grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        self._label(form, row, "Couverture nuageuse",
                      help="Nuages (0 à 100 %) · optionnel")
        self.cov_label_var = ctk.StringVar(value=_UNSET)
        ctk.CTkOptionMenu(
            form, variable=self.cov_label_var,
            values=[_UNSET] + couverture_labels(), width=160,
        ).grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        # --- Section matériel ---
        row = self._section(form, row, "Matériel")

        # Enrichissement : prépend les modèles du parc matériel (Préférences →
        # Mes matériels) au-dessus des listes standards. Le nom reste tel quel
        # (pas de préfixe visuel type ★) pour que ce soit directement envoyable
        # à l'API sans post-traitement.
        det_values = self._build_material_choices(
            DETECTEUR_ENREGISTREUR_TYPES, attr="modele")
        mic_values = self._build_material_choices(
            MICRO_MODELES, attr="micro_modele", attr2="micro2_modele")

        self._label(form, row, "Détecteur / enregistreur *")
        self.det_var = ctk.StringVar()
        det_frame = ctk.CTkFrame(form, fg_color="transparent")
        det_frame.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        det_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkOptionMenu(
            det_frame, variable=self.det_var, values=[_UNSET] + det_values,
            width=220, command=self._on_det_change,
            dynamic_resizing=False,
        ).grid(row=0, column=0, sticky="w")
        # Champ libre visible uniquement si "Autre" sélectionné
        self.det_other_var = ctk.StringVar()
        self.det_other_entry = ctk.CTkEntry(
            det_frame, textvariable=self.det_other_var,
            placeholder_text="préciser le modèle…", width=260,
        )
        # pas de grid() : affiché dynamiquement par _on_det_change
        row += 1

        self._label(form, row, "Micro gauche (modèle)")
        self.mic0_var = ctk.StringVar()
        mic0_frame = ctk.CTkFrame(form, fg_color="transparent")
        mic0_frame.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        mic0_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkOptionMenu(
            mic0_frame, variable=self.mic0_var, values=[_UNSET] + mic_values,
            width=220, command=self._on_mic0_change,
            dynamic_resizing=False,
        ).grid(row=0, column=0, sticky="w")
        self.mic0_other_var = ctk.StringVar()
        self.mic0_other_entry = ctk.CTkEntry(
            mic0_frame, textvariable=self.mic0_other_var,
            placeholder_text="préciser le modèle…", width=260,
        )
        row += 1
        # Mémoriser la liste des micros pour re-use sur le micro droit stéréo
        self._mic_values = mic_values

        self._label(form, row, "Hauteur micro gauche (m)",
                      help="Négatif si détecteur en gîte ; bornes : -50 à +100")
        self.mic0_h_var = ctk.StringVar(value="2")
        ctk.CTkEntry(form, textvariable=self.mic0_h_var, width=100,
                       placeholder_text="2").grid(
            row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        # --- Section stéréo (optionnelle) ---
        self.stereo_var = ctk.BooleanVar(value=False)
        stereo_frame = ctk.CTkFrame(form, fg_color="transparent")
        stereo_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(10, 4))
        ctk.CTkCheckBox(
            stereo_frame, text="Enregistrement stéréo (2 micros)",
            variable=self.stereo_var, command=self._on_stereo_toggle,
        ).pack(side="left")
        row += 1

        # Micro droit (initialement masqué) — avec champ libre "Autre" en bonus
        self._mic1_rows: list = []

        self._mic1_label = ctk.CTkLabel(form, text="Micro droit (modèle)",
                                          anchor="w", width=140,
                                          font=ctk.CTkFont(size=12, weight="bold"))
        self.mic1_var = ctk.StringVar()
        self.mic1_other_var = ctk.StringVar()
        self._mic1_menu = ctk.CTkOptionMenu(
            form, variable=self.mic1_var,
            values=getattr(self, "_mic_values", MICRO_MODELES), width=220,
            command=self._on_mic1_change, dynamic_resizing=False)
        self._mic1_other_entry = ctk.CTkEntry(
            form, textvariable=self.mic1_other_var,
            placeholder_text="préciser le modèle…", width=260)

        self._mic1h_label = ctk.CTkLabel(form, text="Hauteur micro droit (m)",
                                           anchor="w", width=140,
                                           font=ctk.CTkFont(size=12, weight="bold"))
        self.mic1_h_var = ctk.StringVar(value="2")
        self._mic1h_entry = ctk.CTkEntry(form, textvariable=self.mic1_h_var,
                                           width=100, placeholder_text="2")

        # --- Section commentaire ---
        row = self._section(form, row + 2, "Commentaire")

        self.comment_txt = ctk.CTkTextbox(form, height=80)
        self.comment_txt.grid(row=row, column=0, columnspan=2,
                                sticky="ew", padx=16, pady=(4, 12))
        row += 1

        # --- Erreurs ---
        self.err_lbl = ctk.CTkLabel(
            self, text="", anchor="w", justify="left",
            font=ctk.CTkFont(size=11),
            text_color=("#cf222e", "#f85149"),
            wraplength=700,
        )
        self.err_lbl.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 0))

        # --- Footer ---
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=16, pady=(6, 14))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            footer, text="Annuler", width=100, height=34,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_cancel,
        ).grid(row=0, column=1, padx=(0, 6))

        self._validate_btn = ctk.CTkButton(
            footer, text="Valider", width=140, height=34,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_validate,
        )
        self._validate_btn.grid(row=0, column=2)

    def _section(self, form, row: int, title: str) -> int:
        ctk.CTkLabel(
            form, text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=row, column=0, columnspan=2, sticky="ew",
               padx=16, pady=(16, 6))
        return row + 1

    def _label(self, form, row: int, text: str, *, help: str = ""):
        """Titre + aide empilés (deux labels dans la même cellule se recouvraient)."""
        cell = ctk.CTkFrame(form, fg_color="transparent")
        cell.grid(row=row, column=0, sticky="nw", padx=(16, 4), pady=(4, 0))
        cell.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            cell, text=text, width=220, anchor="w", justify="left",
            wraplength=200,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        if help:
            ctk.CTkLabel(
                cell, text=help, width=220, anchor="w", justify="left",
                wraplength=200,
                font=ctk.CTkFont(size=10),
                text_color=("gray50", "gray60"),
            ).grid(row=1, column=0, sticky="w")

    def _build_material_choices(self, base_list: list[str], *,
                                 attr: str, attr2: str | None = None) -> list[str]:
        """Enrichit ``base_list`` avec les modèles trouvés dans le parc local.

        Les modèles du parc (Préférences → Mes matériels) sont ajoutés EN TÊTE
        de la liste pour être proposés en premier (UX : ce que l'utilisateur
        a saisi vaut priorité sur les listes génériques). Les doublons sont
        évités. ``"Autre"`` reste à la fin pour saisie libre.

        Args:
            base_list : liste standard (ex: MICRO_MODELES)
            attr      : nom d'attribut Materiel à lire (ex: "modele", "micro_modele")
            attr2     : second attribut optionnel à considérer aussi (ex: "micro2_modele")
        """
        try:
            from materiels import load_materiels
            mats = load_materiels()
        except Exception:
            mats = []
        user_models: list[str] = []
        seen: set[str] = set()
        for m in mats:
            for a in (attr, attr2):
                if not a:
                    continue
                val = getattr(m, a, None)
                if val and val not in seen:
                    user_models.append(val)
                    seen.add(val)
        # Concatène : modèles utilisateur d'abord, puis standards pas déjà vus
        result = list(user_models)
        for v in base_list:
            if v not in seen:
                result.append(v)
                seen.add(v)
        return result

    def _on_det_change(self, value: str):
        """Affiche un champ libre quand 'Autre' est choisi pour le détecteur."""
        if value == "Autre":
            self.det_other_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        else:
            self.det_other_entry.grid_forget()

    def _on_mic0_change(self, value: str):
        """Affiche un champ libre quand 'Autre' est choisi pour le micro gauche."""
        if value == "Autre":
            self.mic0_other_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        else:
            self.mic0_other_entry.grid_forget()

    def _on_mic1_change(self, value: str):
        """Affiche un champ libre quand 'Autre' est choisi pour le micro droit."""
        if not self.stereo_var.get():
            return
        if value == "Autre":
            # Même row que le menu micro droit mais column=2 en suppl.
            self._mic1_other_entry.grid(row=100, column=2, sticky="ew", padx=8, pady=4)
        else:
            self._mic1_other_entry.grid_forget()

    def _on_stereo_toggle(self):
        """Affiche/masque les champs du micro droit."""
        if self.stereo_var.get():
            # Ajouter dynamiquement en fin de form
            form = self._mic1_label.master
            # On les insère juste avant la section Commentaire, en re-grid
            # Simplification : on fait un grid basique
            self._mic1_label.grid(row=100, column=0, sticky="w",
                                    padx=(16, 4), pady=4)
            self._mic1_menu.grid(row=100, column=1, sticky="w", padx=8, pady=4)
            self._mic1h_label.grid(row=101, column=0, sticky="w",
                                     padx=(16, 4), pady=4)
            self._mic1h_entry.grid(row=101, column=1, sticky="w", padx=8, pady=4)
        else:
            self._mic1_label.grid_remove()
            self._mic1_menu.grid_remove()
            self._mic1h_label.grid_remove()
            self._mic1h_entry.grid_remove()

    def _fill_defaults(self):
        pre = self._prefill

        def _ensure_dt(v):
            """Garantit qu'on a un datetime (parse string ISO si besoin)."""
            if v is None:
                return None
            if isinstance(v, str):
                from datetime import datetime as _dt
                try:
                    return _dt.fromisoformat(v)
                except ValueError:
                    return None
            return v

        # Dates : pre puis fallback meta.date_debut (toujours datetime ou None)
        date_format = "%Y-%m-%d %H:%M:%S" if pre.get("_dates_from_titley") else "%Y-%m-%d %H:%M"
        dt_deb = _ensure_dt(pre.get("date_debut")) or self.meta.date_debut
        if dt_deb is not None and not self.date_debut_var.get().strip():
            # Par convention : début = 19h, fin = 7h du lendemain (si rien d'autre)
            if dt_deb.hour == 0 and dt_deb.minute == 0 and not pre.get("_dates_from_titley"):
                dt_deb = dt_deb.replace(hour=19, minute=0)
            self.date_debut_var.set(dt_deb.strftime(date_format))

        dt_fin = _ensure_dt(pre.get("date_fin"))
        if dt_fin is None and dt_deb:
            dt_fin = (dt_deb + timedelta(hours=11)).replace(minute=0)
        if dt_fin and not self.date_fin_var.get().strip():
            self.date_fin_var.set(dt_fin.strftime(date_format))

        if pre.get("_dates_from_titley"):
            self._dates_hint.configure(text="T° / horaires lus dans le log Titley")

        if pre.get("_dates_from_wav"):
            try:
                self._dates_hint.configure(
                    text="⚠ Summary ≠ WAV (carte SD souvent non formatée : "
                         "l'ancienne nuit reste dans le Summary). Dates prises "
                         "sur les fichiers. Vérifiez les T° — elles peuvent "
                         "mélanger plusieurs nuits.",
                    text_color=("#b45309", "#fbbf24"),
                )
            except Exception:
                pass

        if "temperature_debut" in pre and not self.temp_deb_var.get().strip():
            self.temp_deb_var.set(str(pre["temperature_debut"]))
        if "temperature_fin" in pre and not self.temp_fin_var.get().strip():
            self.temp_fin_var.set(str(pre["temperature_fin"]))

        # Vent / couverture : appliquer si présents dans le manifest.
        # On stocke les CLÉS API (NUL/FAIBLE/MOYEN/FORT, 0-25, …) mais les
        # dropdowns affichent les LABELS lisibles. On retrouve donc le label
        # depuis la clé via les fonctions inverse-mapping de vigiechiro_enums.
        from vigiechiro_enums import VENT_VALUES, COUVERTURE_VALUES
        vent_key = pre.get("vent")
        if vent_key:
            for k, lbl in VENT_VALUES:
                if k == vent_key:
                    self.vent_label_var.set(lbl)
                    break
        cov_key = pre.get("couverture")
        if cov_key:
            for k, lbl in COUVERTURE_VALUES:
                if k == cov_key:
                    self.cov_label_var.set(lbl)
                    break

        # Hauteur micro 0 (string -> StringVar OK, mais on s'assure du format)
        if pre.get("micro0_hauteur") is not None:
            try:
                self.mic0_h_var.set(str(pre["micro0_hauteur"]))
            except Exception:
                pass

        # Commentaire si présent
        if pre.get("commentaire"):
            try:
                self.comment_txt.delete("1.0", "end")
                self.comment_txt.insert("1.0", str(pre["commentaire"]))
            except Exception:
                pass

        # Stéréo + micro droit si présent dans le manifest
        mic1 = pre.get("micro1_modele")
        if mic1:
            try:
                self.stereo_var.set(True)
                self._on_stereo_toggle()
                # Le micro droit est positionné dans le dropdown ou en "Autre"
                mic_choices = getattr(self, "_mic_values", None) \
                    or self._build_material_choices(
                        MICRO_MODELES, attr="micro_modele",
                        attr2="micro2_modele")
                if mic1 in mic_choices:
                    self.mic1_var.set(mic1)
                else:
                    self.mic1_var.set("Autre")
                    self.mic1_other_var.set(mic1)
                    self._on_mic1_change("Autre")
                if pre.get("micro1_hauteur") is not None:
                    self.mic1_h_var.set(str(pre["micro1_hauteur"]))
            except Exception:
                pass

        # Les dropdowns ont été enrichis avec les modèles du parc matériel.
        # Si le pré-rempli (venant d'un matériel ou de Feuil2) est dans la
        # liste étendue, on le sélectionne ; sinon on bascule sur "Autre".
        det_choices = self._build_material_choices(
            DETECTEUR_ENREGISTREUR_TYPES, attr="modele")
        mic_choices = getattr(self, "_mic_values", None) or \
            self._build_material_choices(
                MICRO_MODELES, attr="micro_modele", attr2="micro2_modele")

        det = pre.get("detecteur_enregistreur_type")
        if det and det in det_choices:
            self.det_var.set(det)
        elif det:
            self.det_var.set("Autre")
            self.det_other_var.set(det)
            self._on_det_change("Autre")
        else:
            self.det_var.set(_UNSET)   # rien de deviné → choix conscient requis

        mic0 = pre.get("micro0_modele")
        if mic0 and mic0 in mic_choices:
            self.mic0_var.set(mic0)
        elif mic0:
            self.mic0_var.set("Autre")
            self.mic0_other_var.set(mic0)
            self._on_mic0_change("Autre")
        else:
            self.mic0_var.set(_UNSET)   # rien de deviné → non renseigné

    # -- Validation ---------------------------------------------------------

    def _on_validate(self):
        self.err_lbl.configure(text="")
        errs: list[str] = []

        # Le log Titley porte les secondes ; le reste du wizard reste à la minute.
        def _parse_date(raw):
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(raw.strip(), fmt)
                except ValueError:
                    pass
            raise ValueError("date locale invalide")

        # Dates
        try:
            date_debut = _parse_date(self.date_debut_var.get())
        except ValueError:
            errs.append("date début invalide (format YYYY-MM-DD HH:MM)")
            date_debut = None
        try:
            date_fin = _parse_date(self.date_fin_var.get())
        except ValueError:
            errs.append("date fin invalide")
            date_fin = None

        if date_debut and date_fin and date_fin <= date_debut:
            errs.append("date fin doit être après date début")

        # Températures : optionnelles (souvent préremplies via Summary).
        # Champ vide = non renseigné (OK). Si saisi : entier -20..+50.
        def _parse_temp_optional(raw: str, label: str):
            s = (raw or "").strip()
            if not s:
                return None
            try:
                v = int(s)
            except ValueError:
                errs.append(f"{label} invalide (nombre entier attendu, ou laisser vide)")
                return None
            if v < -20 or v > 50:
                errs.append(f"{label} hors limites (-20 à +50 °C) : {v}")
                return None
            return v

        temp_deb = _parse_temp_optional(self.temp_deb_var.get(), "température début")
        temp_fin = _parse_temp_optional(self.temp_fin_var.get(), "température fin")
        temps_user_set = temperatures_are_user_set(
            self._prefill.get("_auto_temperature_debut"),
            self._prefill.get("_auto_temperature_fin"),
            temp_deb, temp_fin,
        )

        # Vent / couverture : optionnels. La sentinelle « — à renseigner — »
        # n'est PAS convertie en valeur inventée (from_label → None) et n'est
        # PAS bloquante — l'utilisateur peut compléter plus tard sur le portail.
        vent = vent_from_label(self.vent_label_var.get())
        couverture = couverture_from_label(self.cov_label_var.get())

        # Détecteur — si "Autre", on prend la valeur libre saisie
        detecteur = self.det_var.get().strip()
        if detecteur == "Autre":
            other = self.det_other_var.get().strip()
            if not other:
                errs.append("détecteur 'Autre' : précise le modèle dans le champ à côté")
            else:
                detecteur = other
        elif not detecteur or detecteur == _UNSET:
            errs.append("modèle de détecteur manquant (choisis dans la liste)")

        # Hauteur bornes : négatif possible (gîte) mais pas absurde
        def _parse_hauteur(raw: str, label: str):
            try:
                v = float(raw.replace(",", ".").strip())
            except ValueError:
                errs.append(f"{label} invalide (nombre attendu)")
                return None
            if v < -50 or v > 100:
                errs.append(f"{label} hors limites (-50 à +100 m) : {v}")
                return None
            return v

        # Micro gauche (optionnel) : sentinelle → non renseigné (pas de modèle
        # inventé), le champ matériel est libre côté serveur.
        mic0 = self.mic0_var.get().strip()
        if mic0 == _UNSET:
            mic0 = ""
        if mic0 == "Autre":
            other = self.mic0_other_var.get().strip()
            if not other:
                errs.append("micro gauche 'Autre' : précise le modèle")
            else:
                mic0 = other
        mic0_h = _parse_hauteur(self.mic0_h_var.get(), "hauteur micro gauche")

        # Micro droit (si stéréo)
        mic1 = None
        mic1_h = None
        if self.stereo_var.get():
            mic1 = self.mic1_var.get().strip()
            if mic1 == "Autre":
                other = self.mic1_other_var.get().strip()
                if not other:
                    errs.append("micro droit 'Autre' : précise le modèle")
                else:
                    mic1 = other
            mic1_h = _parse_hauteur(self.mic1_h_var.get(), "hauteur micro droit")

        commentaire = self.comment_txt.get("1.0", "end").strip() or None

        if errs:
            self.err_lbl.configure(text="⚠  " + "\n⚠  ".join(errs))
            return

        if self._prefill.get("_dates_from_wav"):
            from tkinter import messagebox
            if not messagebox.askyesno(
                "Summary et WAV différents",
                "Le Summary.txt ne correspond pas aux WAV de ce dossier "
                "(carte SD souvent non formatée entre deux nuits : "
                "l'ancienne pose reste dans le Summary).\n\n"
                "Les dates affichées viennent des fichiers WAV — ce sont "
                "eux qui font foi. Vérifiez aussi les températures, puis "
                "continuez ?",
                parent=self,
            ):
                return

        # Construction du payload — n'envoyer que les champs météo réellement
        # renseignés (pas de None / pas de fausses valeurs par défaut).
        meteo: dict = {}
        if temp_deb is not None:
            meteo["temperature_debut"] = temp_deb
        if temp_fin is not None:
            meteo["temperature_fin"] = temp_fin
        if vent is not None:
            meteo["vent"] = vent
        if couverture is not None:
            meteo["couverture"] = couverture

        configuration = build_participation_configuration(
            detecteur, self.meta.n_serie, mic0, mic0_h, mic1, mic1_h)

        self.result = {
            "date_debut": date_debut,
            "date_fin": date_fin,
            "point": self.meta.n_point_fixe,
            "meteo": meteo or None,
            "configuration": configuration,
            "commentaire": commentaire,
        }

        # Persist dans le manifest pour réutilisation future
        try:
            m = Manifest.load_or_create(self.session_path)
            serialisable = {
                "date_debut": date_debut.isoformat() if date_debut else None,
                "date_fin": date_fin.isoformat() if date_fin else None,
                "temperature_debut": temp_deb,
                "temperature_fin": temp_fin,
                "temperature_user_set": temps_user_set,
                "vent": vent,
                "couverture": couverture,
                "detecteur_enregistreur_type": detecteur,
                "detecteur_enregistreur_serie": self.meta.n_serie or None,
                "micro0_modele": mic0,
                "micro0_hauteur": str(mic0_h) if mic0_h is not None else None,
                "micro1_modele": mic1,
                "micro1_hauteur": str(mic1_h) if mic1_h is not None else None,
                "commentaire": commentaire,
            }
            m.set_meta(participation_payload=serialisable)
            m.save(self.session_path)
        except Exception:
            pass

        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


def open_participation_wizard(master, *, session_path: Path,
                                meta: SessionMeta) -> dict | None:
    """Helper : ouvre le wizard bloquant et renvoie le payload ou None."""
    w = ParticipationWizard(master, session_path=session_path, meta=meta)
    master.wait_window(w)
    return w.result
