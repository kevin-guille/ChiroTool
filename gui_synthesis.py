"""
gui_synthesis.py — fenêtre « Synthèse de la nuit ».

Affiche, pour une nuit, le nombre de contacts par espèce retenue (validation
observateur si présente, sinon Tadarida) + les totaux, et permet un export CSV
pour les rapports. S'appuie sur la logique pure ``synthesis.compute_night_synthesis``.
"""

from __future__ import annotations

import csv
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

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


class SynthesisView(ctk.CTkToplevel):
    """Fenêtre récapitulative (contacts par espèce) d'une nuit."""

    def __init__(self, master, *, session_path: Path, xlsx_path: Path):
        super().__init__(master)
        self.session_path = Path(session_path)
        self.xlsx_path = Path(xlsx_path)
        self.result: dict | None = None

        self.title(f"Synthèse — {self.session_path.name}")
        self.geometry("720x620")
        self.minsize(560, 440)
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

        cols = ("taxon", "groupe", "contacts", "fichiers")
        self.tree = ttk.Treeview(table, columns=cols, show="headings")
        self.tree.heading("taxon", text="Espèce")
        self.tree.heading("groupe", text="Groupe")
        self.tree.heading("contacts", text="Contacts")
        self.tree.heading("fichiers", text="Fichiers")
        self.tree.column("taxon", width=200, anchor="w")
        self.tree.column("groupe", width=150, anchor="w")
        self.tree.column("contacts", width=100, anchor="center")
        self.tree.column("fichiers", width=100, anchor="center")
        self.tree.tag_configure("validated", background="#e8f5ec")
        self.tree.tag_configure("total", background="#eef2f8")
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 12))
        footer.grid_columnconfigure(0, weight=1)
        self.count_lbl = ctk.CTkLabel(
            footer, text="", anchor="w", font=ctk.CTkFont(size=11))
        self.count_lbl.grid(row=0, column=0, sticky="w")
        self.export_btn = ctk.CTkButton(
            footer, text="📤 Exporter CSV", width=140, height=32,
            command=self._export_csv, state="disabled",
        )
        self.export_btn.grid(row=0, column=1, padx=(6, 6))
        ctk.CTkButton(
            footer, text="Fermer", width=100, height=32,
            fg_color=("gray85", "gray25"), text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"), command=self.destroy,
        ).grid(row=0, column=2)

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

        headers = [str(h) if h is not None else "" for h in data[0]]
        rows = [list(r) for r in data[1:] if any(c is not None for c in r)]
        self.result = compute_night_synthesis(headers, rows)
        self._refresh()

    def _refresh(self):
        res = self.result or {}
        species = res.get("species", [])
        by_group = res.get("by_group", {})

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for i, s in enumerate(species):
            grp = GROUP_LABELS.get(s["groupe"], s["groupe"])
            tags = ("validated",) if s["validated"] else ()
            self.tree.insert("", "end", iid=str(i), tags=tags, values=(
                s["taxon"], grp, s["n_contacts"], s["n_fichiers"]))
        # Ligne total
        if species:
            self.tree.insert("", "end", iid="__total__", tags=("total",), values=(
                "TOTAL", f"{len(species)} espèce(s)",
                res.get("total_contacts", 0), res.get("total_fichiers", 0)))

        # Résumé par groupe (ordre métier)
        order = ["chiros", "orthos", "micromam", "oiseaux", "unknown", "noise"]
        parts = [f"{GROUP_LABELS.get(g, g)} : {by_group[g]}"
                 for g in order if g in by_group]
        for g in by_group:
            if g not in order:
                parts.append(f"{GROUP_LABELS.get(g, g)} : {by_group[g]}")
        self.summary_lbl.configure(
            text="Par groupe —  " + ("   ·   ".join(parts) if parts else "aucun contact"))
        self.count_lbl.configure(text=(
            f"{res.get('total_contacts', 0)} contacts  ·  "
            f"{len(species)} espèces  ·  "
            f"{res.get('total_fichiers', 0)} fichiers"))
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
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Espece", "Groupe", "Contacts", "Fichiers", "Valide"])
                for s in species:
                    w.writerow([s["taxon"], s["groupe"], s["n_contacts"],
                                s["n_fichiers"], "oui" if s["validated"] else ""])
                w.writerow([])
                w.writerow(["TOTAL", "", res.get("total_contacts", 0),
                            res.get("total_fichiers", 0), ""])
        except Exception as e:
            messagebox.showerror("Export échoué", str(e), parent=self)
            return
        self.count_lbl.configure(text=f"✓ exporté : {Path(path).name}")
