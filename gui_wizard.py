"""
gui_wizard.py — Wizard "métadonnées session" (CTkToplevel modale).

Permet à l'utilisateur de saisir/corriger les métadonnées d'une session quand
l'auto-résolution échoue ou qu'il souhaite écraser ce qu'elle a trouvé.

Les champs :
  - Contrat (avec autocomplétion depuis le Suivi)
  - Date de début (YYYY-MM-DD)
  - N° site Tadarida (6 chiffres)
  - Point (ex Z3)
  - Passage (1 à 9)
  - N° enregistreur (1 à 27) — auto-remplit Série + Micro depuis Feuil2
  - Série (auto-rempli, modifiable)

Validation via naming.validate_meta() avant OK.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from naming import SessionMeta, validate_meta


def _load_suivi_safe():
    """Charge le Suivi 2026 (ou le plus récent). Retourne None si échec."""
    try:
        from suivi import Suivi, _default_path
        path = _default_path()
        if path and Path(path).is_file():
            return Suivi(path)
    except Exception:
        pass
    return None


class SessionMetaWizard(ctk.CTkToplevel):
    """Wizard modal. Appeler ``get()`` après ``wait_window()`` pour récupérer
    la ``SessionMeta`` (ou None si annulé)."""

    def __init__(self, master, *, prefill: SessionMeta | None = None,
                 session_name: str | None = None,
                 session_path: Path | None = None):
        super().__init__(master)
        self.title("Métadonnées de la session")
        self.geometry("640x600")
        self.minsize(580, 540)

        self.transient(master)
        self.after(50, self.grab_set)
        self.focus()

        self._result: SessionMeta | None = None
        self.suivi = _load_suivi_safe()
        self.session_name = session_name or "(session)"
        self.session_path = Path(session_path) if session_path else None

        self._build_ui()
        if prefill:
            self._fill_from(prefill)
        # Continuité carte → meta : préremplit site/point si absents du guess
        self._apply_active_point_prefill(prefill)
        self._apply_summary_wav_hint()

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._load_recent_points_async()

    # -- UI -----------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        title = ctk.CTkLabel(self, text="Métadonnées de la session",
                              font=ctk.CTkFont(size=16, weight="bold"),
                              anchor="w")
        title.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))

        sub = ctk.CTkLabel(self, text=self.session_name,
                            font=ctk.CTkFont(size=11),
                            text_color=("gray40", "gray70"), anchor="w")
        sub.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Zone formulaire
        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.grid(row=2, column=0, sticky="nsew", padx=12, pady=0)
        form.grid_columnconfigure(1, weight=1)

        # Récupère les contrats / sites déjà saisis (mémoire d'app + Suivi si présent)
        self._known_contrats = self._collect_known_contrats()
        self._known_sites = self._collect_known_sites()

        # --- Points récents : compte VC + point actif carte + sites externes ---
        # Le point actif (create/reuse sur la carte) comble le trou « autre obs ».
        self._recent_points: list[dict] = []
        self._recent_label_map: dict[str, dict] = {}
        rp = ctk.CTkFrame(form, fg_color=("#eef5ff", "#16263d"), corner_radius=8)
        rp.grid(row=0, column=0, columnspan=2, sticky="ew", padx=2, pady=(0, 10))
        rp.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            rp, text="⭐  Points récents (compte + dernier choix carte)",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        self._recent_menu = ctk.CTkOptionMenu(
            rp, values=["Chargement…"], command=self._on_pick_recent_point,
            dynamic_resizing=False)
        self._recent_menu.set("Chargement…")
        self._recent_menu.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 2))
        ctk.CTkButton(
            rp, text="🗺️  Choisir sur la carte…", height=30,
            fg_color=("#3b8ed0", "#1f6aa5"),
            command=self._on_pick_on_map,
        ).grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 2))
        ctk.CTkLabel(
            rp, text="Sélectionne un point récent, ou ouvre la carte "
                     "(commune · 5 km · create/reuse) → remplit carré + point. "
                     "★ = dernier choix carte ; « autre obs. » = site partagé.",
            font=ctk.CTkFont(size=10), text_color=("gray40", "gray70"),
            anchor="w", justify="left", wraplength=520,
        ).grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

        # PointSelection retenu (lat/lon pour le manifest D8)
        self._picked_selection = None

        row = 1   # le formulaire commence après le bandeau « Points récents »
        # --- Contrat ---
        self._add_field_label(form, row, "Contrat",
                               help="Nom du projet / client / campagne")
        self.contrat_var = ctk.StringVar()
        contrat_frame = ctk.CTkFrame(form, fg_color="transparent")
        contrat_frame.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        contrat_frame.grid_columnconfigure(0, weight=1)
        self.contrat_entry = ctk.CTkEntry(
            contrat_frame, textvariable=self.contrat_var,
            placeholder_text="ex : MonContrat",
        )
        self.contrat_entry.grid(row=0, column=0, sticky="ew")
        # Bouton ▾ qui propose la liste des contrats déjà connus (depuis le
        # registre, Suivi ou settings.recent_contracts). Remplace l'ancien
        # OptionMenu "— choisir —" qui apparaissait seulement si Suivi chargé.
        if self._known_contrats:
            ctk.CTkButton(
                contrat_frame, text="▾", width=30, height=28,
                fg_color=("gray85", "gray25"),
                text_color=("gray15", "gray90"),
                hover_color=("gray75", "gray35"),
                command=lambda: self._pick_from(
                    self._known_contrats, self.contrat_var, "Contrat connu"),
            ).grid(row=0, column=1, padx=(4, 0))
        row += 1

        # --- Date début ---
        self._add_field_label(form, row, "Date début",
                               help="Jour de pose (format YYYY-MM-DD)")
        date_frame = ctk.CTkFrame(form, fg_color="transparent")
        date_frame.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        date_frame.grid_columnconfigure(0, weight=1)
        self.date_var = ctk.StringVar()
        self.date_entry = ctk.CTkEntry(
            date_frame, textvariable=self.date_var,
            placeholder_text="YYYY-MM-DD",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.date_entry.grid(row=0, column=0, sticky="ew")
        # Bouton 📅 qui ouvre un mini date picker custom
        ctk.CTkButton(
            date_frame, text="📅", width=36, height=28,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._open_date_picker,
        ).grid(row=0, column=1, padx=(4, 0))
        row += 1

        self._date_hint = ctk.CTkLabel(
            form, text="",
            font=ctk.CTkFont(size=10),
            text_color=("#b45309", "#fbbf24"),
            anchor="w", justify="left", wraplength=400,
        )
        self._date_hint.grid(row=row, column=0, columnspan=2,
                             sticky="ew", padx=16, pady=(0, 4))
        row += 1

        # --- Site Tadarida ---
        self._add_field_label(form, row, "N° site Tadarida",
                               help="6 chiffres (zéro-paddé si dép. 1→9)")
        site_frame = ctk.CTkFrame(form, fg_color="transparent")
        site_frame.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        site_frame.grid_columnconfigure(0, weight=1)
        self.site_var = ctk.StringVar()
        self.site_entry = ctk.CTkEntry(
            site_frame, textvariable=self.site_var,
            placeholder_text="ex: 212097",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.site_entry.grid(row=0, column=0, sticky="ew")
        if self._known_sites:
            ctk.CTkButton(
                site_frame, text="▾", width=30, height=28,
                fg_color=("gray85", "gray25"),
                text_color=("gray15", "gray90"),
                hover_color=("gray75", "gray35"),
                command=lambda: self._pick_from(
                    self._known_sites, self.site_var, "Site connu"),
            ).grid(row=0, column=1, padx=(4, 0))
        row += 1

        # --- Point ---
        self._add_field_label(form, row, "Point",
                               help="Code lettre+chiffre (Z3, A1, C2, …)")
        self.point_var = ctk.StringVar()
        self.point_entry = ctk.CTkEntry(form, textvariable=self.point_var,
                                          placeholder_text="ex: Z3")
        self.point_entry.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        row += 1

        # --- Passage ---
        self._add_field_label(form, row, "Passage",
                               help="Numéro de passage dans l'année (1, 2, 3…)")
        self.pass_var = ctk.StringVar(value="1")
        pass_frame = ctk.CTkFrame(form, fg_color="transparent")
        pass_frame.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        ctk.CTkOptionMenu(pass_frame, variable=self.pass_var, width=80,
                           values=[str(i) for i in range(1, 10)]
                           ).pack(side="left")
        row += 1

        # --- Enregistreur ---
        self._add_field_label(form, row, "N° enregistreur",
                               help="Enregistreurs saisis dans Préférences → Mes matériels")

        enr_frame = ctk.CTkFrame(form, fg_color="transparent")
        enr_frame.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        enr_frame.grid_columnconfigure(2, weight=1)

        # Dropdown dynamique : d'abord les matériels enregistrés (Préférences
        # → Mes matériels), puis un fallback 1..27 pour les n° "génériques"
        # si le parc n'est pas encore saisi. "Autre" pour n° hors parc.
        self._enr_label_to_id: dict[str, int] = {}
        enr_choices = self._build_enr_choices()
        self.enr_var = ctk.StringVar(value="")
        self.enr_menu = ctk.CTkOptionMenu(
            enr_frame, variable=self.enr_var, values=enr_choices,
            width=280, command=self._on_enr_menu_change,
            dynamic_resizing=False,
        )
        self.enr_menu.grid(row=0, column=0, sticky="w")

        # Entry libre visible uniquement quand "Autre" sélectionné
        self.enr_other_var = ctk.StringVar()
        self.enr_other_entry = ctk.CTkEntry(
            enr_frame, textvariable=self.enr_other_var,
            width=80, placeholder_text="n°",
        )
        # pas de grid() : affiché par _on_enr_menu_change si "Autre"

        self.enr_info_lbl = ctk.CTkLabel(enr_frame, text="",
                                           font=ctk.CTkFont(size=11),
                                           text_color=("gray40", "gray70"),
                                           anchor="w")
        self.enr_info_lbl.grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.enr_var.trace_add("write", self._on_enr_change)
        row += 1

        # --- Série ---
        # Note : ce bloc était précédemment dead code (placé par erreur après
        # un `return` dans une méthode helper, suite à un refactoring).
        # Conséquence : le wizard plantait silencieusement à la validation
        # avec AttributeError sur self.serie_var. Restauré ici dans _build_ui.
        self._add_field_label(form, row, "N° série enregistreur",
                               help="Auto-rempli depuis Mes matériels — modifiable")
        self.serie_var = ctk.StringVar()
        self.serie_entry = ctk.CTkEntry(form, textvariable=self.serie_var,
                                          placeholder_text="ex: SMU03126",
                                          font=ctk.CTkFont(family="Consolas", size=12))
        self.serie_entry.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        row += 1

        # Footer : erreurs éventuelles + boutons (Annuler / Valider)
        self.err_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=11),
            text_color=("#cf222e", "#f85149"),
            anchor="w", justify="left", wraplength=600,
        )
        self.err_lbl.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 14))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            footer, text="Annuler", width=120, height=34,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_cancel,
        ).grid(row=0, column=1, padx=(0, 6))

        # Bouton "🔄 Re-deviner" : relance try_auto_meta sur les WAV présents
        # (utile si l'utilisateur a renommé/déplacé depuis le dernier scan)
        ctk.CTkButton(
            footer, text="🔄 Re-deviner", width=130, height=34,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_redetect,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            footer, text="Valider", width=140, height=34,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_validate,
        ).grid(row=0, column=2)

        # Raccourcis clavier : Entrée = Valider, Échap = Annuler
        self.bind("<Return>", lambda _e: self._on_validate())
        self.bind("<Escape>", lambda _e: self._on_cancel())

        # Auto-focus sur le 1er champ vide (ergonomie : on enchaîne au clavier)
        self.after(120, self._focus_first_empty)

    def _focus_first_empty(self):
        """Place le focus sur le 1er champ vide pour démarrer la saisie."""
        try:
            for var, widget in (
                (self.contrat_var, self.contrat_entry),
                (self.date_var, self.date_entry),
                (self.site_var, self.site_entry),
                (self.point_var, self.point_entry),
                (self.serie_var, self.serie_entry),
            ):
                if not (var.get() or "").strip():
                    widget.focus_set()
                    return
        except Exception:
            pass

    def _on_redetect(self):
        """Relance try_auto_meta sur les WAV présents (pour rattraper un
        renommage/déplacement entre l'ouverture du wizard et maintenant)."""
        # session_path n'est pas exposé directement au wizard ; on utilise
        # le session_name + workspace courant pour reconstruire le chemin.
        # En pratique cette feature est best-effort : si on ne trouve pas le
        # dossier, on ne fait rien plutôt que de planter.
        try:
            from gui_config import load_settings
            from rename import try_auto_meta
            ws = load_settings().last_workspace
            if not ws or not self.session_name:
                self.err_lbl.configure(
                    text="Re-deviner indisponible (workspace inconnu).")
                return
            from pathlib import Path as _P
            # Cherche le dossier session : on parcourt 2 niveaux pour trouver
            # un dossier portant exactement ce nom
            candidates = list(_P(ws).rglob(self.session_name))
            target = next((p for p in candidates if p.is_dir()), None)
            if target is None:
                self.err_lbl.configure(
                    text=f"Dossier '{self.session_name}' introuvable dans le workspace.")
                return
            auto, msgs = try_auto_meta(target)
            if auto is None:
                detail = "  ·  ".join(msgs[:3]) if msgs else "raison inconnue"
                self.err_lbl.configure(
                    text=f"Auto-résolution échouée : {detail}")
                return
            self._fill_from(auto)
            if not auto.n_site_tadarida:
                self.err_lbl.configure(
                    text="✓ Série et date détectées — complète le n° de carré "
                         "et le point (liste ou points récents).",
                    text_color=("#bf8700", "#d29922"))
            else:
                self.err_lbl.configure(
                    text="✓ Champs re-remplis depuis l'auto-résolution",
                    text_color=("#2ea043", "#3fb950"))
        except Exception as e:
            self.err_lbl.configure(
                text=f"Re-deviner : erreur ({e})")

    # -- Points récents (compte Vigie-Chiro) --------------------------------

    def _safe_widget(self, w) -> bool:
        try:
            return bool(w) and w.winfo_exists()
        except Exception:
            return False

    def _apply_active_point_prefill(self, prefill: SessionMeta | None) -> None:
        """Préremplit site/point depuis active_point si le guess est incomplet."""
        try:
            from gui_map import load_active_point, should_prefill_from_active
            from point_selection import point_selection_from_active
            ap = load_active_point()
        except Exception:
            return
        pre_site = (prefill.n_site_tadarida if prefill else None) or ""
        pre_point = (prefill.n_point_fixe if prefill else None) or ""
        # Respecte aussi ce qui aurait déjà été mis par _fill_from
        cur_site = self.site_var.get().strip() if hasattr(self, "site_var") else ""
        cur_point = self.point_var.get().strip() if hasattr(self, "point_var") else ""
        site_for_decision = cur_site or pre_site
        point_for_decision = cur_point or pre_point
        if not should_prefill_from_active(site_for_decision, point_for_decision, ap):
            return
        assert ap is not None
        if not cur_site and ap.get("numero"):
            self.site_var.set(str(ap["numero"]))
        if not cur_point and ap.get("point"):
            self.point_var.set(str(ap["point"]))
        # GPS pour le manifest (D8) même sans clic « récent » explicite
        try:
            ps = point_selection_from_active(ap)
            if ps and ps.has_coords():
                self._picked_selection = ps
        except Exception:
            pass
        try:
            tag = "autre obs." if not ap.get("is_mine", True) else "carte"
            self.err_lbl.configure(
                text=(f"✓ Point actif ({tag}) : carré {ap.get('numero')} · "
                      f"{ap.get('point')} — vérifie le passage."),
                text_color=("#2ea043", "#3fb950"))
        except Exception:
            pass

    def _load_recent_points_async(self):
        """Charge points du compte + externes mémorisés + point actif."""
        try:
            from credentials import load_token
            token = load_token()
        except Exception:
            token = None

        # Même sans token : afficher au moins le point actif local
        if not token:
            try:
                from gui_map import load_active_point, merge_recent_points
                ap = load_active_point()
                pts = merge_recent_points([], [], ap)
            except Exception:
                pts = []
            if pts:
                self._on_recent_loaded(pts)
            else:
                self._set_recent_menu(
                    ["(token API requis — ou choisis un point sur la carte)"])
            return

        def _worker():
            mine: list[dict] = []
            external: list[dict] = []
            active = None
            try:
                from vigiechiro_api import VigieChiroClient
                from gui_map import (
                    load_active_point, merge_recent_points,
                    _load_external_site_ids, _points_from_raw,
                )
                client = VigieChiroClient(token)
                try:
                    mine = client.list_my_recent_points(limit=15) or []
                    for p in mine:
                        p.setdefault("is_mine", True)
                except Exception:
                    mine = []

                # Sites d'autres obs. mémorisés (create/reuse sur leur carré)
                for ext_id in (_load_external_site_ids() or [])[:10]:
                    try:
                        raw = client.get_site_raw(ext_id)
                    except Exception:
                        continue
                    if not raw:
                        continue
                    import re
                    titre = raw.get("titre") or ""
                    m = re.search(r"-(\d{5,6})\s*$", titre)
                    numero = m.group(1).zfill(6) if m else ""
                    updated = raw.get("_updated") or ""
                    for pt in _points_from_raw(raw):
                        external.append({
                            "numero": numero,
                            "site_id": raw.get("_id") or ext_id,
                            "point": pt.get("nom"),
                            "lat": pt.get("lat"),
                            "lon": pt.get("lon"),
                            "updated": updated,
                            "is_mine": False,
                        })

                active = load_active_point()
                pts = merge_recent_points(mine, external, active)
            except Exception:
                pts = None
            self.after(0, lambda: self._on_recent_loaded(pts))
            if pts:                       # communes en tâche de fond (1 req/s)
                try:
                    from gui_map import reverse_commune
                except Exception:
                    return
                for p in pts:
                    if p.get("lat") is None:
                        continue
                    com = reverse_commune(p["lat"], p["lon"])
                    if com:
                        p["commune"] = com
                        self.after(0, self._refresh_recent_labels)

        threading.Thread(target=_worker, daemon=True).start()

    def _label_for_recent(self, p: dict) -> str:
        """Libellé humain d'abord (commune · Zx · carré) — SPEC D6."""
        try:
            from point_selection import format_point_label
            base = format_point_label(
                str(p.get("numero") or ""),
                str(p.get("point") or ""),
                commune=p.get("commune"),
                provenance=(
                    "other" if p.get("is_mine") is False
                    else ("created" if p.get("is_active") and p.get("source") == "create"
                          else "mine")
                ),
            )
        except Exception:
            base = f"{p.get('numero') or '?'} · {p.get('point') or '?'}"
            if p.get("commune"):
                base = f"{p['commune']} · {base}"
        if p.get("is_active"):
            base = f"★ {base} · dernier choix carte"
        upd = (p.get("updated") or "")[:10]
        return f"{base}   ({upd})" if upd else base

    def _set_recent_menu(self, values):
        if not self._safe_widget(self._recent_menu):
            return
        try:
            self._recent_menu.configure(values=values)
            self._recent_menu.set(values[0])
        except Exception:
            pass

    def _on_recent_loaded(self, pts):
        if not pts:
            self._set_recent_menu(["(aucun point — crée-en un sur la carte)"])
            return
        self._recent_points = pts
        self._refresh_recent_labels()

    def _refresh_recent_labels(self):
        if not self._safe_widget(self._recent_menu):
            return
        self._recent_label_map = {}
        values = ["— choisir un point récent —"]
        for p in self._recent_points:
            label = self._label_for_recent(p)
            self._recent_label_map[label] = p
            values.append(label)
        try:
            cur = self._recent_menu.get()
            self._recent_menu.configure(values=values)
            # Si un point actif est en tête, le présélectionner pour le voir
            active_label = next(
                (self._label_for_recent(p) for p in self._recent_points
                 if p.get("is_active")),
                None,
            )
            if cur not in values:
                self._recent_menu.set(active_label or values[0])
        except Exception:
            pass

    def _on_pick_on_map(self):
        """Mode PICK carte (SPEC P2) : masque le wizard, retourne un PointSelection."""
        app = self.winfo_toplevel()
        map_panel = getattr(app, "map_panel", None)
        if map_panel is None:
            messagebox.showinfo(
                "Carte",
                "Onglet Carte indisponible. Utilise les points récents "
                "ou la saisie manuelle.",
                parent=self)
            return

        def _on_result(selection):
            try:
                self.deiconify()
                self.lift()
                self.grab_set()
                self.focus()
            except Exception:
                pass
            self._apply_point_selection(selection)

        def _on_cancel():
            try:
                self.deiconify()
                self.lift()
                self.grab_set()
                self.focus()
            except Exception:
                pass
            try:
                self.err_lbl.configure(
                    text="Choix carte annulé — saisie manuelle ou points récents.",
                    text_color=("gray40", "gray70"))
            except Exception:
                pass

        try:
            self.grab_release()
        except Exception:
            pass
        self.withdraw()
        try:
            # Bascule onglet Carte si l'app le permet
            tabs = getattr(app, "detail_tabs", None)
            if tabs is not None:
                tabs.set("Carte")
        except Exception:
            pass
        try:
            map_panel.enter_pick_mode(_on_result, _on_cancel)
            map_panel.load_sites_async()
        except Exception as e:
            _on_cancel()
            messagebox.showerror("Carte", f"Mode pick impossible :\n{e}", parent=self)

    def _apply_point_selection(self, selection) -> None:
        """Applique un PointSelection aux champs + mémorise pour le manifest."""
        from point_selection import PointSelection
        if not isinstance(selection, PointSelection):
            return
        self._picked_selection = selection
        if selection.site_numero:
            self.site_var.set(selection.site_numero)
        if selection.point_code:
            self.point_var.set(selection.point_code)
        try:
            self.err_lbl.configure(
                text=f"✓ {selection.label_humain}",
                text_color=("#2ea043", "#3fb950"))
        except Exception:
            pass

    def get_point_selection(self):
        """PointSelection retenu (pick / récent avec coords), ou None."""
        return getattr(self, "_picked_selection", None)

    def _on_pick_recent_point(self, label: str):
        p = self._recent_label_map.get(label)
        if not p:
            return
        if p.get("numero"):
            self.site_var.set(str(p["numero"]))
        if p.get("point"):
            self.point_var.set(str(p["point"]))
        # Construit PointSelection si coords connues
        try:
            from point_selection import PointSelection
            if p.get("lat") is not None and p.get("lon") is not None:
                self._picked_selection = PointSelection(
                    site_numero=str(p.get("numero") or ""),
                    point_code=str(p.get("point") or ""),
                    lat=float(p["lat"]), lon=float(p["lon"]),
                    site_id=str(p.get("site_id") or ""),
                    provenance="other" if p.get("is_mine") is False else "mine",
                    commune=p.get("commune"),
                )
        except Exception:
            pass
        # Mémorise le choix explicite comme point actif (prochaine session)
        try:
            from gui_map import save_active_point
            save_active_point(
                site_id=p.get("site_id") or "",
                numero=p.get("numero"),
                point=p.get("point") or "",
                lat=p.get("lat"), lon=p.get("lon"),
                is_mine=bool(p.get("is_mine", True)),
                source="reuse",
            )
        except Exception:
            pass
        try:
            origin = (
                "dernier choix carte" if p.get("is_active")
                else ("autre observateur" if p.get("is_mine") is False
                      else "ton compte")
            )
            self.err_lbl.configure(
                text=f"✓ Carré {p.get('numero')} · point {p.get('point')} "
                     f"({origin}) — renseigne le passage.",
                text_color=("#2ea043", "#3fb950"))
        except Exception:
            pass

    def _build_enr_choices(self) -> list[str]:
        """Construit la liste des options du dropdown enregistreur.

        Format : "#7 · SM4BAT FS (S4U04784)" pour les matériels saisis,
        suivis de "#N°" purs pour les numéros 1..27 non saisis, puis "Autre".
        Le mapping label → id est mémorisé dans ``self._enr_label_to_id``.
        """
        self._enr_label_to_id = {}
        choices: list[str] = []
        try:
            from materiels import load_materiels
            mats = load_materiels()
        except Exception:
            mats = []
        used_ids = set()
        for m in mats:
            if m.is_empty():
                continue
            lbl = m.label()  # "#7 SM4BAT FS (S4U04784)"
            choices.append(lbl)
            self._enr_label_to_id[lbl] = m.id
            used_ids.add(m.id)
        # Compléter avec les numéros 1..27 non utilisés (fallback historique)
        for i in range(1, 28):
            if i not in used_ids:
                lbl = f"#{i}"
                choices.append(lbl)
                self._enr_label_to_id[lbl] = i
        choices.append("Autre")
        return choices

    def _extract_enr_id(self, choice: str) -> int | None:
        """Extrait le numéro d'enregistreur depuis un label du dropdown."""
        if choice == "Autre":
            return None
        return self._enr_label_to_id.get(choice)

    # -- Sources auxiliaires de saisie (autocomplétion / picker) -----------

    def _collect_known_contrats(self) -> list[str]:
        """Liste des contrats connus, ordonnée par fréquence d'usage.

        Sources combinées :
          1. settings.recent_contracts (saisies précédentes dans l'app)
          2. Registre SQLite (workspace courant)
          3. Feuil2 du Suivi Excel s'il est chargé
        """
        seen: set[str] = set()
        out: list[str] = []

        def _add(name: str | None):
            if not name:
                return
            n = name.strip()
            if not n or n in seen:
                return
            seen.add(n)
            out.append(n)

        # 1. settings.recent_contracts
        try:
            from gui_config import load_settings
            s = load_settings()
            for c in getattr(s, "recent_contracts", None) or []:
                _add(c)
        except Exception:
            pass
        # 2. Registre du workspace
        try:
            from gui_config import load_settings
            from pathlib import Path as _P
            from registry import Registry
            ws = (load_settings().last_workspace or "").strip()
            if ws and _P(ws).is_dir():
                reg = Registry(_P(ws))
                try:
                    for row in reg.list_sessions():
                        _add(row.get("nom_contrat"))
                finally:
                    reg.close()
        except Exception:
            pass
        # 3. Suivi Excel (fallback historique)
        try:
            if self.suivi:
                for c in self.suivi.contrats() or []:
                    _add(c)
        except Exception:
            pass
        return out

    def _collect_known_sites(self) -> list[str]:
        """Liste des n° de site connus (registre + Suivi)."""
        seen: set[str] = set()
        out: list[str] = []
        try:
            from gui_config import load_settings
            from pathlib import Path as _P
            from registry import Registry
            ws = (load_settings().last_workspace or "").strip()
            if ws and _P(ws).is_dir():
                reg = Registry(_P(ws))
                try:
                    for row in reg.list_sessions():
                        n = row.get("n_site_tadarida")
                        if n and str(n).isdigit() and n not in seen:
                            seen.add(n)
                            out.append(n)
                finally:
                    reg.close()
        except Exception:
            pass
        try:
            if self.suivi:
                for r in self.suivi.rows:
                    n = r.n_site_tadarida
                    if n and str(n).isdigit() and n not in seen:
                        seen.add(n)
                        out.append(n)
        except Exception:
            pass
        return sorted(out)

    def _pick_from(self, values: list[str], target_var: ctk.StringVar,
                    title: str):
        """Mini-dialogue avec liste cliquable pour choisir une valeur."""
        if not values:
            return
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("420x420")
        dlg.transient(self)
        dlg.after(50, dlg.grab_set)
        dlg.grid_columnconfigure(0, weight=1)
        dlg.grid_rowconfigure(1, weight=1)

        # Recherche
        filter_var = ctk.StringVar()
        filter_entry = ctk.CTkEntry(
            dlg, textvariable=filter_var,
            placeholder_text="🔍 filtrer…",
        )
        filter_entry.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))

        scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        scroll.grid_columnconfigure(0, weight=1)

        def _render(q: str = ""):
            for w in scroll.winfo_children():
                w.destroy()
            q_lower = q.lower()
            for i, v in enumerate(values):
                if q_lower and q_lower not in v.lower():
                    continue
                ctk.CTkButton(
                    scroll, text=v, anchor="w", height=28,
                    font=ctk.CTkFont(size=11),
                    fg_color=("gray95", "gray22"),
                    text_color=("gray15", "gray90"),
                    hover_color=("#cfe2ff", "#1a3d5c"),
                    command=lambda val=v: (target_var.set(val), dlg.destroy()),
                ).grid(row=i, column=0, sticky="ew", padx=2, pady=2)

        _render()
        filter_var.trace_add("write", lambda *_: _render(filter_var.get()))
        filter_entry.focus_set()

    def _open_date_picker(self):
        """Ouvre un mini-calendrier pour choisir la date de début.

        Implémentation custom (pas de dépendance tkcalendar) : grille de
        boutons jours d'un mois, navigation mois précédent / suivant.
        """
        # Pré-remplir avec la date actuellement saisie ou aujourd'hui
        from datetime import date as _date, datetime as _dt
        try:
            current = _dt.strptime(self.date_var.get().strip(),
                                     "%Y-%m-%d").date()
        except (ValueError, TypeError):
            current = _date.today()

        dlg = ctk.CTkToplevel(self)
        dlg.title("Choisir une date")
        dlg.geometry("300x320")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.after(50, dlg.grab_set)
        dlg.grid_columnconfigure(0, weight=1)

        state = {"year": current.year, "month": current.month}

        # Header navigation
        nav = ctk.CTkFrame(dlg, fg_color="transparent")
        nav.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        nav.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            nav, text="◂", width=36, height=28,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=lambda: _shift(-1),
        ).grid(row=0, column=0, padx=(0, 4))

        title_lbl = ctk.CTkLabel(
            nav, text="", font=ctk.CTkFont(size=13, weight="bold"),
        )
        title_lbl.grid(row=0, column=1)

        ctk.CTkButton(
            nav, text="▸", width=36, height=28,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=lambda: _shift(1),
        ).grid(row=0, column=2, padx=(4, 0))

        # Grille des jours
        grid_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        grid_frame.grid(row=1, column=0, padx=10, pady=(0, 10))
        for i in range(7):
            grid_frame.grid_columnconfigure(i, weight=1, uniform="day")

        MOIS = ["janvier", "février", "mars", "avril", "mai", "juin",
                "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        JOURS = ["L", "M", "M", "J", "V", "S", "D"]

        def _shift(delta: int):
            m = state["month"] + delta
            y = state["year"]
            while m < 1:
                m += 12
                y -= 1
            while m > 12:
                m -= 12
                y += 1
            state["month"] = m
            state["year"] = y
            _redraw()

        def _on_pick(d: _date):
            self.date_var.set(d.strftime("%Y-%m-%d"))
            dlg.destroy()

        def _redraw():
            for w in grid_frame.winfo_children():
                w.destroy()
            title_lbl.configure(
                text=f"{MOIS[state['month'] - 1]} {state['year']}")
            # Entête jours
            for i, lbl in enumerate(JOURS):
                ctk.CTkLabel(
                    grid_frame, text=lbl,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=("gray50", "gray60"),
                ).grid(row=0, column=i, padx=1, pady=1)
            # Calcul du 1er jour du mois et nombre de jours
            import calendar as _cal
            first_weekday, n_days = _cal.monthrange(state["year"],
                                                       state["month"])
            # first_weekday : 0=Lundi → on est aligné sur notre grille
            row_g = 1
            col = first_weekday
            today = _date.today()
            for day in range(1, n_days + 1):
                d = _date(state["year"], state["month"], day)
                is_today = (d == today)
                fg = ("#1f6feb", "#1f6feb") if is_today \
                    else ("gray95", "gray22")
                tc = "white" if is_today \
                    else ("gray15", "gray90")
                ctk.CTkButton(
                    grid_frame, text=str(day), width=32, height=30,
                    font=ctk.CTkFont(size=11,
                                       weight="bold" if is_today else "normal"),
                    fg_color=fg, text_color=tc,
                    hover_color=("#cfe2ff", "#1a3d5c"),
                    command=lambda dd=d: _on_pick(dd),
                ).grid(row=row_g, column=col, padx=1, pady=1)
                col += 1
                if col >= 7:
                    col = 0
                    row_g += 1

        _redraw()

    def _add_field_label(self, form, row, text, *, help=""):
        """Affiche un label principal + un sous-titre d'aide, empilés.

        Sous-frame compact (pas de grid_propagate False / pas de hauteur fixe)
        pour éviter l'espacement vertical excessif rapporté par les testeurs.
        Le sous-frame s'adapte à la hauteur des 2 labels (sticky="ew" sur
        column=0) et la rangée du form prend le minimum de hauteur.
        """
        cell = ctk.CTkFrame(form, fg_color="transparent")
        cell.grid(row=row, column=0, sticky="nw", padx=(16, 8), pady=(4, 0))
        cell.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            cell, text=text,
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w", justify="left", width=180,
        ).grid(row=0, column=0, sticky="w")

        if help:
            ctk.CTkLabel(
                cell, text=help,
                font=ctk.CTkFont(size=10),
                text_color=("gray50", "gray60"),
                anchor="w", justify="left", wraplength=170, width=180,
            ).grid(row=1, column=0, sticky="w", pady=(0, 0))

    # -- Pré-remplissage / watchers ----------------------------------------

    def _summary_wav_warning(self) -> str | None:
        if not self.session_path:
            return None
        try:
            from rename import inspect_summary_vs_wav
            return inspect_summary_vs_wav(self.session_path).get("warning")
        except Exception:
            return None

    def _apply_summary_wav_hint(self):
        warn = self._summary_wav_warning()
        if not warn:
            return
        try:
            from rename import inspect_summary_vs_wav
            info = inspect_summary_vs_wav(self.session_path)
            wav_min = info.get("wav_min")
            if wav_min is not None:
                self.date_var.set(wav_min.strftime("%Y-%m-%d"))
            self._date_hint.configure(
                text="⚠ Summary ≠ WAV (carte SD souvent non formatée). "
                     "Date proposée = celle des fichiers.")
        except Exception:
            try:
                self._date_hint.configure(text="⚠ " + warn.splitlines()[0])
            except Exception:
                pass

    def _fill_from(self, meta: SessionMeta):
        if meta.nom_contrat:
            self.contrat_var.set(meta.nom_contrat)
        if meta.date_debut:
            self.date_var.set(meta.date_debut.strftime("%Y-%m-%d"))
        if meta.n_site_tadarida:
            self.site_var.set(meta.n_site_tadarida)
        if meta.n_point_fixe:
            self.point_var.set(meta.n_point_fixe)
        if meta.n_passage is not None:
            self.pass_var.set(str(meta.n_passage))
        if meta.n_enregistreur is not None:
            n = meta.n_enregistreur
            # Cherche le label correspondant dans notre mapping
            match_label = None
            for lbl, lid in self._enr_label_to_id.items():
                if lid == n:
                    match_label = lbl
                    break
            if match_label:
                self.enr_var.set(match_label)
            else:
                # N° hors parc et hors 1..27 : bascule sur "Autre" + champ libre
                self.enr_var.set("Autre")
                self.enr_other_var.set(str(n))
                self._on_enr_menu_change("Autre")
            # _on_enr_change se déclenche via trace
        if meta.n_serie:
            self.serie_var.set(meta.n_serie)

    def _on_enr_menu_change(self, value: str):
        """Affiche/masque le champ libre 'Autre'."""
        if value == "Autre":
            self.enr_other_entry.grid(row=0, column=1, sticky="w", padx=(6, 0))
        else:
            self.enr_other_entry.grid_forget()
            self.enr_other_var.set("")

    def _on_enr_change(self, *_):
        """Quand l'utilisateur change le n° enreg, auto-remplit série/micro."""
        v = self.enr_var.get().strip()
        if not v:
            self.enr_info_lbl.configure(text="")
            return
        # Le dropdown contient des labels riches ("#7 SM4BAT (...)") + "Autre".
        # On extrait l'id via le mapping. "Autre" = None (géré plus bas).
        n = self._extract_enr_id(v)
        if n is None:
            self.enr_info_lbl.configure(text="")
            return

        # 1. Priorité : parc matériel persistant de l'app (Préférences → Mes matériels).
        # Source canonique, à jour, pas dépendante d'un Suivi Excel présent.
        try:
            from materiels import find_by_id, load_materiels
            m = find_by_id(load_materiels(), n)
        except Exception:
            m = None
        if m is not None and not m.is_empty():
            bits = []
            if m.modele:
                bits.append(m.modele)
            if m.serie_enr:
                bits.append(f"série {m.serie_enr}")
            if m.micro_modele:
                bits.append(f"micro {m.micro_modele}")
            self.enr_info_lbl.configure(
                text=" · ".join(bits) + "  (parc local)",
                text_color=("gray40", "gray70"))
            if m.serie_enr and not self.serie_var.get().strip():
                self.serie_var.set(m.serie_enr)
            return

        # 2. Fallback : Feuil2 du Suivi Excel (compat historique).
        if not self.suivi:
            self.enr_info_lbl.configure(
                text="(aucun matériel saisi pour ce n°. Préférences → Mes matériels)",
                text_color=("#bf8700", "#d29922"))
            return
        e = self.suivi.enregistreur(n)
        if e is None:
            self.enr_info_lbl.configure(
                text="(inconnu dans Feuil2 et dans Mes matériels)",
                text_color=("#cf222e", "#f85149"))
            return
        info = f"{e.modele or '?'} · série {e.serie_enr or '?'}  (Feuil2 Suivi)"
        self.enr_info_lbl.configure(text=info,
                                       text_color=("gray40", "gray70"))
        if e.serie_enr and not self.serie_var.get().strip():
            self.serie_var.set(e.serie_enr)

    # -- Validation --------------------------------------------------------

    def _on_validate(self):
        self.err_lbl.configure(text="")
        errs = []

        contrat = self.contrat_var.get().strip() or None

        date_str = self.date_var.get().strip()
        date_debut = None
        if not date_str:
            errs.append("date début manquante")
        else:
            try:
                date_debut = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                errs.append(f"date invalide : {date_str!r} (format YYYY-MM-DD)")

        site = self.site_var.get().strip()
        if site and site.isdigit():
            site = site.zfill(6)
        point = self.point_var.get().strip().upper()
        try:
            n_pass = int(self.pass_var.get())
        except ValueError:
            n_pass = None
            errs.append("passage invalide")
        # N° enregistreur : le dropdown contient des labels riches.
        # On extrait l'id via le mapping ; "Autre" → champ libre.
        enr_choice = self.enr_var.get().strip()
        n_enr: int | None
        if enr_choice == "Autre":
            try:
                n_enr = int(self.enr_other_var.get().strip())
                if n_enr < 1:
                    errs.append("n° enregistreur doit être >= 1")
                    n_enr = None
            except (ValueError, TypeError):
                n_enr = None
                errs.append("n° enregistreur invalide (entier attendu)")
        else:
            n_enr = self._extract_enr_id(enr_choice)
            if n_enr is None:
                errs.append("n° enregistreur manquant (choisis dans la liste)")
        serie = self.serie_var.get().strip()

        meta = SessionMeta(
            date_debut=date_debut,
            n_site_tadarida=site or None,
            n_point_fixe=point or None,
            n_passage=n_pass,
            n_enregistreur=n_enr,
            n_serie=serie or None,
            nom_contrat=contrat,
        )

        validation_errs = validate_meta(meta)
        if validation_errs:
            # Traduit les noms de champs internes (n_site_tadarida…) en libellés
            # d'écran lisibles par un naturaliste. naming.validate_meta reste pur.
            _lbl = {"n_site_tadarida": "N° site Tadarida", "n_point_fixe": "Point",
                    "n_passage": "Passage", "n_enregistreur": "N° enregistreur",
                    "n_serie": "Série", "date_debut": "Date de début",
                    "nom_contrat": "Contrat"}
            for e in validation_errs:
                for k, v in _lbl.items():
                    e = e.replace(k, v)
                errs.append(e)

        if errs:
            self.err_lbl.configure(text="⚠  " + "\n⚠  ".join(errs))
            return

        # Vérification de cohérence non-bloquante : si l'enregistreur saisi
        # correspond à un matériel du parc mais que la série diffère, alerter.
        # (ex: utilisateur s'est trompé de numéro ou vient de prêter son
        # enregistreur #7 à un collègue qui a mis le sien à la place)
        warning_msg = None
        try:
            from materiels import find_by_id, load_materiels
            if meta.n_enregistreur is not None and meta.n_serie:
                mat = find_by_id(load_materiels(), meta.n_enregistreur)
                if mat and mat.serie_enr:
                    saisie = meta.n_serie.strip().upper()
                    attendue = mat.serie_enr.strip().upper()
                    if saisie != attendue:
                        warning_msg = (
                            f"⚠ La série saisie ({meta.n_serie}) ne correspond "
                            f"pas à la série du matériel #{meta.n_enregistreur} "
                            f"dans « Mes matériels » ({mat.serie_enr}).\n"
                            "Continuer quand même ?"
                        )
        except Exception:
            pass
        if warning_msg:
            from tkinter import messagebox
            if not messagebox.askyesno("Série incohérente",
                                         warning_msg, parent=self):
                return

        self._result = meta
        self.destroy()

    def _on_cancel(self):
        self._result = None
        self.destroy()

    def get(self) -> SessionMeta | None:
        """À appeler après wait_window() pour récupérer le résultat."""
        return self._result


def open_wizard(master, *, prefill: SessionMeta | None = None,
                session_name: str | None = None,
                session_path: Path | None = None) -> SessionMeta | None:
    """Helper : ouvre le wizard bloquant et retourne la SessionMeta ou None.

    Si un PointSelection a été retenu (pick carte / récent avec GPS), il est
    attaché sur ``meta._point_selection`` pour que l'appelant le fusionne
    dans le manifest (D8).
    """
    dlg = SessionMetaWizard(master, prefill=prefill, session_name=session_name,
                            session_path=session_path)
    master.wait_window(dlg)
    meta = dlg.get()
    if meta is not None:
        try:
            meta._point_selection = dlg.get_point_selection()  # type: ignore[attr-defined]
        except Exception:
            pass
    return meta
