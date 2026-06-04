"""
gui_dashboard.py — tableau de bord global (nouvel onglet).

Vue agrégée sur tout le workspace pour pilotage :

  - Progression saison en cours : par contrat, combien de Pass1/Pass2 faits
  - Répartition par campagne : nb de nuits, volume WAV, nb WAV
  - Heatmap mois × année : quand ont eu lieu les campagnes
  - Sources : local / serveur (depuis `registry.sessions.source`)

Implémentation **sans dépendance ajoutée** : graphiques dessinés sur
``tk.Canvas`` natif (rectangles + texte). Garde l'exe léger (pas de
matplotlib à 15 MB). Le tradeoff : pas de zoom/sélection interactive,
mais lisibilité correcte et rendu instantané.

Les stats taxonomiques (répartition chiros/orthos/micromam/oiseaux/noise)
seront ajoutées quand la table ``participation_stats`` sera peuplée par
la Sync API.
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path

import customtkinter as ctk


class DashboardPanel(ctk.CTkFrame):
    """Panneau dashboard transverse (3 cartes de stats)."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.registry = None   # setter via set_registry()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_toolbar()
        self._build_body()

    # -- UI ----------------------------------------------------------------

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar, text="Dashboard",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=(4, 16))

        self.year_var = ctk.StringVar(value=str(datetime.now().year))
        ctk.CTkLabel(bar, text="Saison :",
                      font=ctk.CTkFont(size=11)).grid(row=0, column=2, padx=(0, 4))
        self.year_menu = ctk.CTkOptionMenu(
            bar, variable=self.year_var,
            values=[str(y) for y in range(datetime.now().year + 1, 2019, -1)],
            width=90, command=lambda _v: self.refresh(),
        )
        self.year_menu.grid(row=0, column=3, padx=(0, 8))

        ctk.CTkButton(
            bar, text="⟳ Rafraîchir", height=28, width=110,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self.refresh,
        ).grid(row=0, column=4)

    def _build_body(self):
        # Scrollable frame car les 3 cartes peuvent déborder en hauteur
        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.body.grid_columnconfigure(0, weight=1)

        # Placeholder affiché tant qu'aucun registre n'est branché
        self._placeholder = ctk.CTkLabel(
            self.body,
            text=(
                "(workspace non scanné)\n\n"
                "Ouvre un dossier et clique « Scanner » pour voir le tableau de bord."
            ),
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color=("gray50", "gray60"),
            justify="center",
        )
        self._placeholder.grid(row=0, column=0, sticky="nsew", pady=80)

    def set_registry(self, registry) -> None:
        """Injecte une Registry et rafraîchit automatiquement."""
        self.registry = registry
        self.refresh()

    # -- Refresh -----------------------------------------------------------

    def refresh(self):
        """Re-calcule toutes les stats et redessine les cartes."""
        # Clear body
        for w in self.body.winfo_children():
            w.destroy()

        if self.registry is None:
            self._placeholder = ctk.CTkLabel(
                self.body,
                text="(workspace non scanné)\n\nOuvre un dossier et clique « Scanner ».",
                font=ctk.CTkFont(size=12, slant="italic"),
                text_color=("gray50", "gray60"),
                justify="center",
            )
            self._placeholder.grid(row=0, column=0, sticky="nsew", pady=80)
            return

        try:
            year = int(self.year_var.get())
        except (ValueError, TypeError):
            year = datetime.now().year

        # Carte 1 : progression saison
        self._build_card_season(self.body, row=0, year=year)
        # Carte 2 : volumes par campagne
        self._build_card_campaigns(self.body, row=1)
        # Carte 3 : heatmap mois × année
        self._build_card_heatmap(self.body, row=2)
        # Carte 4 : sources (local / serveur / synced)
        self._build_card_sources(self.body, row=3)

    # =========================================================================
    # Cartes
    # =========================================================================

    def _card_frame(self, parent, row: int, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent, fg_color=("gray96", "gray17"), corner_radius=8,
        )
        card.grid(row=row, column=0, sticky="ew", padx=4, pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

        return card

    # --- Carte 1 : saison en cours par contrat ---------------------------

    def _build_card_season(self, parent, row: int, year: int):
        card = self._card_frame(parent, row, f"🌙  Saison {year} — progression par contrat")

        data = self._fetch_season_per_contract(year)
        if not data:
            ctk.CTkLabel(
                card, text=f"(aucune nuit en {year})",
                font=ctk.CTkFont(size=11, slant="italic"),
                text_color=("gray50", "gray60"), anchor="w",
            ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
            return

        # Pour chaque contrat : 2 barres (Pass1, Pass2) + libellés
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        body.grid_columnconfigure(1, weight=1)

        for i, (contrat, counts) in enumerate(data.items()):
            # Label contrat
            ctk.CTkLabel(
                body, text=contrat[:32] + ("…" if len(contrat) > 32 else ""),
                font=ctk.CTkFont(size=11), anchor="w", width=220,
            ).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=2)

            # Pastilles Pass1 / Pass2 / autres
            passes_line = ctk.CTkFrame(body, fg_color="transparent")
            passes_line.grid(row=i, column=1, sticky="w", pady=2)

            for p in (1, 2):
                n = counts.get(p, 0)
                color = ("#2ea043", "#3fb950") if n > 0 \
                    else ("gray80", "gray35")
                txt = f"Pass{p} ✓ ({n})" if n > 0 else f"Pass{p} —"
                ctk.CTkLabel(
                    passes_line, text=txt,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=color,
                ).pack(side="left", padx=(0, 10))

            # Passages supplémentaires (3+) s'il y en a
            for p in sorted(k for k in counts if k not in (1, 2)):
                ctk.CTkLabel(
                    passes_line, text=f"Pass{p} ({counts[p]})",
                    font=ctk.CTkFont(size=10),
                    text_color=("gray45", "gray60"),
                ).pack(side="left", padx=(0, 10))

    def _fetch_season_per_contract(self, year: int) -> dict[str, dict[int, int]]:
        """{nom_contrat: {passage_num: count}} pour l'année donnée."""
        try:
            conn = self.registry._get_conn()
            rows = conn.execute(
                "SELECT nom_contrat, n_passage FROM sessions "
                "WHERE date_debut LIKE ? AND nom_contrat IS NOT NULL "
                "AND nom_contrat <> '' "
                "ORDER BY nom_contrat",
                (f"{year}%",),
            ).fetchall()
        except Exception:
            return {}
        out: dict[str, dict[int, int]] = {}
        for r in rows:
            c = r["nom_contrat"]
            p = r["n_passage"]
            if p is None:
                continue
            try:
                p = int(p)
            except (TypeError, ValueError):
                continue
            out.setdefault(c, {})
            out[c][p] = out[c].get(p, 0) + 1
        return out

    # --- Carte 2 : volumes par campagne ----------------------------------

    def _build_card_campaigns(self, parent, row: int):
        card = self._card_frame(
            parent, row, "📦  Volumes par campagne (tous contrats)")

        data = self._fetch_campaigns()
        if not data:
            ctk.CTkLabel(
                card, text="(aucune campagne enregistrée)",
                font=ctk.CTkFont(size=11, slant="italic"),
                text_color=("gray50", "gray60"), anchor="w",
            ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
            return

        # Barres horizontales : largeur proportionnelle au nb de nuits
        max_n = max(r["n_sessions"] for r in data)
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        body.grid_columnconfigure(1, weight=1)

        for i, r in enumerate(data[:12]):  # Top 12
            ctk.CTkLabel(
                body, text=(r["campaign"] or "(sans campagne)")[:32],
                font=ctk.CTkFont(size=11), anchor="w", width=220,
            ).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=2)

            # Canvas pour la barre
            bar_canvas = tk.Canvas(body, height=18, bg=self._canvas_bg(),
                                      highlightthickness=0)
            bar_canvas.grid(row=i, column=1, sticky="ew", padx=(0, 8), pady=2)
            body.update_idletasks()
            w = max(body.winfo_width() - 310, 200)
            bar_w = int(w * r["n_sessions"] / max_n) if max_n else 0
            bar_canvas.create_rectangle(
                0, 2, bar_w, 16, fill="#1f6feb", outline="")

            # Libellé à droite
            vol_gb = r["total_bytes"] / (1024 ** 3) if r["total_bytes"] else 0
            txt = f"{r['n_sessions']} nuit(s) · {r['n_wavs']:,} WAV · {vol_gb:.1f} GB"
            ctk.CTkLabel(
                body, text=txt,
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color=("gray40", "gray65"), anchor="w",
            ).grid(row=i, column=2, sticky="w", padx=(0, 0), pady=2)

    def _fetch_campaigns(self) -> list[dict]:
        try:
            conn = self.registry._get_conn()
            rows = conn.execute(
                "SELECT campaign, COUNT(*) AS n_sessions, "
                "SUM(COALESCE(n_wav, 0)) AS n_wavs, "
                "SUM(COALESCE(total_bytes, 0)) AS total_bytes "
                "FROM sessions WHERE source <> 'server' "
                "GROUP BY campaign ORDER BY n_sessions DESC"
            ).fetchall()
        except Exception:
            return []
        return [dict(r) for r in rows]

    # --- Carte 3 : heatmap mois × année ----------------------------------

    def _build_card_heatmap(self, parent, row: int):
        card = self._card_frame(
            parent, row, "📅  Activité mensuelle (nb de nuits)")

        data = self._fetch_heatmap()  # {(year, month): n}
        if not data:
            ctk.CTkLabel(
                card, text="(aucune donnée)",
                font=ctk.CTkFont(size=11, slant="italic"),
                text_color=("gray50", "gray60"), anchor="w",
            ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
            return

        years = sorted({y for y, _m in data.keys()}, reverse=True)[:5]
        max_val = max(data.values()) or 1

        # Canvas : 12 mois × N années, chaque cellule ~36×22 px
        cell_w = 36
        cell_h = 22
        left_margin = 56
        top_margin = 22
        canvas_w = left_margin + cell_w * 12 + 10
        canvas_h = top_margin + cell_h * len(years) + 6

        canvas = tk.Canvas(
            card, width=canvas_w, height=canvas_h,
            bg=self._canvas_bg(), highlightthickness=0,
        )
        canvas.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))

        # Entête mois
        mois = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
        for i, mm in enumerate(mois):
            canvas.create_text(
                left_margin + cell_w * i + cell_w // 2, 10,
                text=mm, fill=self._gray(),
                font=("Segoe UI", 9, "bold"),
            )

        # Cellules
        for r_idx, year in enumerate(years):
            y0 = top_margin + cell_h * r_idx
            canvas.create_text(
                left_margin - 8, y0 + cell_h // 2,
                text=str(year), anchor="e", fill=self._gray(),
                font=("Segoe UI", 10, "bold"),
            )
            for m in range(1, 13):
                n = data.get((year, m), 0)
                if n > 0:
                    # Intensité proportionnelle à n (0..max_val → alpha 0..100%)
                    intensity = min(1.0, n / max_val)
                    color = self._blend_color(intensity)
                else:
                    color = self._canvas_bg_alt()
                x0 = left_margin + cell_w * (m - 1) + 2
                x1 = left_margin + cell_w * m - 2
                y0b = y0 + 2
                y1b = y0 + cell_h - 2
                canvas.create_rectangle(
                    x0, y0b, x1, y1b,
                    fill=color, outline="",
                )
                if n > 0:
                    canvas.create_text(
                        (x0 + x1) // 2, (y0b + y1b) // 2,
                        text=str(n),
                        fill="#ffffff" if intensity > 0.5 else self._gray(),
                        font=("Segoe UI", 9, "bold"),
                    )

    def _fetch_heatmap(self) -> dict[tuple[int, int], int]:
        try:
            conn = self.registry._get_conn()
            rows = conn.execute(
                "SELECT date_debut FROM sessions "
                "WHERE date_debut IS NOT NULL AND date_debut <> ''"
            ).fetchall()
        except Exception:
            return {}
        out: dict[tuple[int, int], int] = {}
        for r in rows:
            d = str(r["date_debut"])
            if len(d) < 7 or d[4] != "-":
                continue
            try:
                year = int(d[:4])
                month = int(d[5:7])
            except ValueError:
                continue
            k = (year, month)
            out[k] = out.get(k, 0) + 1
        return out

    # --- Carte 4 : sources (local / server / synced) ---------------------

    def _build_card_sources(self, parent, row: int):
        card = self._card_frame(
            parent, row, "📂  Sources des sessions enregistrées")

        data = self._fetch_sources()
        if not data:
            ctk.CTkLabel(
                card, text="(aucune session)",
                font=ctk.CTkFont(size=11, slant="italic"),
                text_color=("gray50", "gray60"), anchor="w",
            ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
            return

        total = sum(data.values()) or 1
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        body.grid_columnconfigure(1, weight=1)

        labels = {
            "local":  ("💻 Local uniquement", ("#1f6feb", "#58a6ff")),
            "synced": ("✓ Synchronisé local+serveur", ("#2ea043", "#3fb950")),
            "server": ("👻 Serveur seulement (ghost)", ("#f2a93b", "#d29922")),
        }
        for i, src in enumerate(("local", "synced", "server")):
            n = data.get(src, 0)
            lbl_txt, color = labels[src]
            ctk.CTkLabel(
                body, text=lbl_txt, anchor="w", width=260,
                font=ctk.CTkFont(size=11),
            ).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=2)

            bar = tk.Canvas(body, height=18, bg=self._canvas_bg(),
                              highlightthickness=0)
            bar.grid(row=i, column=1, sticky="ew", padx=(0, 8), pady=2)
            body.update_idletasks()
            w = max(body.winfo_width() - 380, 150)
            bar_w = int(w * n / total)
            # Trouve le hex color pour le rectangle selon l'appearance
            try:
                hex_c = color[0] if ctk.get_appearance_mode() == "Light" \
                    else color[1]
            except Exception:
                hex_c = color[0]
            bar.create_rectangle(0, 2, bar_w, 16, fill=hex_c, outline="")

            pct = 100 * n / total
            ctk.CTkLabel(
                body, text=f"{n}  ({pct:.0f}%)",
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color=("gray40", "gray65"), anchor="w", width=100,
            ).grid(row=i, column=2, sticky="w", pady=2)

    def _fetch_sources(self) -> dict[str, int]:
        try:
            conn = self.registry._get_conn()
            rows = conn.execute(
                "SELECT COALESCE(source, 'local') AS src, COUNT(*) AS n "
                "FROM sessions GROUP BY src"
            ).fetchall()
        except Exception:
            return {}
        return {r["src"]: r["n"] for r in rows}

    # =========================================================================
    # Helpers couleurs (respectent le thème CTk)
    # =========================================================================

    def _canvas_bg(self) -> str:
        """Couleur de fond d'un tk.Canvas dans le thème courant."""
        try:
            mode = ctk.get_appearance_mode()
        except Exception:
            mode = "System"
        if mode == "Dark":
            return "#2b2b2b"
        return "#f2f2f2"

    def _canvas_bg_alt(self) -> str:
        """Cellule vide de la heatmap."""
        try:
            mode = ctk.get_appearance_mode()
        except Exception:
            mode = "System"
        return "#3a3a3a" if mode == "Dark" else "#e5e5e5"

    def _gray(self) -> str:
        try:
            mode = ctk.get_appearance_mode()
        except Exception:
            mode = "System"
        return "#aaaaaa" if mode == "Dark" else "#555555"

    def _blend_color(self, intensity: float) -> str:
        """Dégradé bleu pour la heatmap, intensité ∈ [0, 1]."""
        # Base : bleu moyen (#1f6feb) → mix avec blanc/noir selon intensité
        r0, g0, b0 = 0x1f, 0x6f, 0xeb   # cible max
        r1, g1, b1 = 0xc8, 0xde, 0xff   # cible min (bleu pâle)
        r = int(r1 + (r0 - r1) * intensity)
        g = int(g1 + (g0 - g1) * intensity)
        b = int(b1 + (b0 - b1) * intensity)
        return f"#{r:02x}{g:02x}{b:02x}"
