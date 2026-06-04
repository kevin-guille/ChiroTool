"""
gui_participation_wizard.py — wizard de création d'une participation Vigie-Chiro.

Ouvert avant l'upload API pour collecter :
  - météo (températures début/fin obligatoirement **entières**,
    vent & couverture en enum stricts)
  - configuration matériel (détecteur, micro gauche, hauteur)
  - option stéréo (micro droit)
  - commentaire libre

Pré-remplissage :
  1. Summary.txt de la session (températures début/fin)
  2. Ligne du Suivi correspondante (modèle enregistreur / micro via Feuil2)
  3. Manifest existant (si l'utilisateur avait déjà saisi)

Retour : ``payload`` compatible ``VigieChiroClient.create_participation``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import customtkinter as ctk

from chiro_core import parse_summary_txt
from manifest import Manifest
from naming import SessionMeta
from vigiechiro_enums import (
    COUVERTURE_VALUES, DETECTEUR_ENREGISTREUR_TYPES, MICRO_MODELES, VENT_VALUES,
    couverture_from_label, couverture_labels, vent_from_label, vent_labels,
)


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

        self.transient(master)
        self.after(50, self.grab_set)
        self.focus()

        # Données pré-remplies (best-effort)
        self._prefill = self._collect_prefill()

        self._build_ui()
        self._fill_defaults()

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # -- Pré-remplissage ---------------------------------------------------

    def _collect_prefill(self) -> dict:
        """Agrège les valeurs pré-remplies depuis Summary.txt + Suivi + manifest."""
        pre: dict = {}

        # 1. Summary.txt → temperatures, dates, GPS
        for child in self.session_path.iterdir():
            if (child.is_file() and
                child.name.lower().endswith("_summary.txt")):
                s = parse_summary_txt(child)
                if s:
                    if s.start_dt:
                        pre["date_debut"] = s.start_dt
                    if s.end_dt:
                        pre["date_fin"] = s.end_dt
                    if s.temp_start is not None:
                        pre["temperature_debut"] = int(round(s.temp_start))
                    if s.temp_end is not None:
                        pre["temperature_fin"] = int(round(s.temp_end))
                break

        # 2. Parc matériel local (Préférences → Mes matériels) PRIORITAIRE.
        # C'est la source canonique : modèle + micro à jour, pas dépendant
        # d'un Suivi Excel qui peut être obsolète ou inaccessible.
        used_materiels = False
        try:
            from materiels import find_by_id, load_materiels
            if self.meta.n_enregistreur is not None:
                m = find_by_id(load_materiels(), self.meta.n_enregistreur)
                if m is not None and not m.is_empty():
                    used_materiels = True
                    if m.modele:
                        pre["detecteur_enregistreur_type"] = m.modele
                    if m.micro_modele:
                        pre["micro0_modele"] = m.micro_modele
                    if m.hauteur_m is not None:
                        pre["micro0_hauteur"] = str(m.hauteur_m)
                    if m.stereo and m.micro2_modele:
                        pre["stereo"] = True
                        pre["micro1_modele"] = m.micro2_modele
        except Exception:
            pass

        # 2bis. Fallback Feuil2 Suivi Excel si pas trouvé dans Mes matériels.
        if not used_materiels:
            try:
                from suivi import Suivi, _default_path
                path = _default_path(
                    self.meta.date_debut.year if self.meta.date_debut else None)
                if path and path.is_file() and self.meta.n_enregistreur is not None:
                    suivi = Suivi(path)
                    e = suivi.enregistreur(self.meta.n_enregistreur)
                    if e:
                        if e.modele:
                            pre["detecteur_enregistreur_type"] = e.modele
                        # Heuristique : modèle micro depuis le numéro série micro
                        if e.serie_micro:
                            serie = str(e.serie_micro).strip()
                            pre["micro0_modele"] = self._guess_micro_model(
                                e.modele or "", serie)
            except Exception:
                pass

        # 3. Manifest existant (si l'utilisateur avait déjà saisi).
        # IMPORTANT : le manifest stocke `date_debut`/`date_fin` en strings
        # ISO (JSON ne supporte pas datetime). On les reparse en datetime ici
        # sinon `_fill_defaults` tombe en AttributeError silencieux quand il
        # fait `dt.hour` → wizard apparaît vide (bug rapporté par testeur).
        m = Manifest.load(self.session_path)
        if m and m.meta:
            part_cached = m.meta.get("participation_payload") or {}
            if isinstance(part_cached, dict):
                from datetime import datetime as _dt
                for k, v in part_cached.items():
                    if v is None:
                        continue
                    if k in ("date_debut", "date_fin") and isinstance(v, str):
                        try:
                            v = _dt.fromisoformat(v)
                        except ValueError:
                            continue
                    pre[k] = v

        return pre

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

        # --- Section météo ---
        row = self._section(form, row, "Conditions météo")

        self._label(form, row, "Température début (°C) *",
                      help="Valeur entière")
        self.temp_deb_var = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self.temp_deb_var, width=120,
                       placeholder_text="ex: 22",
                       ).grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        self._label(form, row, "Température fin (°C) *",
                      help="Valeur entière")
        self.temp_fin_var = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self.temp_fin_var, width=120,
                       placeholder_text="ex: 15",
                       ).grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        self._label(form, row, "Vent")
        self.vent_label_var = ctk.StringVar(value=vent_labels()[0])
        ctk.CTkOptionMenu(
            form, variable=self.vent_label_var, values=vent_labels(),
            width=160,
        ).grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

        self._label(form, row, "Couverture nuageuse")
        self.cov_label_var = ctk.StringVar(value=couverture_labels()[0])
        ctk.CTkOptionMenu(
            form, variable=self.cov_label_var, values=couverture_labels(),
            width=160,
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
            det_frame, variable=self.det_var, values=det_values,
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
            mic0_frame, variable=self.mic0_var, values=mic_values,
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

        ctk.CTkButton(
            footer, text="Valider", width=140, height=34,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_validate,
        ).grid(row=0, column=2)

    def _section(self, form, row: int, title: str) -> int:
        ctk.CTkLabel(
            form, text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=row, column=0, columnspan=2, sticky="ew",
               padx=16, pady=(16, 6))
        return row + 1

    def _label(self, form, row: int, text: str, *, help: str = ""):
        ctk.CTkLabel(
            form, text=text, width=220, anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=row, column=0, sticky="nw", padx=(16, 4), pady=(4, 0))
        if help:
            ctk.CTkLabel(
                form, text=help, width=220, anchor="w",
                font=ctk.CTkFont(size=10),
                text_color=("gray50", "gray60"),
            ).grid(row=row, column=0, sticky="sw", padx=(16, 4))

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
        dt_deb = _ensure_dt(pre.get("date_debut")) or self.meta.date_debut
        if dt_deb is not None:
            # Par convention : début = 19h, fin = 7h du lendemain (si rien d'autre)
            if dt_deb.hour == 0 and dt_deb.minute == 0:
                dt_deb = dt_deb.replace(hour=19, minute=0)
            self.date_debut_var.set(dt_deb.strftime("%Y-%m-%d %H:%M"))

        dt_fin = _ensure_dt(pre.get("date_fin"))
        if dt_fin is None and dt_deb:
            dt_fin = (dt_deb + timedelta(hours=11)).replace(minute=0)
        if dt_fin:
            self.date_fin_var.set(dt_fin.strftime("%Y-%m-%d %H:%M"))

        if "temperature_debut" in pre:
            self.temp_deb_var.set(str(pre["temperature_debut"]))
        if "temperature_fin" in pre:
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
            self.det_var.set(det_choices[0])

        mic0 = pre.get("micro0_modele")
        if mic0 and mic0 in mic_choices:
            self.mic0_var.set(mic0)
        elif mic0:
            self.mic0_var.set("Autre")
            self.mic0_other_var.set(mic0)
            self._on_mic0_change("Autre")
        else:
            self.mic0_var.set(mic_choices[0])

    # -- Validation ---------------------------------------------------------

    def _on_validate(self):
        self.err_lbl.configure(text="")
        errs: list[str] = []

        # Dates
        try:
            date_debut = datetime.strptime(
                self.date_debut_var.get().strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            errs.append("date début invalide (format YYYY-MM-DD HH:MM)")
            date_debut = None
        try:
            date_fin = datetime.strptime(
                self.date_fin_var.get().strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            errs.append("date fin invalide")
            date_fin = None

        if date_debut and date_fin and date_fin <= date_debut:
            errs.append("date fin doit être après date début")

        # Températures (entier obligatoire, bornes -20..+50 °C)
        def _parse_temp(raw: str, label: str):
            try:
                v = int(raw.strip())
            except ValueError:
                errs.append(f"{label} invalide (nombre entier attendu)")
                return None
            if v < -20 or v > 50:
                errs.append(f"{label} hors limites (-20 à +50 °C) : {v}")
                return None
            return v

        temp_deb = _parse_temp(self.temp_deb_var.get(), "température début")
        temp_fin = _parse_temp(self.temp_fin_var.get(), "température fin")

        # Vent / couverture
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
        elif not detecteur:
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

        # Micro gauche
        mic0 = self.mic0_var.get().strip()
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

        # Construction du payload
        meteo = {
            "temperature_debut": temp_deb,
            "temperature_fin": temp_fin,
            "vent": vent,
            "couverture": couverture,
        }
        configuration = {
            "detecteur_enregistreur_type": detecteur,
        }
        if mic0:
            configuration["micro0_modele"] = mic0
        if mic0_h is not None:
            configuration["micro0_hauteur"] = str(mic0_h)
        if mic1:
            configuration["micro1_modele"] = mic1
        if mic1_h is not None:
            configuration["micro1_hauteur"] = str(mic1_h)

        self.result = {
            "date_debut": date_debut,
            "date_fin": date_fin,
            "point": self.meta.n_point_fixe,
            "meteo": meteo,
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
                "vent": vent,
                "couverture": couverture,
                "detecteur_enregistreur_type": detecteur,
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
