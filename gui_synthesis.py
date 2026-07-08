"""
gui_synthesis.py — fenêtre « Synthèse de la nuit ».

Affiche, pour une nuit, le nombre de contacts par espèce retenue (validation
observateur si présente, sinon Tadarida) + les totaux, et permet un export CSV
pour les rapports. S'appuie sur la logique pure ``synthesis.compute_night_synthesis``.
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
from synthesis import compute_night_synthesis

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

    def __init__(self, master, *, session_path: Path, xlsx_path: Path):
        super().__init__(master)
        self.session_path = Path(session_path)
        self.xlsx_path = Path(xlsx_path)
        self.result: dict | None = None

        # Contexte d'interprétation (niveaux d'activité)
        self._reference = load_reference()          # {} si CSV absent → pas de classe
        self._season, self._region = _parse_night_context(self.session_path.name)
        self._habitat = None                        # milieu dominant (choix utilisateur)

        self.title(f"Synthèse — {self.session_path.name}")
        self.geometry("820x660")
        self.minsize(640, 460)
        self.transient(master)
        self.after(50, self.grab_set)
        self.focus()

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

        # Ne compter que les identifications VALIDÉES par l'observateur (ignore
        # les identifications automatiques Tadarida non revues).
        self.validated_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            header, text="Identifications validées seulement",
            variable=self.validated_only_var, command=self._recompute,
            font=ctk.CTkFont(size=11), checkbox_width=18, checkbox_height=18,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

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
            import warnings
            warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
            import openpyxl
            wb = openpyxl.load_workbook(self.xlsx_path, data_only=True)
            ws = wb.active
            data = list(ws.iter_rows(values_only=True))
        except Exception as e:
            messagebox.showerror("Lecture impossible",
                                 f"Impossible d'ouvrir {self.xlsx_path.name} :\n{e}",
                                 parent=self)
            self.destroy()
            return
        if not data:
            messagebox.showwarning("Fichier vide", "Le tableur est vide.", parent=self)
            self.destroy()
            return

        self._headers = [str(h) if h is not None else "" for h in data[0]]
        self._rows = [list(r) for r in data[1:] if any(c is not None for c in r)]
        self._recompute()

    def _recompute(self):
        """(Re)calcule la synthèse selon la case « validées seulement », puis
        (ré)applique les niveaux d'activité et rafraîchit."""
        vo = bool(self.validated_only_var.get()) if hasattr(self, "validated_only_var") else False
        self.result = compute_night_synthesis(self._headers, self._rows, validated_only=vo)
        self._apply_activity()

    # -- niveaux d'activité -------------------------------------------------

    def _selected_habitat(self):
        var = getattr(self, "habitat_var", None)
        if var is None or var.get() == _HABITAT_NATIONAL:
            return None
        return next((c for c, lbl in _HABITAT_LABELS.items() if lbl == var.get()), None)

    def _apply_activity(self):
        """(Ré)annote la synthèse selon le contexte (saison/région/milieu) puis
        rafraîchit. Sans référentiel chargé, l'affichage reste un simple comptage."""
        if self.result and self._reference:
            self._habitat = self._selected_habitat()
            annotate_synthesis(self.result, self._reference, saison=self._season,
                               region=self._region, habitat=self._habitat)
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
        has_ref = bool(self._reference)

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
        self.count_lbl.configure(text=(
            f"{res.get('total_contacts', 0)} contacts détectés  ·  "
            f"{val} identifiés (validés)  ·  "
            f"{res.get('richesse_chiros', 0)} espèces de chiros  ·  "
            f"{res.get('total_fichiers', 0)} fichiers"))

        if has_ref:
            self.note_lbl.configure(text=(
                f"Activité — référentiel : {self._context_label()} (unité : {UNITE}). "
                "Aide à l'interprétation espèce par espèce : ne pas comparer les "
                "contacts entre espèces ; une classe n'est pas un niveau d'enjeu ; "
                "valable sous réserve du protocole (matériel conforme, micro < 6 m, "
                f"métropole). Source : {CITATION}."))
        else:
            self.note_lbl.configure(text="")
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
        has_ref = bool(self._reference)
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                # En-tête « propre » : contexte + rappels, avant les données.
                w.writerow(["Synthèse de nuit", self.session_path.name])
                w.writerow(["Contacts détectés", res.get("total_contacts", 0)])
                w.writerow(["Identifiés (validés)", res.get("validated_contacts", 0)])
                w.writerow(["Espèces de chiroptères", res.get("richesse_chiros", 0)])
                w.writerow(["Fichiers", res.get("total_fichiers", 0)])
                if has_ref:
                    w.writerow(["Référentiel d'activité", self._context_label(),
                                f"unité : {UNITE}"])
                w.writerow([])
                cols = ["Espece", "Groupe", "Contacts", "Contacts_valides",
                        "Fichiers", "Valide"]
                if has_ref:
                    cols += ["Activite", "Referentiel_utilise", "Seuil_fiable",
                             "Q25", "Q75", "Q98"]
                w.writerow(cols)
                for s in species:
                    row = [s["taxon"], s["groupe"], s["n_contacts"],
                           s.get("n_valides", 0), s["n_fichiers"],
                           "oui" if s["validated"] else ""]
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
