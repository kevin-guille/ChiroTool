"""
gui_history.py — panneau Historique par session.

Fusionne chronologiquement :
  - les actions du ``_session_manifest.json`` de la session
  - les events du ``_campaign_log.jsonl`` de la campagne filtrés sur la session

Affichage : timeline verticale avec icône par type d'action, horodatage,
stats synthétiques, statut (ok/warning/error).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import customtkinter as ctk

from campaign_log import CampaignLog
from chiro_core import SessionState
from manifest import Manifest


# Icône + label humain-lisible par type d'action
ACTION_META = {
    "rename":              ("🏷", "Renommage",       "prep"),
    "te10":                ("⏱", "TE×10",            "prep"),
    "upload":              ("☁", "Upload WAVs",      "upload"),
    "upload_wavs":         ("☁", "Upload WAVs",      "upload"),
    "trigger_compute":     ("▶", "Lancement Tadarida", "upload"),
    "wait_for_completion": ("⏳", "Attente Tadarida", "wait"),
    "fetch_observations":  ("⬇", "Téléchargement obs", "fetch"),
    "download_observations": ("⬇", "Téléchargement obs", "fetch"),
    "cleanup":             ("🧹", "Nettoyage",       "cleanup"),
    "suivi_write":         ("📝", "Suivi Excel",      "suivi"),
}

STATUS_COLORS = {
    "ok":             ("#2ea043", "#3fb950"),
    "warning":        ("#bf8700", "#d29922"),
    "partial":        ("#bf8700", "#d29922"),
    "verify_failed":  ("#b35900", "#e89a3c"),
    "error":          ("#cf222e", "#f85149"),
}

STATUS_LABELS = {
    "ok":             "✓ OK",
    "warning":        "⚠ warning",
    "partial":        "◑ partiel",
    "verify_failed":  "⚠ vérif échouée",
    "error":          "✗ erreur",
}


class HistoryPanel(ctk.CTkFrame):
    """Panneau Historique contextuel à une session."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._session: SessionState | None = None
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Barre du haut
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        header.grid_columnconfigure(0, weight=1)

        self.title_lbl = ctk.CTkLabel(
            header, text="Historique", anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.title_lbl.grid(row=0, column=0, sticky="w")

        self.reload_btn = ctk.CTkButton(
            header, text="⟳", width=36, height=28,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self.refresh,
        )
        self.reload_btn.grid(row=0, column=1)

        # Zone timeline scrollable
        self.timeline = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.timeline.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.timeline.grid_columnconfigure(0, weight=1)

        self._show_empty()

    # -- API publique -------------------------------------------------------

    def set_session(self, session: SessionState | None):
        self._session = session
        self.refresh()

    def refresh(self):
        for w in self.timeline.winfo_children():
            w.destroy()

        if self._session is None:
            self._show_empty()
            return

        events = self._collect_events(self._session)
        if not events:
            self._show_empty(message=(
                "Aucune action enregistrée pour cette session.\n"
                "Le manifest et le journal campagne sont vides.\n"
                "Lance 'Préparer' pour démarrer le pipeline."
            ))
            return

        for i, ev in enumerate(events):
            self._render_event(self.timeline, ev, is_last=(i == len(events) - 1))

    # -- Collecte & fusion ---------------------------------------------------

    def _collect_events(self, s: SessionState) -> list[dict]:
        """Fusionne manifest actions + campaign log, dédoublonne, trie."""
        events: list[dict] = []
        seen_keys: set[tuple] = set()   # (at, action)

        # 1. Manifest actions
        m = Manifest.load(s.path)
        if m:
            for a in m.actions:
                key = (a.at, a.type)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                events.append({
                    "at": a.at,
                    "action": a.type,
                    "status": getattr(a, "status", None) or "ok",
                    "stats": a.stats or {},
                    "notes": a.notes,
                    "source": "manifest",
                })

        # 2. Campaign log filtré sur la session
        campaign_dir = s.path.parent
        log = CampaignLog(campaign_dir)
        for ev in log.events(session=s.name):
            key = (ev.get("at"), ev.get("action"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            events.append({
                "at": ev.get("at", ""),
                "action": ev.get("action", "?"),
                "phase": ev.get("phase"),
                "status": ev.get("status", "ok"),
                "stats": ev.get("stats") or {},
                "notes": ev.get("notes"),
                "source": "campaign_log",
            })

        # Tri chronologique décroissant (plus récent en haut)
        events.sort(key=lambda e: e.get("at", ""), reverse=True)
        return events

    # -- Rendu d'un événement -----------------------------------------------

    def _render_event(self, parent, ev: dict, is_last: bool = False):
        action = ev.get("action", "?")
        icon, label, _phase = ACTION_META.get(action, ("•", action, "?"))
        status = ev.get("status", "ok")
        status_color = STATUS_COLORS.get(status, ("gray40", "gray70"))

        card = ctk.CTkFrame(
            parent,
            fg_color=("gray92", "gray20"),
            corner_radius=8,
            border_width=1,
            border_color=("gray80", "gray25"),
        )
        card.pack(fill="x", expand=True, padx=4, pady=4)
        card.grid_columnconfigure(1, weight=1)

        # Icône
        icon_lbl = ctk.CTkLabel(
            card, text=icon, width=44,
            font=ctk.CTkFont(size=20),
        )
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=(6, 4), pady=6)

        # Titre + statut
        title_line = ctk.CTkFrame(card, fg_color="transparent")
        title_line.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=(8, 0))
        title_line.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            title_line, text=label, anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        status_badge = ctk.CTkLabel(
            title_line,
            text=STATUS_LABELS.get(status, status),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=status_color,
        )
        status_badge.grid(row=0, column=1, sticky="e", padx=(8, 0))

        # Horodatage
        try:
            ts = datetime.fromisoformat(ev["at"])
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            ts_str = ev.get("at", "?")
        ctk.CTkLabel(
            card, text=ts_str, anchor="w",
            font=ctk.CTkFont(size=10),
            text_color=("gray45", "gray65"),
        ).grid(row=1, column=1, sticky="w", padx=(4, 8), pady=(0, 2))

        # Stats (si dispo)
        stats = ev.get("stats") or {}
        if stats:
            stats_text = self._format_stats(action, stats)
            if stats_text:
                ctk.CTkLabel(
                    card, text=stats_text, anchor="w",
                    font=ctk.CTkFont(family="Consolas", size=10),
                    text_color=("gray35", "gray70"),
                    justify="left", wraplength=500,
                ).grid(row=2, column=1, sticky="ew", padx=(4, 8), pady=(0, 8))
            else:
                ctk.CTkLabel(card, text="").grid(row=2, column=1, pady=2)
        else:
            ctk.CTkLabel(card, text="").grid(row=2, column=1, pady=2)

        # Notes (commentaires) si présentes
        notes = ev.get("notes")
        if notes:
            ctk.CTkLabel(
                card, text=f"💬  {notes}", anchor="w",
                font=ctk.CTkFont(size=11),
                text_color=("gray30", "gray75"),
                justify="left", wraplength=500,
            ).grid(row=3, column=1, sticky="ew", padx=(4, 8), pady=(0, 8))

    # -- Formatage stats lisibles ------------------------------------------

    def _format_stats(self, action: str, stats: dict) -> str:
        """Produit un résumé lisible par type d'action."""
        if action == "rename":
            n = stats.get("n_planned") or stats.get("n_wav_found") or "?"
            ok = stats.get("executed") or stats.get("n_renamed") or 0
            consistent = stats.get("serial_consistent")
            c_str = "" if consistent is None else (
                " · série cohérente" if consistent else " · ⚠ série incohérente")
            return f"{ok}/{n} WAV renommés{c_str}"

        if action == "te10":
            src = stats.get("n_source_wavs") or "?"
            seg = stats.get("n_segments") or stats.get("n_planned_segments") or "?"
            wrote = stats.get("written")
            if wrote is not None:
                return f"{src} sources → {seg} segments  ·  {wrote} écrits"
            return f"{src} sources → {seg} segments"

        if action in ("upload", "upload_wavs"):
            n = stats.get("n_wavs") or "?"
            up = stats.get("uploaded") or 0
            fail = stats.get("failed") or 0
            if isinstance(fail, list):
                fail = len(fail)
            return f"{up}/{n} WAV uploadés" + (f"  ·  ⚠ {fail} erreurs" if fail else "")

        if action in ("fetch_observations", "download_observations"):
            n = stats.get("n_files") or "?"
            c = stats.get("n_contacts") or 0
            return f"{n} fichiers  ·  {c} contacts"

        if action == "cleanup":
            kept = stats.get("kept") or stats.get("wav_kept") or 0
            deleted = stats.get("deleted") or stats.get("wav_deleted") or 0
            mb = stats.get("bytes_freed") or stats.get("bytes_deleted") or 0
            if isinstance(mb, (int, float)):
                mb = mb / (1024 * 1024)
            thresholds = stats.get("thresholds") or {}
            t_str = ""
            if thresholds:
                t_str = ("  ·  seuils chiros≥{chiros} ortho≥{orthos} "
                         "mam≥{micromam} oisx≥{oiseaux}").format(**thresholds)
            return f"{kept} gardés, {deleted} supprimés ({mb:.0f} MB){t_str}"

        if action == "wait_for_completion":
            return f"état final : {stats.get('final_state', '?')}"

        # Fallback : résumé compact 3 premières clés
        parts = []
        for k, v in list(stats.items())[:3]:
            if isinstance(v, (dict, list)):
                v = f"[{len(v)}]"
            parts.append(f"{k}={v}")
        return "  ·  ".join(parts)

    def _show_empty(self, message: str | None = None):
        empty = ctk.CTkFrame(self.timeline, fg_color="transparent")
        empty.pack(fill="both", expand=True, pady=80)
        empty.grid_columnconfigure(0, weight=1)

        text = message or "← Sélectionne une session dans la liste"
        ctk.CTkLabel(
            empty, text=text,
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray60"),
            justify="center",
        ).pack()
