"""
gui_synthesis.py — fenêtre « Synthèse de la nuit ».

Affiche, pour une nuit, le nombre de contacts par espèce retenue (validation
observateur si présente, sinon Tadarida) + les totaux, et permet un export CSV
pour les rapports. S'appuie sur ``synthesis.compute_night_synthesis`` et, pour la méthode
MNHN 10 % / 75 %, ``compute_mnhn_synthesis``.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from activity_reference import (
    annotate_synthesis, load_reference, region_for_site, season_for_date,
    CITATION, HABITATS, UNITE,
)
from synthesis import (
    compute_mnhn_synthesis, compute_night_synthesis, merge_night_syntheses,
)

# Libellés lisibles des groupes métier.
GROUP_LABELS = {
    "chiros": "Chiroptères",
    "orthos": "Orthoptères",
    "micromam": "Micromammifères",
    "oiseaux": "Oiseaux",
    "noise": "Bruit",
    "unknown": "Indéterminé",
}

# Menu « milieu dominant » (habitats grossiers du référentiel + option national).
_HABITAT_NATIONAL = "— (national)"
_HABITAT_LABELS = {
    "Foret": "Forêt", "Agricole": "Agricole", "Urbain": "Urbain",
    "Riviere": "Rivière", "Agricole-Foret": "Agricole / Forêt",
    "Agricole-Urbain": "Agricole / Urbain", "Foret-Urbain": "Forêt / Urbain",
}
_SEASON_LABELS = {"printemps": "printemps", "ete": "été", "automne": "automne",
                  "toutes": "toutes saisons"}


def _parse_night_context(session_name: str):
    """(saison, region) déduits du nom canonique ``YYYYMMDD_site<N6>_…``.
    Aucune saisie : la date donne la saison, le n° de site donne le département."""
    m = re.match(r"(\d{8})", session_name or "")
    dt = None
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%Y%m%d")
        except ValueError:
            dt = None
    ms = re.search(r"site(\d{6})", session_name or "")
    region = region_for_site(ms.group(1)) if ms else None
    return season_for_date(dt), region


class SynthesisView(ctk.CTkToplevel):
    """Fenêtre récapitulative (contacts par espèce) d'une nuit."""

    def __init__(self, master, *, session_path: Path, xlsx_path: Path,
                 prefer_vu_night: int | None = None):
        super().__init__(master)
        self.session_path = Path(session_path)
        self.xlsx_path = Path(xlsx_path)
        self.prefer_vu_night = prefer_vu_night
        self.result: dict | None = None
        self._source_label = self.xlsx_path.name

        # Contexte d'interprétation (niveaux d'activité)
        self._reference = load_reference()          # {} si CSV absent → pas de classe
        self._season, self._region = _parse_night_context(self.session_path.name)
        self._habitat = None                        # milieu dominant (choix utilisateur)

        title_extra = f" · nuit {prefer_vu_night}" if prefer_vu_night else ""
        self.title(f"Synthèse — {self.session_path.name}{title_extra}")
        self.geometry("820x700")
        self.minsize(640, 480)
        self.transient(master)
        self.after(50, self.grab_set)
        self.focus()

        self._xlsx_headers: list = []
        self._xlsx_rows: list = []
        self._slices: list = []
        self._vu_by_night: dict[int, object] = {}
        self._night_key = int(prefer_vu_night) if prefer_vu_night else 1
        self._night_labels: dict[str, int] = {}
        self._mixed_nights = False
        self._data_ready = False
        self._mnhn_xlsx_warning = False

        self._build_ui()
        self.after(80, self._load)

    # -- UI -----------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text=f"📊  Synthèse — {self.session_path.name}",
            font=ctk.CTkFont(size=16, weight="bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w")

        # Sélecteur de nuit (multi-nuits bio) : indépendant de ChiroSurf.
        self.night_row = ctk.CTkFrame(header, fg_color="transparent")
        self.night_row.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ctk.CTkLabel(
            self.night_row, text="Nuit :", font=ctk.CTkFont(size=11),
        ).pack(side="left")
        self._night_var = ctk.StringVar(value="")
        self._night_menu = ctk.CTkOptionMenu(
            self.night_row, variable=self._night_var, width=340,
            values=["—"], command=self._on_night_change,
            font=ctk.CTkFont(size=12),
        )
        self._night_menu.pack(side="left", padx=(6, 0))
        self.night_row.grid_remove()

        # Ne compter que les identifications VALIDÉES par l'observateur (ignore
        # les identifications automatiques Tadarida non revues).
        self.validated_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            header, text="Identifications validées seulement",
            variable=self.validated_only_var, command=self._on_validated_toggle,
            font=ctk.CTkFont(size=11), checkbox_width=18, checkbox_height=18,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.mnhn_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            header, text="Méthode MNHN 10 % / 75 %",
            variable=self.mnhn_var, command=self._on_mnhn_toggle,
            font=ctk.CTkFont(size=11), checkbox_width=18, checkbox_height=18,
        ).grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.chiros_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            header, text="Chiros seulement",
            variable=self.chiros_only_var, command=self._recompute,
            font=ctk.CTkFont(size=11), checkbox_width=18, checkbox_height=18,
        ).grid(row=2, column=1, sticky="w", pady=(4, 0), padx=(12, 0))

        # Filtre proba Tadarida min (synthèse non validée) — issue #3
        filt = ctk.CTkFrame(header, fg_color="transparent")
        filt.grid(row=4, column=0, sticky="w", pady=(4, 0))
        ctk.CTkLabel(filt, text="Proba Tadarida ≥", font=ctk.CTkFont(size=11)).pack(
            side="left")
        self.min_proba_var = ctk.StringVar(value="")
        self.min_proba_entry = ctk.CTkEntry(
            filt, textvariable=self.min_proba_var, width=56,
            placeholder_text="ex 0.5",
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self.min_proba_entry.pack(side="left", padx=(4, 4))
        self.min_proba_btn = ctk.CTkButton(
            filt, text="Appliquer", width=80, height=26,
            command=self._recompute,
        )
        self.min_proba_btn.pack(side="left")

        # Sélecteur « milieu dominant » : affine le référentiel d'activité
        # (contexte général autour du point). Défaut = national.
        if self._reference:
            ctk.CTkLabel(header, text="Milieu :", font=ctk.CTkFont(size=11)).grid(
                row=0, column=1, padx=(8, 4))
            self.habitat_var = ctk.StringVar(value=_HABITAT_NATIONAL)
            ctk.CTkOptionMenu(
                header, variable=self.habitat_var, width=160,
                values=[_HABITAT_NATIONAL] + [_HABITAT_LABELS[h] for h in HABITATS],
                command=self._on_habitat_change,
            ).grid(row=0, column=2, padx=(0, 2))

        self.summary_lbl = ctk.CTkLabel(
            self, text="chargement…", anchor="w", justify="left",
            font=ctk.CTkFont(size=12), text_color=("gray25", "gray75"),
        )
        self.summary_lbl.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))

        # Tableau
        table = ctk.CTkFrame(self)
        table.grid(row=2, column=0, sticky="nsew", padx=12, pady=4)
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)

        cols = ("taxon", "groupe", "contacts", "fichiers", "activite")
        self.tree = ttk.Treeview(table, columns=cols, show="headings")
        self.tree.heading("taxon", text="Espèce")
        self.tree.heading("groupe", text="Groupe")
        self.tree.heading("contacts", text="Contacts")
        self.tree.heading("fichiers", text="Fichiers")
        self.tree.heading("activite", text="Activité")
        self.tree.column("taxon", width=190, anchor="w")
        self.tree.column("groupe", width=130, anchor="w")
        self.tree.column("contacts", width=90, anchor="center")
        self.tree.column("fichiers", width=80, anchor="center")
        self.tree.column("activite", width=190, anchor="w")
        self.tree.tag_configure("validated", background="#e8f5ec")
        self.tree.tag_configure("total", background="#eef2f8")
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 12))
        footer.grid_columnconfigure(0, weight=1)

        # Garde-fous scientifiques + citation : toujours visibles, jamais un
        # « verdict » brut. Rempli dynamiquement dans _refresh (référentiel utilisé).
        self.note_lbl = ctk.CTkLabel(
            footer, text="", anchor="w", justify="left", wraplength=790,
            font=ctk.CTkFont(size=10), text_color=("gray45", "gray60"))
        self.note_lbl.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))

        self.count_lbl = ctk.CTkLabel(
            footer, text="", anchor="w", font=ctk.CTkFont(size=11))
        self.count_lbl.grid(row=1, column=0, sticky="w")
        self.export_btn = ctk.CTkButton(
            footer, text="📤 Exporter CSV", width=140, height=32,
            command=self._export_csv, state="disabled",
        )
        self.export_btn.grid(row=1, column=1, padx=(6, 6))
        ctk.CTkButton(
            footer, text="Fermer", width=100, height=32,
            fg_color=("gray85", "gray25"), text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"), command=self.destroy,
        ).grid(row=1, column=2)

    # -- Données ------------------------------------------------------------

    def _load(self):
        try:
            from chirosurf_nights import (
                list_chirosurf_nights, rows_from_xlsx,
                split_rows_by_biological_night, synthesis_night_menu,
                harvest_vu_sidecars,
            )
            harvest_vu_sidecars(self.session_path)
            headers, rows = rows_from_xlsx(self.xlsx_path)
        except Exception as e:
            messagebox.showerror("Lecture impossible",
                                 f"Impossible d'ouvrir les observations :\n{e}",
                                 parent=self)
            self.destroy()
            return
        if not headers:
            messagebox.showwarning("Fichier vide", "Le tableur est vide.", parent=self)
            self.destroy()
            return

        self._xlsx_headers = headers
        self._xlsx_rows = rows
        self._slices = split_rows_by_biological_night(headers, rows)
        self._vu_by_night = {
            nf.night_index: nf
            for nf in list_chirosurf_nights(self.session_path)
            if nf.has_vu and nf.vu_path.is_file()
        }
        if self.prefer_vu_night:
            self._night_key = int(self.prefer_vu_night)
        elif self._slices:
            self._night_key = self._slices[0].night_index
        else:
            self._night_key = 0
        self._fill_night_menu()
        self._apply_night_source()

    def _fill_night_menu(self):
        from chirosurf_nights import synthesis_night_menu
        items = synthesis_night_menu(
            self._slices, vu_indexes=set(self._vu_by_night),
        )
        self._night_labels = {label: key for key, label in items}
        if len(self._slices) <= 1:
            self.night_row.grid_remove()
            return
        labels = [label for _k, label in items]
        by_key = {key: label for key, label in items}
        chosen = by_key.get(self._night_key) or (labels[1] if len(labels) > 1 else labels[0])
        self._night_menu.configure(values=labels)
        self._night_var.set(chosen)
        self.night_row.grid()

    def _on_night_change(self, value=None):
        label = value if value is not None else self._night_var.get()
        key = self._night_labels.get(label)
        if key is None:
            return
        self._night_key = key
        extra = f" · nuit {key}" if key else ""
        self.title(f"Synthèse — {self.session_path.name}{extra}")
        self._apply_night_source()

    def _apply_night_source(self):
        from chirosurf_nights import resolve_synthesis_table
        vu = self._vu_by_night.get(self._night_key)
        vu_path = vu.vu_path if vu is not None else None
        headers, rows, src, mixed = resolve_synthesis_table(
            self._xlsx_headers, self._xlsx_rows,
            night_index=self._night_key, vu_path=vu_path,
        )
        self._headers = headers
        self._rows = rows
        self._source_label = src
        self._base_source_label = src
        self._mixed_nights = mixed
        self._data_ready = True
        self._recompute()

    def _on_mnhn_toggle(self):
        if self.mnhn_var.get():
            self.validated_only_var.set(False)
        self._sync_min_proba_state()
        self._recompute()

    def _on_validated_toggle(self):
        if self.validated_only_var.get():
            self.mnhn_var.set(False)
        self._sync_min_proba_state()
        self._recompute()

    def _sync_min_proba_state(self):
        mnhn = bool(getattr(self, "mnhn_var", None) and self.mnhn_var.get())
        state = "disabled" if mnhn else "normal"
        if hasattr(self, "min_proba_entry"):
            self.min_proba_entry.configure(state=state)
        if hasattr(self, "min_proba_btn"):
            self.min_proba_btn.configure(state=state)

    def _recompute(self):
        """(Re)calcule la synthèse selon filtres, puis niveaux d'activité."""
        if not getattr(self, "_data_ready", False):
            return
        vo = bool(self.validated_only_var.get()) if hasattr(self, "validated_only_var") else False
        mnhn = bool(getattr(self, "mnhn_var", None) and self.mnhn_var.get())
        chiros = bool(self.chiros_only_var.get()) if hasattr(self, "chiros_only_var") else False
        self._mnhn_xlsx_warning = False
        if mnhn:
            if getattr(self, "_mixed_nights", False) and getattr(self, "_slices", None):
                from chirosurf_nights import read_csv
                parts = []
                src_bits = []
                used_xlsx = False
                for sl in self._slices:
                    vu = (self._vu_by_night or {}).get(sl.night_index)
                    if vu is not None and vu.vu_path.is_file():
                        h, r = read_csv(vu.vu_path)
                        src_bits.append(f"nuit {sl.night_index} _Vu")
                    else:
                        h, r = sl.headers, sl.rows
                        src_bits.append(f"nuit {sl.night_index} xlsx")
                        used_xlsx = True
                    parts.append(compute_mnhn_synthesis(h, r, chiros_only=chiros))
                self.result = merge_night_syntheses(parts)
                self._source_label = "MNHN · " + " · ".join(src_bits)
                self._mnhn_xlsx_warning = used_xlsx
            else:
                self.result = compute_mnhn_synthesis(
                    self._headers, self._rows, chiros_only=chiros)
                src = str(getattr(self, "_source_label", "") or "")
                self._mnhn_xlsx_warning = not src.startswith("_Vu")
            self._apply_activity()
            return
        thr = None
        if hasattr(self, "min_proba_var"):
            raw = (self.min_proba_var.get() or "").strip().replace(",", ".")
            if raw:
                try:
                    thr = float(raw)
                    if thr > 1.0:  # utilisateur a saisi 50 pour 50 %
                        thr = thr / 100.0
                except ValueError:
                    thr = None
        self._source_label = getattr(
            self, "_base_source_label", getattr(self, "_source_label", ""))
        self.result = compute_night_synthesis(
            self._headers, self._rows,
            validated_only=vo,
            min_tadarida_proba=thr,
            chiros_only=chiros,
        )
        self._apply_activity()

    # -- niveaux d'activité -------------------------------------------------

    def _selected_habitat(self):
        var = getattr(self, "habitat_var", None)
        if var is None or var.get() == _HABITAT_NATIONAL:
            return None
        return next((c for c, lbl in _HABITAT_LABELS.items() if lbl == var.get()), None)

    def _apply_activity(self):
        """(Ré)annote la synthèse selon le contexte (saison/région/milieu) puis
        rafraîchit. Sans référentiel chargé, l'affichage reste un simple comptage.
        Cumul multi-nuits : pas de classes (référentiel = contacts/nuit)."""
        if self.result and self._reference and not self._mixed_nights:
            self._habitat = self._selected_habitat()
            annotate_synthesis(self.result, self._reference, saison=self._season,
                               region=self._region, habitat=self._habitat)
        elif self.result:
            for s in self.result.get("species", []):
                s.pop("activite", None)
        self._refresh()

    def _on_habitat_change(self, _value=None):
        self._apply_activity()

    def _activity_cell(self, s) -> str:
        a = s.get("activite")
        if not a:
            return "—" if s.get("groupe") == "chiros" else ""
        txt = a.get("classe") or "—"
        if not a.get("fiable"):
            txt += "  (indicatif)"
        return txt

    def _context_label(self) -> str:
        parts = [_SEASON_LABELS.get(self._season, self._season),
                 self._region or "national"]
        if self._habitat:
            parts.append(_HABITAT_LABELS.get(self._habitat, self._habitat))
        return " · ".join(parts)

    def _refresh(self):
        res = self.result or {}
        species = res.get("species", [])
        by_group = res.get("by_group", {})
        has_ref = bool(self._reference) and not self._mixed_nights

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for i, s in enumerate(species):
            grp = GROUP_LABELS.get(s["groupe"], s["groupe"])
            tags = ("validated",) if s["validated"] else ()
            self.tree.insert("", "end", iid=str(i), tags=tags, values=(
                s["taxon"], grp, s["n_contacts"], s["n_fichiers"],
                self._activity_cell(s) if has_ref else ""))
        if species:
            self.tree.insert("", "end", iid="__total__", tags=("total",), values=(
                "TOTAL", f"{res.get('richesse_totale', len(species))} taxon(s)",
                res.get("total_contacts", 0), res.get("total_fichiers", 0), ""))

        # Résumé par groupe (ordre métier)
        order = ["chiros", "orthos", "micromam", "oiseaux", "unknown", "noise"]
        parts = [f"{GROUP_LABELS.get(g, g)} : {by_group[g]}"
                 for g in order if g in by_group]
        for g in by_group:
            if g not in order:
                parts.append(f"{GROUP_LABELS.get(g, g)} : {by_group[g]}")
        self.summary_lbl.configure(
            text="Par groupe —  " + ("   ·   ".join(parts) if parts else "aucun contact"))

        val = res.get("validated_contacts", 0)
        src = getattr(self, "_source_label", "") or ""
        mnhn = res.get("method") == "mnhn"
        contacts_lbl = ("contacts retenus (MNHN 10 % / 75 %)" if mnhn
                        else "contacts détectés")
        self.count_lbl.configure(text=(
            f"{res.get('total_contacts', 0)} {contacts_lbl}  ·  "
            f"{val} identifiés (validés)  ·  "
            f"{res.get('richesse_chiros', 0)} espèces de chiros  ·  "
            f"{res.get('total_fichiers', 0)} fichiers"
            + (f"  ·  source : {src}" if src else "")))

        mnhn_warn = ""
        if res.get("method") == "mnhn" and getattr(self, "_mnhn_xlsx_warning", False):
            mnhn_warn = (
                " Source xlsx : la méthode suppose un échantillonnage ChiroSurf "
                "(bandes de confiance). Une validation contact par contact n'est "
                "pas le même protocole. "
            )
        mnhn_empty = (
            res.get("method") == "mnhn" and not species
        )
        if mnhn_empty:
            self.note_lbl.configure(text=(
                "Aucun contact écouté dans cette source. La méthode MNHN n'a "
                "rien à reconstituer. Ouvrez d'abord le CSV dans ChiroSurf "
                "pour produire un _Vu."
                + mnhn_warn))
        elif self._mixed_nights:
            extra = ""
            if res.get("method") == "mnhn":
                extra = (" Méthode MNHN calculée nuit par nuit, puis cumulée "
                         "(pas de classe d'activité sur le cumul). Une ligne "
                         "verte = au moins un contact écouté."
                         + mnhn_warn)
            self.note_lbl.configure(text=(
                "Cumul de plusieurs nuits biologiques : les classes d'activité "
                "(contacts/nuit) ne s'appliquent pas. Choisissez une nuit dans le "
                "menu pour l'interprétation. Indépendant de ChiroSurf."
                + extra))
        elif has_ref:
            prefix = ""
            if res.get("method") == "mnhn":
                prefix = (
                    "Méthode MNHN 10 % / 75 % : bandes de confiance Tadarida "
                    "(pas le temps). Une ligne verte = au moins un contact écouté. "
                    + mnhn_warn
                )
            self.note_lbl.configure(text=(
                prefix
                + f"Activité — référentiel : {self._context_label()} (unité : {UNITE}). "
                "Aide à l'interprétation espèce par espèce : ne pas comparer les "
                "contacts entre espèces ; une classe n'est pas un niveau d'enjeu ; "
                "valable sous réserve du protocole (matériel conforme, micro < 6 m, "
                f"métropole). Source : {CITATION}."))
        else:
            note = ""
            if res.get("method") == "mnhn":
                note = (
                    "Méthode MNHN 10 % / 75 % : bandes de confiance Tadarida "
                    "(pas le temps). Une ligne verte = au moins un contact écouté."
                    + mnhn_warn
                )
            self.note_lbl.configure(text=note)
        self.export_btn.configure(state="normal" if species else "disabled")

    # -- Export -------------------------------------------------------------

    def _export_csv(self):
        res = self.result or {}
        species = res.get("species", [])
        if not species:
            return
        default = f"synthese_{self.session_path.name}.csv"
        path = filedialog.asksaveasfilename(
            parent=self, title="Exporter la synthèse en CSV",
            defaultextension=".csv", initialfile=default,
            filetypes=[("CSV", "*.csv"), ("Tous", "*.*")],
        )
        if not path:
            return
        has_ref = bool(self._reference) and not self._mixed_nights
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                # En-tête « propre » : contexte + rappels, avant les données.
                w.writerow(["Synthèse de nuit", self.session_path.name])
                if res.get("method") == "mnhn":
                    w.writerow(["Methode", "MNHN 10 % / 75 % (bandes de confiance Tadarida)"])
                    w.writerow(["Contacts retenus", res.get("total_contacts", 0)])
                else:
                    w.writerow(["Contacts détectés", res.get("total_contacts", 0)])
                w.writerow(["Source", getattr(self, "_source_label", "")])
                if res.get("method") == "mnhn" and getattr(
                        self, "_mnhn_xlsx_warning", False):
                    w.writerow([
                        "Avertissement",
                        "Source xlsx : la methode suppose un echantillonnage "
                        "ChiroSurf (bandes de confiance).",
                    ])
                w.writerow(["Identifiés (validés)", res.get("validated_contacts", 0)])
                w.writerow(["Espèces de chiroptères", res.get("richesse_chiros", 0)])
                w.writerow(["Fichiers", res.get("total_fichiers", 0)])
                if has_ref:
                    w.writerow(["Référentiel d'activité", self._context_label(),
                                f"unité : {UNITE}"])
                w.writerow([])
                mnhn = res.get("method") == "mnhn"
                cols = ["Espece", "Groupe", "Contacts", "Contacts_valides",
                        "Fichiers", "Valide"]
                if mnhn:
                    cols += ["Atteint_75", "F75", "Pool_Tadarida", "Ajouts_forces"]
                if has_ref:
                    cols += ["Activite", "Referentiel_utilise", "Seuil_fiable",
                             "Q25", "Q75", "Q98"]
                w.writerow(cols)
                for s in species:
                    row = [s["taxon"], s["groupe"], s["n_contacts"],
                           s.get("n_valides", 0), s["n_fichiers"],
                           "oui" if s["validated"] else ""]
                    if mnhn:
                        if self._mixed_nights:
                            row += ["n/a cumul", "",
                                    s.get("n_pool", ""), s.get("n_forced", 0)]
                        else:
                            row += [
                                "oui" if s.get("reached_75") else "non",
                                "" if s.get("f75") is None else s.get("f75"),
                                s.get("n_pool", ""),
                                s.get("n_forced", 0),
                            ]
                    if has_ref:
                        a = s.get("activite") or {}
                        row += [a.get("classe") or "", a.get("referentiel") or "",
                                ("oui" if a.get("fiable") else "non") if a else "",
                                a.get("q25", ""), a.get("q75", ""), a.get("q98", "")]
                    w.writerow(row)
                w.writerow([])
                w.writerow(["TOTAL", res.get("richesse_totale", ""),
                            res.get("total_contacts", 0),
                            res.get("validated_contacts", 0),
                            res.get("total_fichiers", 0), ""])
                if has_ref:
                    w.writerow([])
                    w.writerow(["Avertissement", "Ne pas comparer les contacts entre "
                                "especes (detectabilite variable). Une classe "
                                "d'activite n'est pas un niveau d'enjeu de "
                                "conservation. Valable sous reserve du protocole."])
                    w.writerow(["Source", CITATION])
        except Exception as e:
            messagebox.showerror("Export échoué", str(e), parent=self)
            return
        self.count_lbl.configure(text=f"✓ exporté : {Path(path).name}")
