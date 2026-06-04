"""
campaign_log.py — journal chronologique au niveau campagne.

Chaque dossier de campagne (= dossier parent des sessions) contient un fichier
``_campaign_log.jsonl`` (JSON Lines, append-only) qui trace **chronologiquement**
toutes les actions appliquées aux sessions qu'il contient.

Objectif de portabilité :
  - Si on déplace ``D:\\Chiros\\MonContrat\\`` sur un autre HDD, on emporte
    avec lui tous les ``_session_manifest.json`` ET le ``_campaign_log.jsonl``.
  - À l'ouverture de l'outil sur le nouveau disque, le scan retrouve tout
    l'historique sans dépendre d'aucune ressource externe.

Format d'une ligne (JSONL = une ligne = un objet JSON complet) :
  {"at": "2026-04-15T10:23:45",
   "tool_version": "0.1",
   "session": "20250903_site212097_Z3_Pass2_enr07",
   "phase": "prep",          # prep | upload | wait | fetch | cleanup | suivi_write
   "action": "rename",
   "status": "ok",           # ok | warning | error | skipped
   "stats": {...},
   "notes": "..."}

Avantages du JSONL :
  - Append-only → écritures concurrentes sûres (1 event = 1 line)
  - Lecture ligne par ligne streamée, pas besoin de tout charger en RAM
  - Grep-friendly depuis n'importe quel shell
  - Reconstructible : perdu le log ? on le régénère depuis les manifestes
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


FILENAME = "_campaign_log.jsonl"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class CampaignLog:
    """Journal d'une campagne. Création paresseuse du fichier au 1er record."""

    def __init__(self, campaign_dir: Path):
        self.dir = Path(campaign_dir).resolve()
        self.path = self.dir / FILENAME

    # -- Écriture ----------------------------------------------------------

    def record(
        self,
        *,
        phase: str,
        action: str,
        session: str | None = None,
        status: str = "ok",
        stats: dict | None = None,
        notes: str | None = None,
        tool_version: str | None = None,
    ) -> None:
        """Écrit une ligne JSONL. Création auto du dossier + fichier."""
        self.dir.mkdir(parents=True, exist_ok=True)
        event: dict[str, Any] = {
            "at": _now_iso(),
            "phase": phase,
            "action": action,
            "status": status,
        }
        if session:
            event["session"] = session
        if tool_version:
            event["tool_version"] = tool_version
        if stats:
            event["stats"] = stats
        if notes:
            event["notes"] = notes

        line = json.dumps(event, ensure_ascii=False, default=str)
        # Append atomique (1 write syscall par ligne → safe)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # -- Lecture -----------------------------------------------------------

    def events(
        self,
        *,
        session: str | None = None,
        phase: str | None = None,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> Iterator[dict]:
        """Itère sur les événements, filtre optionnel."""
        if not self.path.is_file():
            return
        with self.path.open("r", encoding="utf-8") as f:
            n = 0
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if session and ev.get("session") != session:
                    continue
                if phase and ev.get("phase") != phase:
                    continue
                if since:
                    try:
                        ts = datetime.fromisoformat(ev.get("at", ""))
                    except ValueError:
                        continue
                    if ts < since:
                        continue
                yield ev
                n += 1
                if limit and n >= limit:
                    return

    def last_event(
        self,
        *,
        session: str | None = None,
        phase: str | None = None,
        action: str | None = None,
    ) -> dict | None:
        """Retourne le dernier événement matching (lecture en avant, OK car fichiers petits)."""
        last: dict | None = None
        for ev in self.events(session=session, phase=phase):
            if action and ev.get("action") != action:
                continue
            last = ev
        return last

    def count(self, **filters) -> int:
        return sum(1 for _ in self.events(**filters))

    # -- Reconstruction depuis les manifestes (fallback si log perdu) -----

    def rebuild_from_manifests(self, overwrite: bool = False) -> int:
        """
        Reconstruit le journal campagne à partir de tous les ``_session_manifest.json``
        trouvés dans les sous-dossiers. Utilité : récupérer après perte du .jsonl.

        Retourne le nombre d'événements écrits.
        """
        if self.path.exists() and not overwrite:
            return 0
        from manifest import Manifest

        events: list[dict] = []
        for session_dir in sorted(self.dir.iterdir()):
            if not session_dir.is_dir():
                continue
            m = Manifest.load(session_dir)
            if m is None:
                continue
            for a in m.actions:
                events.append({
                    "at": a.at,
                    "phase": a.type,                      # approximatif
                    "action": a.type,
                    "status": "ok",
                    "session": session_dir.name,
                    "stats": a.stats,
                    "tool_version": a.tool_version,
                    "notes": a.notes,
                })
        # Tri chronologique
        events.sort(key=lambda e: e.get("at", ""))
        self.path.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in events) + ("\n" if events else ""),
            encoding="utf-8",
        )
        return len(events)


# ---------------------------------------------------------------------------
# Helper pratique : appel direct depuis pipeline/cleanup/rename/te10 sans
# instancier manuellement
# ---------------------------------------------------------------------------

def log_to_campaign(
    session_dir: Path,
    *,
    phase: str,
    action: str,
    status: str = "ok",
    stats: dict | None = None,
    notes: str | None = None,
    tool_version: str | None = None,
) -> None:
    """Écrit un événement dans le journal de la campagne parente de la session."""
    session_dir = Path(session_dir).resolve()
    campaign_dir = session_dir.parent
    log = CampaignLog(campaign_dir)
    log.record(
        phase=phase, action=action,
        session=session_dir.name,
        status=status, stats=stats, notes=notes,
        tool_version=tool_version,
    )


# ---------------------------------------------------------------------------
# CLI — lecture / reconstruction
# ---------------------------------------------------------------------------

def _cli() -> int:
    import argparse
    import sys

    if sys.stdout is not None and getattr(sys.stdout, "encoding", None):
        if sys.stdout.encoding.lower() != "utf-8":
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

    ap = argparse.ArgumentParser(description="Journal campagne.")
    ap.add_argument("campaign", type=Path, help="dossier de campagne")
    ap.add_argument("--tail", type=int, default=20, help="n dernières lignes (défaut 20)")
    ap.add_argument("--session", help="filtrer sur une session")
    ap.add_argument("--phase", help="filtrer sur une phase")
    ap.add_argument("--rebuild", action="store_true",
                    help="reconstruit le .jsonl depuis les manifestes")
    ap.add_argument("--overwrite", action="store_true",
                    help="écrase si fichier existant (avec --rebuild)")
    args = ap.parse_args()

    log = CampaignLog(args.campaign)

    if args.rebuild:
        n = log.rebuild_from_manifests(overwrite=args.overwrite)
        print(f"✓ {n} événements reconstruits dans {log.path}")
        return 0

    events = list(log.events(session=args.session, phase=args.phase))
    tail = events[-args.tail:]
    print(f"{len(tail)} / {len(events)} événement(s) de {log.path}")
    for e in tail:
        sess = e.get("session", "-")
        stats = e.get("stats") or {}
        stats_s = ("  " + ", ".join(f"{k}={v}" for k, v in list(stats.items())[:3])) if stats else ""
        print(f"  {e.get('at','')}  {e.get('status','?'):<7}  "
              f"{e.get('phase','?'):<8}  {e.get('action','?'):<20}  {sess}{stats_s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
