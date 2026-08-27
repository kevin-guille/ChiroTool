"""
gui_activity.py — onglet « Activité » : graphes par tranche horaire.

Permet de visualiser, pour une ou plusieurs nuits validées, le nombre de
contacts par tranche horaire (15/30/60 minutes), filtrable par taxon.

Source : xlsx d'observations (présents à la racine de chaque session, ou
le suffixe ``_<initiales>.xlsx`` après validation ChiroSurf).

Rendu : graphique linéaire sur ``tk.Canvas`` natif (cohérent avec le
dashboard, zéro dépendance ajoutée).

Cas d'usage :
  - Voir l'activité d'une nuit unique (1 ligne par taxon principal)
  - Cumuler plusieurs nuits sur le même graph pour repérer les patterns
    récurrents (ex : peak Pippip à 22h tous les soirs)
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from activity_graph import (
    aggregate_multi_xlsx,
    cascade_options,
    filter_items,
    list_nights,
    list_passages,
    list_points,
    list_sites,
    list_taxons,
)


def _file_size_kb(path: str) -> float:
    """Retourne la taille du fichier en Ko (utilisé pour le feedback export)."""
    try:
        return Path(path).stat().st_size / 1024
    except Exception:
        return 0.0


# Couleurs des courbes (suite récurrente, accessible aux daltoniens)
_PALETTE = [
    "#1f6feb", "#2ea043", "#f2a93b", "#cf222e", "#9b59b6",
    "#16a085", "#e67e22", "#34495e", "#d35400", "#7f8c8d",
]


class ActivityPanel(ctk.CTkFrame):
    """Panneau "Activité par tranche horaire" — onglet du panneau détail."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.workspace: Path | None = None
        # Cache d'agrégation : recalculé sur changement de filtres
        self._aggregated: dict = {}
        self._all_xlsx: list[Path] = []
        # Sélections actives — toutes ANDées au moment du rendu.
        # Sémantique : set() = "rien coché" → rien à afficher (vs précédemment
        # "rien coché = pas de filtre"). L'initialisation à "tout coché" se
        # fait UNE SEULE FOIS dans _on_loaded, pas à chaque refresh, pour que
        # le clic "Aucun" persiste.
        self._sel_sites: set[str] = set()
        self._sel_points: set[str] = set()
        self._sel_passages: set[int] = set()
        self._sel_nights: set[str] = set()
        self._sel_taxons: set[str] = set()
        self._filters_initialized = False
        self._bin_minutes = 30
        self._only_validated = False
        self._chiros_only = False
        self._observer_taxon = False
        # Mode d'agrégation : "cumul" (toute la sélection sommée) ou
        # "par_point" (1 courbe par point dans la sélection)
        self._group_by_point = False

        self.grid_columnconfigure(0, weight=0)  # panneau filtres
        self.grid_columnconfigure(1, weight=1)  # canvas graphe
        self.grid_rowconfigure(1, weight=1)

        self._build_toolbar()
        self._build_filters_panel()
        self._build_canvas_panel()

    # =========================================================================
    # UI : toolbar
    # =========================================================================

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        bar.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(
            bar, text="Activité",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=(4, 16))

        # Tranche horaire
        ctk.CTkLabel(bar, text="Tranche :",
                      font=ctk.CTkFont(size=11)).grid(row=0, column=1, padx=(0, 4))
        self.bin_var = ctk.StringVar(value="30 min")
        bin_menu = ctk.CTkOptionMenu(
            bar, variable=self.bin_var, width=100,
            values=["15 min", "30 min", "60 min"],
            command=self._on_bin_change,
        )
        bin_menu.grid(row=0, column=2, padx=(0, 8))

        # Identification humaine : validateur_taxon OU observateur_taxon
        self.validated_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            bar, text="Validés humains seulement",
            variable=self.validated_var,
            command=self._on_validated_toggle,
        ).grid(row=0, column=3, padx=(0, 16))

        ctk.CTkButton(
            bar, text="⟳ Recharger", height=28, width=110,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self.refresh,
        ).grid(row=0, column=5, padx=(0, 4))

        # Bouton "Exporter" : capture le graphe + légende en PNG (sans perte).
        # Format unique PNG : qualité parfaite, supporte la transparence, taille
        # raisonnable, ouvrable partout (vs JPG qui flouterait les fines lignes
        # du graphe et JPEG qui est juste un alias).
        ctk.CTkButton(
            bar, text="💾 Exporter PNG", height=28, width=130,
            fg_color=("#1f6feb", "#1f6feb"),
            text_color="white",
            hover_color=("#1158c7", "#1158c7"),
            command=self._on_export_png,
        ).grid(row=0, column=6, padx=(0, 8))

        self.status_lbl = ctk.CTkLabel(
            bar, text="(aucun workspace)",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"), anchor="e",
        )
        self.status_lbl.grid(row=0, column=4, sticky="e", padx=(0, 8))

    # =========================================================================
    # UI : panneau filtres (gauche)
    # =========================================================================

    # Sections du panneau : (clé, titre, recherche ?, repliée par défaut ?)
    _SECTION_DEFS = (
        ("sites", "Sites (carrés)", False, False),
        ("points", "Points", False, True),
        ("passages", "Passages", False, True),
        ("nights", "Nuits", True, False),
        ("taxons", "Taxons", True, False),
    )

    def _build_filters_panel(self):
        side = ctk.CTkFrame(self, fg_color=("gray96", "gray17"),
                              corner_radius=6, width=280)
        side.grid(row=1, column=0, sticky="nsw", padx=(8, 4), pady=(0, 8))
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(0, weight=1)

        # UN SEUL scroll pour tout le panneau. Avant : un scroll externe qui
        # contenait 5 scrolls internes de 110 px → la molette était imprévisible
        # et on lisait 3 lignes à la fois. Les sections sont maintenant de simples
        # frames repliables dans ce scroll unique.
        outer = ctk.CTkScrollableFrame(side, fg_color="transparent", width=260)
        outer.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        outer.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(outer, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="Filtres", anchor="w",
                      font=ctk.CTkFont(size=13, weight="bold")
                      ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="Réinitialiser", width=86, height=22,
                       font=ctk.CTkFont(size=10), fg_color="transparent",
                       text_color=("#2f6bb0", "#5aa0e0"),
                       hover_color=("gray88", "gray28"),
                       command=self._reset_filters).grid(row=0, column=1, sticky="e")

        # Résumé des filtres actifs : voir l'état sans dérouler les 5 sections.
        self.filters_summary_lbl = ctk.CTkLabel(
            outer, text="", anchor="w", justify="left", wraplength=238,
            font=ctk.CTkFont(size=10), text_color=("gray35", "gray65"))
        self.filters_summary_lbl.grid(row=1, column=0, sticky="ew", padx=8, pady=(2, 4))

        self._group_by_point_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            outer, text="Détailler par point",
            variable=self._group_by_point_var,
            command=self._on_group_toggle,
            font=ctk.CTkFont(size=11),
        ).grid(row=2, column=0, sticky="w", padx=8, pady=(2, 2))

        self.chiros_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            outer, text="Chiros seulement",
            variable=self.chiros_only_var,
            command=self._on_chiros_toggle,
            font=ctk.CTkFont(size=11),
        ).grid(row=3, column=0, sticky="w", padx=8, pady=(0, 2))

        self.observer_taxon_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            outer, text="Taxons observateur",
            variable=self.observer_taxon_var,
            command=self._on_observer_toggle,
            font=ctk.CTkFont(size=11),
        ).grid(row=4, column=0, sticky="w", padx=8, pady=(0, 6))

        self._sections: dict[str, dict] = {}
        row = 5
        for key, title, searchable, collapsed in self._SECTION_DEFS:
            row = self._build_section(outer, row, key, title, searchable, collapsed)

        # Compat : les _render_* ciblent le corps de chaque section.
        self.sites_box = self._sections["sites"]["items"]
        self.points_box = self._sections["points"]["items"]
        self.passages_box = self._sections["passages"]["items"]
        self.nights_box = self._sections["nights"]["items"]
        self.taxons_box = self._sections["taxons"]["items"]

    def _build_section(self, parent, row: int, key: str, title: str,
                        searchable: bool, collapsed: bool) -> int:
        """Section repliable : en-tête cliquable (▾/▸ + compteur) + corps."""
        head = ctk.CTkButton(
            parent, text="", height=26, anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("gray91", "gray23"), text_color=("gray10", "gray92"),
            hover_color=("gray84", "gray30"),
            command=lambda k=key: self._toggle_section(k),
        )
        head.grid(row=row, column=0, sticky="ew", padx=4, pady=(5, 0))
        row += 1

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=row, column=0, sticky="ew", padx=2, pady=(0, 2))
        body.grid_columnconfigure(0, weight=1)
        row += 1

        search_var = None
        if searchable:
            search_var = ctk.StringVar(value="")
            ent = ctk.CTkEntry(
                body, textvariable=search_var, height=26,
                placeholder_text="rechercher…", font=ctk.CTkFont(size=11))
            ent.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
            # Re-render de CETTE section seulement (pas de cascade) à la frappe.
            search_var.trace_add(
                "write", lambda *a, k=key: self._on_search_change(k))

        items = ctk.CTkFrame(body, fg_color="transparent")
        items.grid(row=1, column=0, sticky="ew")
        items.grid_columnconfigure(0, weight=1)

        self._sections[key] = {
            "head": head, "body": body, "items": items,
            "title": title, "search": search_var, "collapsed": collapsed,
            "n_sel": 0, "n_total": 0,
        }
        if collapsed:
            body.grid_remove()
        self._update_section_header(key)
        return row

    # -- sections repliables : repli / compteur / recherche -----------------

    def _toggle_section(self, key: str):
        sec = self._sections.get(key)
        if not sec:
            return
        sec["collapsed"] = not sec["collapsed"]
        (sec["body"].grid_remove if sec["collapsed"] else sec["body"].grid)()
        self._update_section_header(key)

    def _update_section_header(self, key: str, n_sel=None, n_total=None):
        sec = self._sections.get(key)
        if not sec:
            return
        if n_sel is not None:
            sec["n_sel"] = n_sel
        if n_total is not None:
            sec["n_total"] = n_total
        arrow = "▸" if sec["collapsed"] else "▾"
        ns, nt = sec["n_sel"], sec["n_total"]
        if nt == 0:
            cnt = "—"
        elif ns >= nt:
            cnt = "tous"
        else:
            cnt = f"{ns} / {nt}"
        sec["head"].configure(text=f"{arrow}  {sec['title']}     {cnt}")

    def _section_query(self, key: str) -> str:
        sec = self._sections.get(key)
        var = sec.get("search") if sec else None
        return var.get() if var else ""

    def _on_search_change(self, key: str):
        # Re-render de CETTE section uniquement (aucune cascade, aucun saut).
        {
            "sites": self._render_sites, "points": self._render_points,
            "passages": self._render_passages, "nights": self._render_nights,
            "taxons": self._render_taxons,
        }.get(key, lambda: None)()

    def _reset_filters(self):
        """Restaure les sélections par défaut (comme au 1er chargement) + vide
        les recherches. Un seul point d'entrée pour « tout remettre à plat »."""
        agg = self._aggregated or {}
        self._sel_sites = set(list_sites(agg))
        self._sel_points = set(list_points(agg))
        self._sel_passages = set(list_passages(agg))
        nights = list_nights(agg)
        self._sel_nights = {nights[-1]} if nights else set()
        self._sel_taxons = {t for t, _ in list_taxons(agg)[:5]}
        for sec in self._sections.values():
            if sec.get("search"):
                sec["search"].set("")
        self._refresh_filters_ui()
        self._redraw()

    def _update_filters_summary(self):
        """Résumé compact des filtres actifs (voir l'état sans dérouler)."""
        if not hasattr(self, "filters_summary_lbl"):
            return
        casc = self._cascade()
        rows = [
            (self._sel_sites, len(list_sites(self._aggregated)), "sites"),
            (self._sel_points, len(casc["points"]), "points"),
            (self._sel_passages, len(casc["passages"]), "passages"),
            (self._sel_nights, len(casc["nights"]), "nuits"),
            (self._sel_taxons,
             len(list_taxons(self._filtered_aggregated(skip_taxon=True))), "taxons"),
        ]
        parts = []
        for sel, total, label in rows:
            if not total:
                continue
            n = len(sel)
            parts.append(f"{label} : {'tous' if n >= total else n}")
        self.filters_summary_lbl.configure(
            text=("Actifs —  " + "   ·   ".join(parts)) if parts else "")

    def _sync_headers(self):
        """MAJ des compteurs d'en-tête des sections (n_sel) + du résumé, sans
        reconstruire les listes — appelé après un clic de case."""
        sel = {"sites": self._sel_sites, "points": self._sel_points,
               "passages": self._sel_passages, "nights": self._sel_nights,
               "taxons": self._sel_taxons}
        for key, sec in self._sections.items():
            total = sec.get("n_total", 0)
            self._update_section_header(key, min(len(sel[key]), total), total)
        self._update_filters_summary()

    # =========================================================================
    # UI : canvas (droite)
    # =========================================================================

    def _build_canvas_panel(self):
        right = ctk.CTkFrame(self, fg_color=("gray96", "gray17"),
                                corner_radius=6)
        right.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=(0, 8))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)

        # Canvas Tk natif (theme-aware via _bg)
        self.canvas = tk.Canvas(
            right, bg=self._canvas_bg(), highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        # Légende sous le graph
        self.legend_frame = ctk.CTkScrollableFrame(
            right, fg_color="transparent", height=80,
        )
        self.legend_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.legend_frame.grid_columnconfigure(0, weight=1)

        # Redessiner sur resize
        self.canvas.bind("<Configure>", lambda _e: self._redraw())

    # =========================================================================
    # Public API
    # =========================================================================

    def set_workspace(self, workspace: Path | None) -> None:
        """Définit le workspace racine et rafraîchit la liste des xlsx."""
        self.workspace = Path(workspace) if workspace else None
        self.refresh()

    def refresh(self):
        """Re-scanne le workspace pour trouver tous les xlsx d'observations,
        recalcule l'agrégation et redessine."""
        if self.workspace is None or not self.workspace.is_dir():
            self.status_lbl.configure(text="(aucun workspace)")
            self._aggregated = {}
            self._refresh_filters_ui()
            self._redraw()
            return

        self.status_lbl.configure(text="scan des xlsx…")
        # Threading pour ne pas bloquer l'UI sur gros workspace
        def _worker():
            xlsx_paths = self._discover_xlsx()
            try:
                aggregated = aggregate_multi_xlsx(
                    xlsx_paths,
                    bin_minutes=self._bin_minutes,
                    use_only_validated=self._only_validated,
                    use_observer_taxon=self._observer_taxon,
                    chiros_only=self._chiros_only,
                )
            except Exception as e:
                self.after(0, lambda: self.status_lbl.configure(
                    text=f"erreur agrégation : {e}",
                    text_color=("#cf222e", "#f85149")))
                return
            self.after(0, lambda: self._on_loaded(xlsx_paths, aggregated))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_loaded(self, xlsx_paths: list[Path], aggregated: dict):
        self._all_xlsx = xlsx_paths
        self._aggregated = aggregated
        n_nights = len(list_nights(aggregated))
        n_contacts = sum(sum(bins) for bins in aggregated.values())
        self.status_lbl.configure(
            text=f"{len(xlsx_paths)} source(s) · {n_nights} nuits · "
                 f"{n_contacts:,} contacts",
            text_color=("gray40", "gray60"),
        )
        # Initialisation **unique** des sélections par défaut. Après ça,
        # un clic « Aucun » de l'utilisateur restera respecté.
        if not self._filters_initialized:
            self._sel_sites = set(list_sites(aggregated))
            # points : tous ceux du(es) site(s) coché(s)
            self._sel_points = set(list_points(aggregated))
            self._sel_passages = set(list_passages(aggregated))
            nights = list_nights(aggregated)
            self._sel_nights = {nights[-1]} if nights else set()  # dernière nuit
            top = list_taxons(aggregated)[:5]
            self._sel_taxons = {t for t, _n in top}
            self._filters_initialized = True
        else:
            # Lors d'un rechargement (changement workspace, toggle validé…),
            # on garde les sélections mais on les intersecte avec ce qui existe.
            self._sel_sites &= set(list_sites(aggregated))
            self._sel_points &= set(list_points(aggregated))
            self._sel_passages &= set(list_passages(aggregated))
            self._sel_nights &= set(list_nights(aggregated))
            self._sel_taxons &= {t for t, _ in list_taxons(aggregated)}
        self._refresh_filters_ui()
        self._redraw()

    def _discover_xlsx(self) -> list[Path]:
        """Scan xlsx d'observations + CSV ``_Vu`` ChiroSurf (issue #4.10).

        Si une session a des ``chirosurf/*_Vu.csv``, on les prend **à la
        place** du xlsx (évite de compter deux fois la même nuit).
        """
        if self.workspace is None:
            return []
        xlsx: list[Path] = []
        sessions_with_vu: set[Path] = set()
        vu_csvs: list[Path] = []
        for p in self.workspace.rglob("*"):
            if not p.is_file():
                continue
            try:
                rel_depth = len(p.relative_to(self.workspace).parts)
                if rel_depth > 6:
                    continue
            except ValueError:
                continue
            low = p.name.lower()
            if p.suffix.lower() == ".csv" and low.endswith("_vu.csv") \
                    and p.parent.name.lower() == "chirosurf":
                vu_csvs.append(p)
                sessions_with_vu.add(p.parent.parent)
                continue
            if p.suffix.lower() != ".xlsx":
                continue
            if "observations" not in low or not low.startswith("participation-"):
                continue
            if "_cleanup" in low or "_backup" in low:
                continue
            xlsx.append(p)
        xlsx = [x for x in xlsx if x.parent not in sessions_with_vu]
        return sorted(xlsx + vu_csvs)

    # =========================================================================
    # Filtres : checkboxes nuits + taxons
    # =========================================================================

    def _cascade(self) -> dict:
        """Options disponibles EN CASCADE selon les sélections amont courantes.
        Une sélection vide (falsy) = pas de contrainte pour cette dimension."""
        return cascade_options(
            self._aggregated,
            sel_sites=(self._sel_sites or None),
            sel_points=(self._sel_points or None),
            sel_passages=(self._sel_passages or None),
        )

    def _refresh_filters_ui(self):
        """Repopule les 5 filtres. N'INITIALISE PAS les sélections (job de
        _on_loaded) mais PURGE les sélections aval devenues indisponibles."""
        self._render_sites()
        self._render_points()
        self._render_passages()
        self._render_nights()
        self._render_taxons()
        self._update_filters_summary()

    def _render_sites(self):
        sites = list_sites(self._aggregated)
        self._update_section_header("sites", len(self._sel_sites & set(sites)),
                                    len(sites))
        shown = filter_items(sites, self._section_query("sites"),
                             label_fn=lambda s: f"#{s}")
        self._render_checkbox_box(
            self.sites_box, shown, self._sel_sites,
            on_toggle=self._on_site_toggle,
            select_all_cb=lambda v: self._set_filter_all("sites", v),
            label_fn=lambda s: f"#{s}",
        )

    def _render_points(self):
        # Points limités aux sites sélectionnés ; purge des points orphelins.
        pts = self._cascade()["points"]
        self._sel_points &= set(pts)
        self._update_section_header("points", len(self._sel_points), len(pts))
        self._render_checkbox_box(
            self.points_box, pts, self._sel_points,
            on_toggle=self._on_point_toggle,
            select_all_cb=lambda v: self._set_filter_all("points", v),
        )

    def _render_passages(self):
        pas = self._cascade()["passages"]
        self._sel_passages &= set(pas)
        self._update_section_header("passages", len(self._sel_passages), len(pas))
        self._render_checkbox_box(
            self.passages_box, pas, self._sel_passages,
            on_toggle=self._on_passage_toggle,
            select_all_cb=lambda v: self._set_filter_all("passages", v),
            label_fn=lambda p: "(inconnu)" if p is None else f"Pass{p}",
        )

    def _render_nights(self):
        nights = self._cascade()["nights"]
        self._sel_nights &= set(nights)
        self._update_section_header("nights", len(self._sel_nights), len(nights))
        shown = filter_items(list(reversed(nights)), self._section_query("nights"))
        # Raccourci « Dernière nuit » en plus de Tout/Aucun.
        self._render_checkbox_box(
            self.nights_box, shown, self._sel_nights,
            on_toggle=self._on_night_toggle,
            select_all_cb=lambda v: self._set_filter_all("nights", v),
            mono=True,
            actions=(("Dernière", self._select_last_night),) if nights else (),
        )

    def _select_last_night(self):
        nights = self._cascade()["nights"]
        if nights:
            self._sel_nights = {nights[-1]}
            self._refresh_filters_ui()
            self._redraw()

    def _render_taxons(self):
        # Taxons avec compteur respectant les autres filtres (sites/points/
        # passages/nuits). On NE purge PAS la sélection (un taxon réapparaît si
        # on élargit les filtres). Plus de troncature à 50 : la recherche remplace.
        taxons_all = list_taxons(self._filtered_aggregated(skip_taxon=True),
                                    min_total=1)
        counts = dict(taxons_all)
        codes = [t for t, _ in taxons_all]
        self._update_section_header("taxons", len(self._sel_taxons & set(codes)),
                                    len(codes))
        shown = filter_items(codes, self._section_query("taxons"))
        self._render_checkbox_box(
            self.taxons_box, shown, self._sel_taxons,
            on_toggle=self._on_taxon_toggle,
            select_all_cb=None,
            label_fn=lambda t: f"{t}  ({counts.get(t, 0)})",
            actions=(("Top 5", lambda: self._select_top_taxons(5)),
                     ("Aucun", lambda: self._select_all_taxons(False))),
        )

    def _render_checkbox_box(self, box, items, selection,
                               *, on_toggle, select_all_cb=None,
                               label_fn=str, mono: bool = False,
                               actions: tuple = ()):
        """Repopule une box de cases à cocher. ``select_all_cb`` → boutons
        Tout/Aucun ; ``actions`` = ((libellé, callback), …) supplémentaires."""
        for w in box.winfo_children():
            w.destroy()
        if not items:
            ctk.CTkLabel(
                box, text="(aucun résultat)",
                font=ctk.CTkFont(size=10, slant="italic"),
                text_color=("gray50", "gray60"),
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            return
        bar = ctk.CTkFrame(box, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(2, 4))
        buttons: list = []
        if select_all_cb is not None:
            buttons += [("Tout", lambda: select_all_cb(True)),
                        ("Aucun", lambda: select_all_cb(False))]
        buttons += list(actions)
        for label, cb in buttons:
            ctk.CTkButton(bar, text=label, width=54, height=20,
                           font=ctk.CTkFont(size=10),
                           fg_color=("gray85", "gray25"),
                           text_color=("gray15", "gray90"),
                           hover_color=("gray75", "gray35"),
                           command=cb).pack(side="left", padx=2)

        font = ctk.CTkFont(family="Consolas" if mono else None, size=11)
        for i, item in enumerate(items):
            var = ctk.BooleanVar(value=(item in selection))
            ctk.CTkCheckBox(
                box, text=label_fn(item), variable=var, font=font,
                command=lambda it=item, v=var: on_toggle(it, v),
            ).grid(row=i + 1, column=0, sticky="w", padx=8, pady=1)

    def _set_filter_all(self, kind: str, select: bool):
        """Tout/Aucun générique pour les filtres sites/points/passages/nights."""
        if kind == "sites":
            self._sel_sites = set(list_sites(self._aggregated)) if select else set()
            # Reset points pour qu'ils soient recalculés selon nouveaux sites
            self._sel_points = set()
        elif kind == "points":
            if self._sel_sites:
                pts = {p for s in self._sel_sites
                       for p in list_points(self._aggregated, s)}
            else:
                pts = set(list_points(self._aggregated))
            self._sel_points = pts if select else set()
        elif kind == "passages":
            self._sel_passages = set(list_passages(self._aggregated)) \
                if select else set()
        elif kind == "nights":
            self._sel_nights = set(list_nights(self._aggregated)) \
                if select else set()
        self._refresh_filters_ui()
        self._redraw()

    def _on_site_toggle(self, site: str, var: ctk.BooleanVar):
        if var.get():
            self._sel_sites.add(site)
        else:
            self._sel_sites.discard(site)
        # Cascade : sites → points → passages → nuits → taxons (on ne re-rend
        # que l'aval pour éviter de reconstruire la liste Sites elle-même).
        self._render_points()
        self._render_passages()
        self._render_nights()
        self._render_taxons()
        self._sync_headers()
        self._redraw()

    def _on_point_toggle(self, point: str, var: ctk.BooleanVar):
        if var.get():
            self._sel_points.add(point)
        else:
            self._sel_points.discard(point)
        self._render_passages()
        self._render_nights()
        self._render_taxons()
        self._sync_headers()
        self._redraw()

    def _on_passage_toggle(self, passage: int, var: ctk.BooleanVar):
        if var.get():
            self._sel_passages.add(passage)
        else:
            self._sel_passages.discard(passage)
        self._render_nights()
        self._render_taxons()
        self._sync_headers()
        self._redraw()

    def _on_group_toggle(self):
        self._group_by_point = bool(self._group_by_point_var.get())
        self._sync_headers()
        self._redraw()

    def _select_all_taxons(self, select: bool):
        if select:
            self._sel_taxons = {t for t, _ in list_taxons(
                self._filtered_aggregated(skip_taxon=True))}
        else:
            self._sel_taxons = set()
        self._refresh_filters_ui()
        self._redraw()

    def _filtered_aggregated(self, *, skip_taxon: bool = False,
                              skip_night: bool = False) -> dict:
        """Renvoie une vue filtrée de ``_aggregated`` selon les sélections.

        Sémantique stricte : un filtre vide = "rien dans cette dimension"
        → rien à afficher. L'utilisateur initialise via "Tout" lors du
        premier chargement (fait par _on_loaded).
        """
        out = {}
        for key, bins in self._aggregated.items():
            if len(key) < 5:
                continue
            site, point, passage, night, taxon = key
            # Sites : "?" toléré uniquement si site "?" est dans la sélection
            if site not in self._sel_sites:
                continue
            if point not in self._sel_points:
                continue
            if passage not in self._sel_passages:
                continue
            if not skip_night and night not in self._sel_nights:
                continue
            if not skip_taxon and taxon not in self._sel_taxons:
                continue
            out[key] = bins
        return out

    def _select_top_taxons(self, n: int):
        self._sel_taxons = {t for t, _ in list_taxons(self._aggregated)[:n]}
        self._refresh_filters_ui()
        self._redraw()

    def _on_night_toggle(self, night: str, var: ctk.BooleanVar):
        if var.get():
            self._sel_nights.add(night)
        else:
            self._sel_nights.discard(night)
        self._render_taxons()   # les compteurs de taxons dépendent des nuits
        self._sync_headers()
        self._redraw()

    def _on_taxon_toggle(self, taxon: str, var: ctk.BooleanVar):
        if var.get():
            self._sel_taxons.add(taxon)
        else:
            self._sel_taxons.discard(taxon)
        self._sync_headers()
        self._redraw()

    def _on_bin_change(self, value: str):
        bins = {"15 min": 15, "30 min": 30, "60 min": 60}
        self._bin_minutes = bins.get(value, 30)
        self.refresh()

    def _on_validated_toggle(self):
        self._only_validated = bool(self.validated_var.get())
        self.refresh()

    def _on_chiros_toggle(self):
        self._chiros_only = bool(self.chiros_only_var.get())
        self.refresh()

    def _on_observer_toggle(self):
        self._observer_taxon = bool(self.observer_taxon_var.get())
        self.refresh()

    # =========================================================================
    # Export PNG
    # =========================================================================

    def _on_export_png(self):
        """Exporte le graphe en PNG en redessinant proprement sur PIL.

        Bug évité : ImageGrab capture l'écran et peut tomber sur du noir si
        le canvas Tk est masqué, en hardware-accel ou si le rendu Windows
        a une race condition. La nouvelle implémentation re-dessine
        intégralement le graphe sur une PIL.Image (titre + axes + courbes
        + légende), sans dépendance à l'état affiché de la fenêtre.
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            messagebox.showerror(
                "Export PNG impossible",
                "Pillow (PIL) n'est pas installé. Réinstalle ChiroTool ou\n"
                "exécute : pip install Pillow",
            )
            return

        if not self._aggregated:
            messagebox.showinfo(
                "Rien à exporter",
                "Aucune donnée chargée. Sélectionne d'abord un workspace "
                "contenant des xlsx d'observations.",
            )
            return
        if not self._sel_nights or not self._sel_taxons:
            messagebox.showinfo(
                "Sélection vide",
                "Coche au moins une nuit et un taxon pour avoir un graphe "
                "à exporter.",
            )
            return

        from datetime import datetime
        from tkinter import filedialog
        default_name = f"activite_{datetime.now():%Y%m%d_%H%M%S}.png"
        path = filedialog.asksaveasfilename(
            title="Exporter le graphe en PNG",
            defaultextension=".png",
            filetypes=[("Image PNG", "*.png")],
            initialfile=default_name,
            parent=self,
        )
        if not path:
            return

        try:
            img = self._render_to_pil(width=1400, height=800)
            img.save(path, "PNG", optimize=True)
            messagebox.showinfo(
                "Export réussi",
                f"Graphe exporté :\n{path}\n\n"
                f"Dimensions : {img.size[0]}×{img.size[1]} px\n"
                f"Taille : {round(_file_size_kb(path), 1)} Ko",
            )
        except Exception as e:
            import traceback
            messagebox.showerror(
                "Export PNG impossible",
                f"Erreur pendant le rendu :\n{e}\n\n"
                f"Détails :\n{traceback.format_exc()[:400]}",
            )

    def _render_to_pil(self, width: int = 1400, height: int = 800):
        """Re-dessine le graphe d'activité sur une PIL.Image (export PNG).

        Indépendant de Tk : pas de capture écran, donc pas de risque
        d'image noire ou de fenêtre masquée. Reproduit la même logique
        que _redraw mais sur ImageDraw.
        """
        from PIL import Image, ImageDraw, ImageFont

        # Image fond blanc (les rapports impriment mieux en clair que
        # le thème dark — on force un rendu "publication")
        img = Image.new("RGB", (width, height), color="#ffffff")
        draw = ImageDraw.Draw(img)

        # Polices : essaye Segoe UI (Windows) puis fallback générique.
        def _load_font(size: int):
            for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
                try:
                    return ImageFont.truetype(name, size)
                except (OSError, IOError):
                    continue
            return ImageFont.load_default()

        font_title = _load_font(22)
        font_sub = _load_font(13)
        font_axis = _load_font(11)
        font_legend = _load_font(13)

        # --- 1. En-tête : titre + ligne filtres résumés
        title = "Activité par tranche horaire"
        sub_parts = []
        if self._sel_sites:
            sites_str = ", ".join(f"#{s}" for s in sorted(self._sel_sites))
            sub_parts.append(f"site(s) : {sites_str}")
        if self._sel_points:
            sub_parts.append(f"points : {', '.join(sorted(self._sel_points))}")
        if self._sel_passages:
            sub_parts.append(
                f"passage(s) : {', '.join(f'Pass{p}' for p in sorted(self._sel_passages) if p is not None)}")
        if self._sel_nights:
            nights = sorted(self._sel_nights)
            if len(nights) == 1:
                sub_parts.append(f"nuit : {nights[0]}")
            else:
                sub_parts.append(f"{len(nights)} nuits ({nights[0]} → {nights[-1]})")
        sub_parts.append(f"tranche : {self._bin_minutes} min")
        if self._only_validated:
            sub_parts.append("validés humains uniquement")
        sub_text = "  ·  ".join(sub_parts)

        draw.text((30, 18), title, fill="#1a1a1a", font=font_title)
        draw.text((30, 56), sub_text, fill="#555555", font=font_sub)

        # --- 2. Calcul des courbes (même logique que _redraw)
        nbins = 1440 // self._bin_minutes
        per_curve: dict[str, list[int]] = {}
        filtered = self._filtered_aggregated()
        for key, bins in filtered.items():
            site, point, passage, night, taxon = key
            curve_key = f"{taxon} · {point}" if self._group_by_point else taxon
            if curve_key not in per_curve:
                per_curve[curve_key] = [0] * nbins
            for i, n in enumerate(bins):
                if i < len(per_curve[curve_key]):
                    per_curve[curve_key][i] += n

        # --- 3. Zone du graphe
        margin_left = 70
        margin_right = 30
        margin_top = 110
        margin_bottom = 130   # garde de la place pour la légende
        gx0 = margin_left
        gy0 = margin_top
        gx1 = width - margin_right
        gy1 = height - margin_bottom

        if not per_curve or all(sum(b) == 0 for b in per_curve.values()):
            draw.text(
                ((gx0 + gx1) // 2 - 100, (gy0 + gy1) // 2),
                "Aucune donnée à afficher",
                fill="#888888", font=font_sub,
            )
            return img

        max_y = max(max(b) if b else 0 for b in per_curve.values())
        if max_y < 1:
            max_y = 1
        y_step = self._nice_step(max_y, target_count=5)
        y_top = (max_y // y_step + 1) * y_step

        # Cadre + grille horizontale
        for i in range(0, y_top + 1, y_step):
            y = int(gy1 - (i / y_top) * (gy1 - gy0))
            draw.line([(gx0, y), (gx1, y)], fill="#d8d8d8", width=1)
            draw.text((gx0 - 10, y - 8), str(i), fill="#555555",
                       anchor="rt", font=font_axis)

        # Axe X : 18h → 8h
        order = list(range(18 * 60, 24 * 60, self._bin_minutes)) \
              + list(range(0, 8 * 60, self._bin_minutes))
        order_n = len(order)
        for i, mins in enumerate(order):
            if mins % 60 != 0:
                continue
            x = int(gx0 + (i / order_n) * (gx1 - gx0))
            draw.line([(x, gy0), (x, gy1)], fill="#d8d8d8", width=1)
            draw.text((x, gy1 + 5), f"{mins // 60:02d}h",
                       fill="#555555", anchor="mt", font=font_axis)

        # Cadre extérieur
        draw.rectangle([gx0, gy0, gx1, gy1], outline="#555555", width=1)

        # --- 4. Tracé des courbes
        legend_data: list[tuple[str, str]] = []
        sorted_keys = sorted(per_curve.keys())
        for idx, curve_key in enumerate(sorted_keys):
            bins = per_curve[curve_key]
            color = _PALETTE[idx % len(_PALETTE)]
            legend_data.append((curve_key, color))

            pts = []
            for i, mins in enumerate(order):
                bidx = mins // self._bin_minutes
                v = bins[bidx] if bidx < len(bins) else 0
                x = int(gx0 + (i / max(1, order_n - 1)) * (gx1 - gx0))
                y = int(gy1 - (v / y_top) * (gy1 - gy0))
                pts.append((x, y))
            if len(pts) >= 2:
                draw.line(pts, fill=color, width=2, joint="curve")

        # --- 5. Légende sous le graphe
        leg_y = gy1 + 40
        leg_x = gx0
        leg_box_w = 16
        leg_pad = 24
        max_x = gx1
        for label, color in legend_data:
            # Carré couleur
            draw.rectangle([leg_x, leg_y + 2, leg_x + leg_box_w, leg_y + 14],
                            fill=color, outline=None)
            # Label
            draw.text((leg_x + leg_box_w + 6, leg_y), label,
                       fill="#1a1a1a", font=font_legend)
            # Avance horizontalement
            try:
                bbox = font_legend.getbbox(label)
                txt_w = bbox[2] - bbox[0]
            except Exception:
                txt_w = len(label) * 7
            leg_x += leg_box_w + 6 + txt_w + leg_pad
            if leg_x > max_x - 100:
                leg_x = gx0
                leg_y += 22

        # --- 6. Pied de page : signature
        from datetime import datetime as _dt
        from version import __version__
        footer = (f"généré par ChiroTool v{__version__} · "
                  f"{_dt.now():%Y-%m-%d %H:%M}")
        draw.text((30, height - 22), footer, fill="#999999", font=font_axis)

        return img

    # =========================================================================
    # Rendu canvas
    # =========================================================================

    def _empty_reason(self) -> str:
        """Message contextuel quand le graphe est vide : nomme la 1re dimension
        de filtre vide (au lieu du générique « nuit et taxon » trompeur quand
        c'est en fait Points/Sites qui a été vidé via « Aucun »)."""
        if not self._aggregated:
            return "Aucune donnée d'observation trouvée dans l'espace de travail."
        for sel, label in (
            (self._sel_sites, "site"),
            (self._sel_points, "point"),
            (self._sel_passages, "passage"),
            (self._sel_nights, "nuit"),
            (self._sel_taxons, "taxon"),
        ):
            if not sel:
                return (f"Aucun {label} sélectionné.\n"
                        f"Coche au moins un {label} dans la colonne de gauche.")
        return ("Aucun contact pour cette combinaison de filtres.\n"
                "Élargis la sélection (colonne de gauche).")

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        # Met à jour la couleur de fond selon le thème
        try:
            c.configure(bg=self._canvas_bg())
        except Exception:
            pass

        w = c.winfo_width() or 800
        h = c.winfo_height() or 400

        # Récupère les courbes filtrées (sites/points/passages/nights/taxons)
        # et les cumule selon le mode d'agrégation :
        #   - cumul par défaut       → clé de courbe = taxon
        #   - "Détailler par point"  → clé de courbe = "taxon · point"
        nbins = 1440 // self._bin_minutes
        per_curve: dict[str, list[int]] = {}

        filtered = self._filtered_aggregated()
        for key, bins in filtered.items():
            site, point, passage, night, taxon = key
            if self._group_by_point:
                curve_key = f"{taxon} · {point}"
            else:
                curve_key = taxon
            if curve_key not in per_curve:
                per_curve[curve_key] = [0] * nbins
            cur = per_curve[curve_key]
            for i, n in enumerate(bins):
                if i < len(cur):
                    cur[i] += n
        per_taxon = per_curve  # garde le nom de variable historique en interne

        # Zone du graph (marges)
        margin_left = 50
        margin_right = 18
        margin_top = 20
        margin_bottom = 36
        gx0 = margin_left
        gy0 = margin_top
        gx1 = w - margin_right
        gy1 = h - margin_bottom
        if gx1 - gx0 < 60 or gy1 - gy0 < 40:
            return  # trop petit pour dessiner

        # Si rien à dessiner : message centré CONTEXTUEL (nomme la dimension vide)
        if not per_taxon or all(sum(bins) == 0 for bins in per_taxon.values()):
            c.create_text(
                (gx0 + gx1) // 2, (gy0 + gy1) // 2,
                text=self._empty_reason(),
                fill=self._gray(),
                font=("Segoe UI", 11),
                justify="center",
            )
            self._refresh_legend({})
            return

        # Échelle Y : max sur tous les taxons sélectionnés, arrondi sup
        max_y = max(max(bins) if bins else 0 for bins in per_taxon.values())
        if max_y < 1:
            max_y = 1
        # Joli "step" pour les graduations
        y_step = self._nice_step(max_y, target_count=5)
        y_top = (max_y // y_step + 1) * y_step

        # Grille + axes
        # Axe Y
        for i in range(0, y_top + 1, y_step):
            y = gy1 - (i / y_top) * (gy1 - gy0)
            c.create_line(gx0, y, gx1, y, fill=self._grid_color(), dash=(2, 4))
            c.create_text(gx0 - 6, y, text=str(i),
                            fill=self._gray(), anchor="e",
                            font=("Segoe UI", 9))

        # Axe X : graduations toutes les 2h en partant de minuit
        # Ordre de l'axe : on tourne pour mettre 18h à gauche, 8h à droite
        # (typique pour visualiser une nuit chiroptère)
        order = list(range(18 * 60, 24 * 60, self._bin_minutes)) \
              + list(range(0, 8 * 60, self._bin_minutes))
        order_n = len(order)
        if order_n == 0:
            return

        for i, mins in enumerate(order):
            if mins % 60 != 0:
                continue
            x = gx0 + (i / order_n) * (gx1 - gx0)
            hh = mins // 60
            label = f"{hh:02d}h"
            c.create_line(x, gy0, x, gy1, fill=self._grid_color(),
                            dash=(2, 4))
            c.create_text(x, gy1 + 14, text=label,
                            fill=self._gray(), font=("Segoe UI", 9))

        # Cadre
        c.create_rectangle(gx0, gy0, gx1, gy1,
                           outline=self._gray(), width=1)

        # Tracé des courbes
        legend_data: dict[str, str] = {}
        # Ordre fixe pour stabilité des couleurs
        sorted_taxons = sorted(per_taxon.keys())
        for tx_idx, taxon in enumerate(sorted_taxons):
            bins = per_taxon[taxon]
            # Réordonne selon order (18h→8h)
            ordered_vals = []
            for mins in order:
                bidx = mins // self._bin_minutes
                v = bins[bidx] if bidx < len(bins) else 0
                ordered_vals.append(v)
            color = _PALETTE[tx_idx % len(_PALETTE)]
            legend_data[taxon] = color

            # Trace la ligne
            pts = []
            for i, v in enumerate(ordered_vals):
                x = gx0 + (i / max(1, order_n - 1)) * (gx1 - gx0)
                y = gy1 - (v / y_top) * (gy1 - gy0)
                pts.extend([x, y])
            if len(pts) >= 4:
                c.create_line(*pts, fill=color, width=2, smooth=False)

        self._refresh_legend(legend_data)

    def _refresh_legend(self, taxon_color: dict[str, str]):
        for w in self.legend_frame.winfo_children():
            w.destroy()
        if not taxon_color:
            return
        # Une rangée flow horizontal
        row_frame = ctk.CTkFrame(self.legend_frame, fg_color="transparent")
        row_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=2)
        col = 0
        for taxon, color in taxon_color.items():
            chip = ctk.CTkFrame(row_frame, fg_color="transparent")
            chip.grid(row=0, column=col, padx=(0, 14), pady=2, sticky="w")
            sw = tk.Canvas(chip, width=14, height=14,
                            bg=self._canvas_bg(), highlightthickness=0)
            sw.create_rectangle(0, 4, 14, 10, fill=color, outline="")
            sw.pack(side="left")
            ctk.CTkLabel(
                chip, text=taxon,
                font=ctk.CTkFont(size=11),
            ).pack(side="left", padx=(4, 0))
            col += 1

    # =========================================================================
    # Helpers visuels
    # =========================================================================

    def _canvas_bg(self) -> str:
        try:
            mode = ctk.get_appearance_mode()
        except Exception:
            mode = "System"
        return "#2b2b2b" if mode == "Dark" else "#fafafa"

    def _gray(self) -> str:
        try:
            mode = ctk.get_appearance_mode()
        except Exception:
            mode = "System"
        return "#aaaaaa" if mode == "Dark" else "#555555"

    def _grid_color(self) -> str:
        try:
            mode = ctk.get_appearance_mode()
        except Exception:
            mode = "System"
        return "#3a3a3a" if mode == "Dark" else "#d8d8d8"

    @staticmethod
    def _nice_step(max_value: int, target_count: int = 5) -> int:
        """Détermine un pas d'axe Y "rond" (1, 2, 5, 10, 20, 50, …)."""
        if max_value <= 0:
            return 1
        rough = max_value / target_count
        magnitude = 10 ** int(len(str(int(rough))) - 1)
        for mult in (1, 2, 5, 10):
            step = mult * magnitude
            if step >= rough:
                return max(1, step)
        return max(1, int(rough))
