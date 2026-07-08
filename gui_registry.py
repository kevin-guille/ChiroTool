"""
gui_registry.py — onglet Registre dans la GUI principale.

Vues :
  - Groupée par contrat (accordéon dépliable) — défaut
  - Tableau plat (triable, filtrable)

Fonctionnalités :
  - Filtres : année, contrat, état (pastilles), recherche globale
  - Édition inline (double-clic) commentaires + champs custom
  - Import / Export (Suivi xlsx, registry .db)
  - Stats contextuelles en pied de panneau
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import customtkinter as ctk

from registry import ETAT_LABELS, Registry


class SyncPreviewDialog(ctk.CTkToplevel):
    """Pop-up affichant le diff de synchronisation API, avec confirmation."""

    def __init__(self, master, *, registry, token: str):
        super().__init__(master)
        self.title("Synchronisation Vigie-Chiro")
        self.geometry("760x600")
        self.minsize(640, 480)
        self.transient(master)
        self.after(50, self.grab_set)

        self.registry = registry
        self.token = token
        self.preview: dict | None = None
        self.applied = False

        self._build_ui()
        self.after(100, self._run_preview)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header_lbl = ctk.CTkLabel(
            self, text="🔄  Récupération en cours…",
            font=ctk.CTkFont(size=15, weight="bold"), anchor="w",
        )
        self.header_lbl.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))

        self.textbox = ctk.CTkTextbox(
            self, font=ctk.CTkFont(family="Consolas", size=11),
            wrap="none",
        )
        self.textbox.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))
        self.textbox.configure(state="disabled")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        footer.grid_columnconfigure(0, weight=1)

        self.status_lbl = ctk.CTkLabel(
            footer, text="Préparation…",
            font=ctk.CTkFont(size=11), anchor="w",
        )
        self.status_lbl.grid(row=0, column=0, sticky="w")

        self.cancel_btn = ctk.CTkButton(
            footer, text="Annuler", width=100, height=32,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self.destroy,
        )
        self.cancel_btn.grid(row=0, column=1, padx=(6, 6))

        self.apply_btn = ctk.CTkButton(
            footer, text="Appliquer", width=140, height=32,
            font=ctk.CTkFont(weight="bold"),
            state="disabled",
            command=self._apply,
        )
        self.apply_btn.grid(row=0, column=2)

    def _append(self, line: str = ""):
        self.textbox.configure(state="normal")
        self.textbox.insert("end", line + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def _run_preview(self):
        """Lance la récupération API en thread et affiche le diff."""
        self._append("Récupération des participations via /api/v1/moi/participations…")

        def _on_progress(n, total):
            try:
                self.after(0, lambda: self.status_lbl.configure(
                    text=f"⏳ {n} participations récupérées…"))
            except Exception:
                pass

        def _worker():
            try:
                # Preview-only : ne modifie pas le registre
                result = self.registry.sync_from_api(
                    self.token, on_progress=_on_progress,
                    apply_changes=False,
                )
            except Exception as e:
                self.after(0, lambda: self._show_error(str(e)))
                return
            self.after(0, lambda: self._show_preview(result))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_error(self, msg: str):
        self._append(f"\n✗  Erreur : {msg}")
        self.status_lbl.configure(text="✗ échec", text_color=("#cf222e", "#f85149"))

    def _show_preview(self, result: dict):
        self.preview = result

        total = result["total_fetched"]
        n_upd = len(result["updates"])
        n_ghost = len(result["ghosts"])
        n_same = len(result["unchanged"])
        n_err = len(result["errors"])

        self.header_lbl.configure(
            text=f"🔄  {total} participations récupérées   "
                 f"·   {n_upd} à mettre à jour   ·   {n_ghost} ghosts   "
                 f"·   {n_same} déjà alignées")

        self._append("")
        if n_upd:
            self._append(f"═══ Sessions locales à mettre à jour ({n_upd}) ═══")
            for u in result["updates"][:30]:
                ch = u.get("changes", {})
                ch_str = ", ".join(f"{k}={v}" for k, v in ch.items()
                                    if k not in ("last_api_sync_at", "api_etat"))
                self._append(f"  ✓ {u['label']}  → {ch_str}  (API état: {u['api_etat']})")
            if n_upd > 30:
                self._append(f"  ... +{n_upd - 30} autres")
            self._append("")

        if n_ghost:
            self._append(f"═══ Participations serveur sans équivalent local ({n_ghost}) ═══")
            self._append("  (seront ajoutées au registre avec marqueur 👻)")
            for g in result["ghosts"][:20]:
                self._append(
                    f"  👻 {g.get('site_numero', '?')}  /  "
                    f"{g.get('point', '?')}  /  {g.get('date_debut', '?')}  "
                    f"(état API: {g.get('etat', '?')})"
                )
            if n_ghost > 20:
                self._append(f"  ... +{n_ghost - 20} autres")
            self._append("")

        if n_err:
            self._append(f"═══ Erreurs ({n_err}) ═══")
            for e in result["errors"][:10]:
                self._append(f"  ✗ {e}")
            self._append("")

        if n_upd == 0 and n_ghost == 0:
            self._append("✓ Tout est déjà aligné. Rien à synchroniser.")
            self.status_lbl.configure(text="✓ Déjà à jour",
                                         text_color=("#2ea043", "#3fb950"))
        else:
            self.apply_btn.configure(state="normal")
            self.status_lbl.configure(text="En attente de ta confirmation")

    def _apply(self):
        """Applique les changements préparés."""
        if not self.preview:
            return
        self.apply_btn.configure(state="disabled", text="Application…")
        self.cancel_btn.configure(state="disabled")

        def _worker():
            try:
                # Réapplique les changements (cette fois avec apply_changes=True)
                result = self.registry.sync_from_api(
                    self.token, apply_changes=True)
                self.applied = True
                self.after(0, lambda: self._show_applied(result))
            except Exception as e:
                self.after(0, lambda: self._show_error(str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_applied(self, result: dict):
        self._append("")
        self._append("═══ ✓ CHANGEMENTS APPLIQUÉS ═══")
        self._append(f"  Sessions mises à jour : {len(result['updates'])}")
        self._append(f"  Ghosts ajoutés        : {len(result['ghosts'])}")
        self.status_lbl.configure(text="✓ Terminé",
                                     text_color=("#2ea043", "#3fb950"))
        self.apply_btn.configure(text="Fermer", state="normal",
                                    command=self.destroy)
        self.cancel_btn.configure(state="normal")


class _FormatChoiceDialog(ctk.CTkToplevel):
    """Petite modale proposant 2 formats explicites (+ Annuler).

    Remplace ``messagebox.askyesnocancel`` qui est trop ambigu lorsqu'on
    mappe Oui/Non sur « registre » / « Excel ». Ici chaque bouton est
    clairement étiqueté.

    Usage :

        dlg = _FormatChoiceDialog(
            self, title="Exporter", prompt="Choisir le format :",
            options=[("registre (.db)", "db", "📦"),
                     ("Excel (.xlsx)",  "xlsx", "📊")],
        )
        self.wait_window(dlg)
        choice = dlg.choice   # "db" | "xlsx" | None
    """

    def __init__(self, master, *, title: str, prompt: str,
                 options: list[tuple[str, str, str]]):
        super().__init__(master)
        self.title(title)
        # Largeur adaptative selon le nombre d'options
        w = max(460, 180 + 160 * len(options))
        self.geometry(f"{w}x220")
        self.resizable(False, False)
        self.transient(master)
        self.after(50, self.grab_set)

        self.choice: str | None = None

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text=prompt,
            font=ctk.CTkFont(size=13),
            anchor="w", justify="left", wraplength=420,
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 16))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=20)
        for i, (label, value, icon) in enumerate(options):
            btn_row.grid_columnconfigure(i, weight=1, uniform="fmt")
            ctk.CTkButton(
                btn_row, text=f"{icon}  {label}",
                height=44, font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda v=value: self._pick(v),
            ).grid(row=0, column=i, padx=(0 if i == 0 else 6, 0), sticky="ew")

        cancel = ctk.CTkButton(
            self, text="Annuler",
            height=30, width=100,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._cancel,
        )
        cancel.grid(row=2, column=0, sticky="e", padx=20, pady=(18, 16))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _e: self._cancel())

    def _pick(self, value: str):
        self.choice = value
        self.destroy()

    def _cancel(self):
        self.choice = None
        self.destroy()


def _ask_format(master, *, title: str, prompt: str,
                options: list[tuple[str, str, str]]) -> str | None:
    """Helper bloquant : retourne la valeur choisie ou None si annulé."""
    dlg = _FormatChoiceDialog(master, title=title, prompt=prompt,
                                options=options)
    master.wait_window(dlg)
    return dlg.choice


class RegistryPanel(ctk.CTkFrame):
    """Panneau Registre (onglet principal)."""

    def __init__(self, master, workspace: Path | None = None, **kwargs):
        super().__init__(master, **kwargs)
        self.workspace = workspace
        self.registry: Registry | None = None
        self._view_mode = "grouped"   # "grouped" | "flat"
        self._current_filter = {}
        self._sessions: list[dict] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_toolbar()
        self._build_filters()
        self._build_table()
        self._build_footer()

    # -- UI Construction ---------------------------------------------------

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        bar.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(bar, text="Registre",
                      font=ctk.CTkFont(size=16, weight="bold"),
                      anchor="w").grid(row=0, column=0, padx=(4, 16))

        # Boutons vue
        self.view_seg = ctk.CTkSegmentedButton(
            bar, values=["Groupé", "Tableau"],
            command=self._on_view_change,
        )
        self.view_seg.set("Groupé")
        self.view_seg.grid(row=0, column=1, padx=(0, 16))

        # Spacer
        ctk.CTkLabel(bar, text="").grid(row=0, column=2)

        # Boutons action
        self.import_btn = ctk.CTkButton(
            bar, text="📥 Importer", height=28, width=110,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_import,
        )
        self.import_btn.grid(row=0, column=3, padx=4)

        self.export_btn = ctk.CTkButton(
            bar, text="📤 Exporter", height=28, width=110,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_export,
        )
        self.export_btn.grid(row=0, column=4, padx=4)

        self.sync_btn = ctk.CTkButton(
            bar, text="🔄 Sync API", height=28, width=110,
            command=self._on_sync_api,
        )
        self.sync_btn.grid(row=0, column=5, padx=4)

        # Bouton "🧹 Nettoyer doublons" : fusionne les entrées du registre
        # qui correspondent à la même nuit (site+point+passage+date) mais
        # ont des ids différents (typiquement après rename de dossier, ou
        # après bascule de PC qui re-scanne avec des chemins différents).
        self.dedup_btn = ctk.CTkButton(
            bar, text="🧹 Doublons", height=28, width=100,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_dedup,
        )
        self.dedup_btn.grid(row=0, column=6, padx=4)

    def _build_filters(self):
        bar = ctk.CTkFrame(self, fg_color=("gray92", "gray20"),
                            corner_radius=8, border_width=1,
                            border_color=("gray80", "gray25"))
        bar.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        # Recherche
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._schedule_refresh())
        self.search_entry = ctk.CTkEntry(
            bar, textvariable=self.search_var, height=28, width=250,
            placeholder_text="🔍 Rechercher contrat, site, série…",
        )
        self.search_entry.grid(row=0, column=0, padx=(10, 8), pady=8)

        # Année
        ctk.CTkLabel(bar, text="Année :").grid(row=0, column=1, padx=(8, 4))
        self.year_var = ctk.StringVar(value="Toutes")
        self.year_menu = ctk.CTkOptionMenu(
            bar, variable=self.year_var, width=100, height=28,
            values=["Toutes"],
            command=lambda _: self._apply_filters(),
        )
        self.year_menu.grid(row=0, column=2, padx=(0, 8))

        # État
        ctk.CTkLabel(bar, text="État :").grid(row=0, column=3, padx=(8, 4))
        self.etat_var = ctk.StringVar(value="Tous")
        self.etat_menu = ctk.CTkOptionMenu(
            bar, variable=self.etat_var, width=140, height=28,
            values=["Tous", "🔴 Brut", "🟠 Préparé", "🟡 En traitement",
                    "🟢 Traité", "⚫ Archivé"],
            command=lambda _: self._apply_filters(),
        )
        self.etat_menu.grid(row=0, column=4, padx=(0, 8))

        # Vues rapides
        ctk.CTkLabel(bar, text="Vue :").grid(row=0, column=5, padx=(8, 4))
        self.quick_view_var = ctk.StringVar(value="—")
        self.quick_view_menu = ctk.CTkOptionMenu(
            bar, variable=self.quick_view_var, width=150, height=28,
            values=["—"],
            command=self._on_quick_view,
        )
        self.quick_view_menu.grid(row=0, column=6, padx=(0, 10))

    def _build_table(self):
        """Zone table/accordéon."""
        self.table_frame = ctk.CTkFrame(self)
        self.table_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        self.table_frame.grid_columnconfigure(0, weight=1)
        self.table_frame.grid_rowconfigure(0, weight=1)

        # Treeview (flat mode)
        columns = ("etat", "source", "sync", "date", "contrat", "site", "point",
                   "pass", "serie", "campaign", "commentaires")
        self.tree = ttk.Treeview(
            self.table_frame, columns=columns, show="headings",
            selectmode="browse",
        )
        self.tree.heading("etat", text="État")
        self.tree.heading("source", text="Src")
        self.tree.heading("sync", text="⬆")
        self.tree.heading("date", text="Date")
        self.tree.heading("contrat", text="Contrat")
        self.tree.heading("site", text="Site")
        self.tree.heading("point", text="Point")
        self.tree.heading("pass", text="Pass")
        self.tree.heading("serie", text="Série")
        self.tree.heading("campaign", text="Campagne")
        self.tree.heading("commentaires", text="Commentaires")

        self.tree.column("etat", width=40, anchor="center")
        self.tree.column("source", width=35, anchor="center")
        self.tree.column("sync", width=32, anchor="center")
        self.tree.column("date", width=90, anchor="center")
        self.tree.column("contrat", width=200)
        self.tree.column("site", width=70, anchor="center")
        self.tree.column("point", width=50, anchor="center")
        self.tree.column("pass", width=40, anchor="center")
        self.tree.column("serie", width=100)
        self.tree.column("campaign", width=140)
        self.tree.column("commentaires", width=180)

        # Tags couleur
        self.tree.tag_configure("not_started", background="#FFE6E6")
        self.tree.tag_configure("prepared", background="#FFE8CC")
        self.tree.tag_configure("in_progress", background="#FFFDE6")
        self.tree.tag_configure("processed", background="#E6FFE6")
        self.tree.tag_configure("archived", background="#E8E8E8")
        self.tree.tag_configure("ghost", foreground="#5a5aa0")  # ghost italic bleu
        self.tree.tag_configure("group_header",
                                 background="#D0D8E0", font=("", 11, "bold"))

        vsb = ttk.Scrollbar(self.table_frame, orient="vertical",
                             command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Double-clic = éditer commentaire
        self.tree.bind("<Double-1>", self._on_double_click)
        # Clic droit = menu contextuel (ghost actions, archive, etc.)
        self.tree.bind("<Button-3>", self._on_right_click)

        # Tri par colonne
        for col in columns:
            self.tree.heading(col, command=lambda c=col: self._sort_by(c))

    def _build_footer(self):
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 8))
        foot.grid_columnconfigure(0, weight=1)

        self.stats_lbl = ctk.CTkLabel(
            foot, text="(registre non chargé)",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
            anchor="w",
        )
        self.stats_lbl.grid(row=0, column=0, sticky="w")

    # -- Chargement / alimentation ----------------------------------------

    def set_workspace(self, workspace: Path | None):
        self.workspace = workspace
        if workspace:
            self.registry = Registry(workspace)
            self._load_quick_views()
            self._populate_year_filter()
            self._apply_filters()
        else:
            self.registry = None

    def feed_from_scan(self, states: list):
        """Alimenter le registre depuis les résultats du scan."""
        if not self.registry:
            return
        self.registry.feed_from_scan(states)
        self._populate_year_filter()
        self._apply_filters()

    def auto_import_suivi(self):
        """Propose d'importer le Suivi Excel s'il est détecté."""
        if not self.workspace or not self.registry:
            return
        # Cherche Suivi analyse Chiros *.xlsx
        candidates = list(self.workspace.glob("Suivi analyse Chiros *.xlsx"))
        if not candidates:
            return
        # Vérifier si déjà importé (check merge_log)
        logs = self.registry.merge_log(limit=50)
        already = any("Suivi" in (l.get("source") or "") for l in logs)
        if already:
            return
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        if messagebox.askyesno(
            "Suivi Excel détecté",
            f"Le fichier suivant a été trouvé :\n{latest.name}\n\n"
            f"Importer les données dans le registre ChiroTool ?\n"
            f"(Aucune modification du fichier Excel.)"):
            try:
                result = self.registry.import_from_suivi_xlsx(latest)
                messagebox.showinfo(
                    "Import terminé",
                    f"{result['imported']} sessions importées, "
                    f"{result['skipped']} lignes ignorées.")
                self._apply_filters()
            except Exception as e:
                messagebox.showerror("Erreur import", str(e))

    # -- Filtres -----------------------------------------------------------

    def _schedule_refresh(self):
        if hasattr(self, "_refresh_after"):
            try:
                self.after_cancel(self._refresh_after)
            except Exception:
                pass
        self._refresh_after = self.after(300, self._apply_filters)

    def _populate_year_filter(self):
        if not self.registry:
            return
        years = set()
        for s in self.registry.all_sessions(include_archived=True):
            d = s.get("date_debut") or ""
            if len(d) >= 4 and d[:4].isdigit():
                years.add(d[:4])
        self.year_menu.configure(values=["Toutes"] + sorted(years, reverse=True))

    def _load_quick_views(self):
        if not self.registry:
            return
        views = self.registry.saved_views()
        names = ["—"] + [v["name"] for v in views]
        self.quick_view_menu.configure(values=names)

    def _on_quick_view(self, name: str):
        if name == "—":
            self.year_var.set("Toutes")
            self.etat_var.set("Tous")
            self.search_var.set("")
            self._apply_filters()
            return
        if not self.registry:
            return
        views = self.registry.saved_views()
        for v in views:
            if v["name"] == name:
                filters = json.loads(v.get("filters") or "{}")
                if filters.get("year_current"):
                    self.year_var.set(str(datetime.now().year))
                etat_filter = filters.get("etat_global")
                if etat_filter:
                    # Map to display
                    etat_to_label = {
                        "not_started": "🔴 Brut",
                        "prepared": "🟠 Préparé",
                        "in_progress": "🟡 En traitement",
                        "processed": "🟢 Traité",
                        "archived": "⚫ Archivé",
                    }
                    if len(etat_filter) == 1:
                        self.etat_var.set(etat_to_label.get(etat_filter[0], "Tous"))
                    else:
                        self.etat_var.set("Tous")  # multi not supported in simple dropdown
                self._apply_filters()
                break

    def _apply_filters(self):
        if not self.registry:
            return
        query = self.search_var.get().strip()
        year = self.year_var.get()
        etat = self.etat_var.get()

        include_archived = etat == "⚫ Archivé"

        if query:
            sessions = self.registry.search(query, include_archived=include_archived)
        else:
            sessions = self.registry.all_sessions(include_archived=include_archived)

        # Filtre année
        if year != "Toutes":
            sessions = [s for s in sessions
                        if (s.get("date_debut") or "")[:4] == year]

        # Filtre état
        etat_map = {
            "🔴 Brut": "not_started",
            "🟠 Préparé": "prepared",
            "🟡 En traitement": "in_progress",
            "🟢 Traité": "processed",
            "⚫ Archivé": "archived",
        }
        if etat in etat_map:
            target = etat_map[etat]
            sessions = [s for s in sessions if s.get("etat_global") == target]

        self._sessions = sessions
        self._render()

    # -- Rendu du tableau --------------------------------------------------

    def _render(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        if self._view_mode == "grouped":
            self._render_grouped()
        else:
            self._render_flat()

        self._update_stats()

    def _render_flat(self):
        for s in self._sessions:
            etat = s.get("etat_global", "not_started")
            pastille = ETAT_LABELS.get(etat, ("?", "?"))[0]
            source_icon = self._source_icon(s.get("source", "local"))
            date = (s.get("date_debut") or "")[:10]
            tags = [etat]
            if s.get("source") == "server":
                tags.append("ghost")
            self.tree.insert(
                "", "end", iid=s["id"],
                values=(
                    pastille, source_icon, self._sync_glyph(s), date,
                    s.get("nom_contrat") or "",
                    s.get("n_site_tadarida") or "",
                    s.get("n_point_fixe") or "",
                    s.get("n_passage") or "",
                    s.get("n_serie") or "",
                    s.get("campaign") or "",
                    s.get("commentaires") or "",
                ),
                tags=tags,
            )

    @staticmethod
    def _source_icon(source: str) -> str:
        return {
            "local":  "💻",     # scanné localement seulement
            "server": "👻",     # sur serveur seulement (ghost)
            "synced": "✓",     # local + serveur (couplé)
        }.get(source, "?")

    @staticmethod
    def _sync_glyph(s: dict) -> str:
        """Indicateur discret de remontée des identifications (colonne ⬆).

        Vide si rien à remonter ; sinon cercle vide (rien envoyé) → partiel →
        plein (tout remonté). Attire l'œil sur les nuits « pas encore remontées ».
        """
        total = s.get("ident_total") or 0
        pushed = s.get("ident_pushed") or 0
        if not total:
            return ""              # feature non utilisée / rien d'envoyable
        if pushed >= total:
            return "●"             # tout remonté
        return "◐" if pushed else "○"   # partiel / rien encore

    def _render_grouped(self):
        by_contrat: dict[str, list[dict]] = {}
        for s in self._sessions:
            key = s.get("nom_contrat") or s.get("campaign") or "(sans contrat)"
            by_contrat.setdefault(key, []).append(s)

        for contrat in sorted(by_contrat):
            sessions = by_contrat[contrat]
            n = len(sessions)
            n_done = sum(1 for s in sessions
                         if s.get("etat_global") == "processed")
            g_pushed = sum(s.get("ident_pushed") or 0 for s in sessions)
            g_total = sum(s.get("ident_total") or 0 for s in sessions)
            remontees = f", {g_pushed}/{g_total} remontées" if g_total else ""
            group_id = f"__group_{contrat}"

            self.tree.insert(
                "", "end", iid=group_id,
                values=("", "", "", "",
                        f"📁 {contrat}  ({n} nuits, {n_done} terminées{remontees})",
                        "", "", "", "", "", ""),
                tags=("group_header",),
                open=True,
            )

            for s in sessions:
                etat = s.get("etat_global", "not_started")
                pastille = ETAT_LABELS.get(etat, ("?", "?"))[0]
                source_icon = self._source_icon(s.get("source", "local"))
                date = (s.get("date_debut") or "")[:10]
                tags = [etat]
                if s.get("source") == "server":
                    tags.append("ghost")
                self.tree.insert(
                    group_id, "end", iid=s["id"],
                    values=(
                        pastille, source_icon, self._sync_glyph(s), date, "",
                        s.get("n_site_tadarida") or "",
                        s.get("n_point_fixe") or "",
                        s.get("n_passage") or "",
                        s.get("n_serie") or "",
                        s.get("campaign") or "",
                        s.get("commentaires") or "",
                    ),
                    tags=tags,
                )

    def _update_stats(self):
        total = len(self._sessions)
        by_etat = {}
        for s in self._sessions:
            e = s.get("etat_global", "?")
            by_etat[e] = by_etat.get(e, 0) + 1
        contrats = len(set(s.get("nom_contrat") or "" for s in self._sessions))

        parts = [f"{total} sessions"]
        parts.append(f"{contrats} contrats")
        for etat_key, (pastille, label) in ETAT_LABELS.items():
            n = by_etat.get(etat_key, 0)
            if n:
                parts.append(f"{pastille} {n} {label.lower()}")
        self.stats_lbl.configure(text="  ·  ".join(parts))

    # -- Vue change --------------------------------------------------------

    def _on_view_change(self, value: str):
        self._view_mode = "grouped" if value == "Groupé" else "flat"
        self._render()

    # -- Tri ---------------------------------------------------------------

    def _sort_by(self, col: str):
        col_map = {
            "etat": "etat_global", "date": "date_debut",
            "contrat": "nom_contrat", "site": "n_site_tadarida",
            "point": "n_point_fixe", "pass": "n_passage",
            "serie": "n_serie", "campaign": "campaign",
            "commentaires": "commentaires",
        }
        key = col_map.get(col, col)
        self._sessions.sort(key=lambda s: str(s.get(key) or ""))
        self._render()

    # -- Édition inline ----------------------------------------------------

    def _on_double_click(self, event):
        sel = self.tree.selection()
        if not sel or sel[0].startswith("__group_"):
            return
        sid = sel[0]
        s = next((s for s in self._sessions if s["id"] == sid), None)
        if not s or not self.registry:
            return

        # Dialog simple : éditer commentaire
        current = s.get("commentaires") or ""
        dlg = ctk.CTkInputDialog(
            text=f"Commentaire pour {sid} :",
            title="Édition",
        )
        new_val = dlg.get_input()
        if new_val is not None and new_val != current:
            self.registry.update_fields(sid, {"commentaires": new_val})
            s["commentaires"] = new_val
            self._render()

    # -- Import / Export ---------------------------------------------------

    def _on_import(self):
        if not self.registry:
            messagebox.showwarning("Registre", "Aucun workspace ouvert.")
            return
        choice = _ask_format(
            self,
            title="Importer",
            prompt="Depuis quelle source veux-tu importer ?",
            options=[
                ("Registre  (.db)", "db", "📦"),
                ("Suivi Excel  (.xlsx)", "xlsx", "📊"),
            ],
        )
        if choice == "db":
            self._import_db()
        elif choice == "xlsx":
            self._import_xlsx()

    def _import_db(self):
        path = filedialog.askopenfilename(
            title="Choisir un registre à fusionner",
            filetypes=[("SQLite", "*.db"), ("Tous", "*")],
        )
        if not path:
            return
        try:
            result = self.registry.merge_from_db(Path(path))
        except Exception as e:
            messagebox.showerror("Erreur fusion", str(e))
            return
        messagebox.showinfo(
            "Fusion terminée",
            f"Ajouts : {result['added']}\n"
            f"Mises à jour : {result['updated']}\n"
            f"Conflits : {result['conflicts']}",
        )
        self._apply_filters()

    def _import_xlsx(self):
        path = filedialog.askopenfilename(
            title="Choisir un fichier Suivi Excel",
            filetypes=[("Excel", "*.xlsx"), ("Tous", "*")],
        )
        if not path:
            return
        try:
            result = self.registry.import_from_suivi_xlsx(Path(path))
        except Exception as e:
            messagebox.showerror("Erreur import", str(e))
            return
        messagebox.showinfo(
            "Import terminé",
            f"{result['imported']} sessions importées\n"
            f"{result['skipped']} lignes ignorées",
        )
        self._apply_filters()

    def _on_export(self):
        if not self.registry:
            return
        choice = _ask_format(
            self,
            title="Exporter",
            prompt="Dans quel format veux-tu exporter le registre ?",
            options=[
                ("Registre  (.db)", "db", "📦"),
                ("Excel  (.xlsx)", "xlsx", "📊"),
                ("CSV  (suivi équipe)", "csv", "📋"),
            ],
        )
        if choice == "db":
            self._export_db()
        elif choice == "xlsx":
            self._export_xlsx()
        elif choice == "csv":
            self._export_csv()

    def _export_csv(self):
        """Export CSV complet avec toutes les colonnes (suivi équipe)."""
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = filedialog.asksaveasfilename(
            title="Exporter le registre en CSV",
            initialfile=f"chirotool_export_{ts}.csv",
            filetypes=[("CSV", "*.csv")],
            defaultextension=".csv",
        )
        if not path:
            return
        try:
            result = self.registry.export_to_csv(Path(path))
            size_kb = result["size_bytes"] / 1024
            messagebox.showinfo(
                "Export CSV",
                f"✓ {result['n_rows']} sessions exportées\n"
                f"   {Path(path).name}\n"
                f"   {size_kb:.1f} Ko · UTF-8 BOM · séparateur ;\n\n"
                f"💡 Pour fusionner les CSV de plusieurs équipiers :\n"
                f"   ouvre-les dans Excel/LibreOffice et concatène, ou\n"
                f"   utilise pandas : df = pd.read_csv(..., sep=';')",
            )
        except Exception as e:
            messagebox.showerror("Erreur export", str(e))

    def _export_db(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = filedialog.asksaveasfilename(
            title="Exporter le registre",
            initialfile=f"registry_export_{ts}.db",
            filetypes=[("SQLite", "*.db")],
            defaultextension=".db",
        )
        if not path:
            return
        try:
            self.registry.export_db(Path(path))
            messagebox.showinfo("Export", f"Registre exporté : {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Erreur export", str(e))

    # -- Déduplication -----------------------------------------------------

    def _on_dedup(self):
        """Détecte et fusionne les doublons du registre.

        Premier appel = dry_run pour montrer ce qui sera fait. Confirmation
        utilisateur → vrai merge + delete des orphelines.
        """
        if not self.registry:
            messagebox.showwarning("Registre", "Aucun workspace ouvert.")
            return
        try:
            report = self.registry.deduplicate(dry_run=True)
        except Exception as e:
            messagebox.showerror("Déduplication", f"Erreur : {e}")
            return
        n_groups = report["groups"]
        n_orphans = report["deleted_orphans"]
        if n_groups == 0 and n_orphans == 0:
            messagebox.showinfo(
                "Pas de doublons",
                "Le registre est déjà propre — aucun doublon ni orpheline détectée.")
            return

        # Construit le détail
        details_lines = []
        for d in report["details"][:15]:
            key = d["key"]
            details_lines.append(
                f"  • site {key[0]} / {key[1]} / Pass{key[2]} / {key[3]}\n"
                f"    → garde « {d['winner_id'][:50]} »\n"
                f"    → fusionne + supprime {len(d['losers_ids'])} doublon(s)"
            )
        if len(report["details"]) > 15:
            details_lines.append(f"  … et {len(report['details']) - 15} autres groupes")

        msg = (
            f"{n_groups} groupe(s) de doublons détecté(s).\n"
            f"{report['merged']} entrée(s) seront fusionnées et supprimées.\n"
            f"{n_orphans} entrée(s) orpheline(s) (sans site/point/date) seront retirées.\n\n"
            + "\n".join(details_lines) +
            "\n\nConfirmer le nettoyage ?\n"
            "(La meilleure entrée de chaque groupe est conservée — celle dont "
            "le dossier existe sur disque, avec les flags les plus avancés.)"
        )
        if not messagebox.askyesno("Nettoyer les doublons ?", msg):
            return
        try:
            report = self.registry.deduplicate(dry_run=False)
            messagebox.showinfo(
                "Nettoyage terminé",
                f"✓ {report['merged']} doublon(s) fusionné(s)\n"
                f"✓ {report['deleted_orphans']} orpheline(s) supprimée(s)",
            )
            self._apply_filters()
        except Exception as e:
            messagebox.showerror("Déduplication", f"Erreur pendant la fusion : {e}")

    # -- Sync API ----------------------------------------------------------

    def _on_sync_api(self):
        if not self.registry:
            return
        from credentials import load_token
        token = load_token()
        if not token:
            messagebox.showwarning(
                "Token API manquant",
                "Aucun token Vigie-Chiro enregistré.\n"
                "Ouvre Préférences → API Vigie-Chiro pour en ajouter un.",
            )
            return

        # Dialog progression + preview
        dlg = SyncPreviewDialog(self, registry=self.registry, token=token)
        self.wait_window(dlg)
        if dlg.applied:
            self._apply_filters()

    # -- Menu contextuel (clic droit) --------------------------------------

    def _on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid or iid.startswith("__group_"):
            return
        self.tree.selection_set(iid)
        s = next((s for s in self._sessions if s["id"] == iid), None)
        if not s or not self.registry:
            return

        import tkinter as tk
        menu = tk.Menu(self, tearoff=0)

        is_ghost = s.get("source") == "server"

        if is_ghost:
            menu.add_command(
                label="📥 Télécharger les observations…",
                command=lambda: self._ghost_download_obs(s))
            menu.add_separator()

        if s.get("archived"):
            menu.add_command(label="📂 Désarchiver",
                             command=lambda: self._toggle_archive(s, False))
        else:
            menu.add_command(label="📦 Archiver",
                             command=lambda: self._toggle_archive(s, True))

        menu.add_command(label="✏ Modifier le commentaire…",
                         command=lambda: self._edit_comment(s))
        menu.add_separator()
        menu.add_command(label="🗑 Retirer du registre",
                         command=lambda: self._remove_entry(s))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
            # Détruit le menu natif pour ne pas en accumuler à chaque clic droit
            try:
                menu.destroy()
            except Exception:
                pass

    def _toggle_archive(self, s: dict, archive: bool):
        if archive:
            self.registry.archive_session(s["id"])
        else:
            self.registry.unarchive_session(s["id"])
        self._apply_filters()

    def _edit_comment(self, s: dict):
        dlg = ctk.CTkInputDialog(
            text=f"Commentaire pour {s['id']} :",
            title="Édition",
        )
        new_val = dlg.get_input()
        if new_val is not None:
            self.registry.update_fields(s["id"], {"commentaires": new_val})
            self._apply_filters()

    def _remove_entry(self, s: dict):
        if messagebox.askyesno(
            "Retirer du registre ?",
            f"Retirer '{s['id']}' du registre local ?\n\n"
            f"(Cette action ne touche pas les fichiers sur disque "
            f"ni la participation sur Vigie-Chiro.)"):
            self.registry.delete_session(s["id"])
            self._apply_filters()

    def _ghost_download_obs(self, s: dict):
        pid = s.get("vigiechiro_participation_id")
        if not pid:
            messagebox.showerror("Erreur",
                                  "Pas d'ID de participation associé.")
            return
        from credentials import load_token
        from vigiechiro_api import VigieChiroClient
        token = load_token()
        if not token:
            return

        # Dossier cible : <workspace>/Ghosts/<numero>_<point>_<date>/
        numero = s.get("n_site_tadarida") or "unknown"
        point = s.get("n_point_fixe") or "unknown"
        date = (s.get("date_debut") or "unknown")[:10]
        dest_dir = self.registry.workspace / "Ghosts" / f"{numero}_{point}_{date}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"participation-{pid}-observations.xlsx"

        def _worker():
            try:
                client = VigieChiroClient(token, source="foreground")
                client.download_observations_as_xlsx(pid, dest)
                self.after(0, lambda: messagebox.showinfo(
                    "Téléchargé",
                    f"xlsx téléchargé :\n{dest}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(
                    "Échec téléchargement", str(e)))

        threading.Thread(target=_worker, daemon=True).start()
        messagebox.showinfo(
            "Téléchargement lancé",
            "Le téléchargement tourne en arrière-plan, tu recevras une "
            "notification en fin.")

    def _export_xlsx(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = filedialog.asksaveasfilename(
            title="Exporter en Excel",
            initialfile=f"registre_chirotool_{ts}.xlsx",
            filetypes=[("Excel", "*.xlsx")],
            defaultextension=".xlsx",
        )
        if not path:
            return
        try:
            self.registry.export_to_xlsx(Path(path))
            messagebox.showinfo("Export", f"Excel exporté : {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Erreur export", str(e))
