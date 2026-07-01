"""
manifest.py — boîte noire d'une session.

Chaque dossier de session contient un fichier ``_session_manifest.json`` qui :

  - trace les actions effectuées (renommage, TE×10, nettoyage, upload, ...)
  - stocke les métadonnées validées par l'utilisateur (site, point, passage, ...)
  - stocke les données extraites automatiquement (Summary.txt, fallback noms WAV)
  - persiste même si les WAV sont supprimés plus tard (historique)

Objectifs :
  1. idempotence : un script relancé peut sauter ce qui a déjà été fait
  2. auditabilité : on peut reconstruire ce qui s'est passé
  3. évite de relancer les extractions : on lit le manifest plutôt que de re-parser
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
MANIFEST_FILENAME = "_session_manifest.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Action:
    """Une étape du pipeline (renommage, TE×10, nettoyage, ...).

    ``status`` permet le "Tool Result Closure" : chaque action enregistre
    son résultat même en cas d'erreur (``"error"``) ou vérification échouée
    (``"verify_failed"``), pas seulement les succès. Zéro action fantôme.
    """
    type: str                   # "rename" | "te10" | "cleanup" | "upload" | "analyze" | ...
    at: str                     # ISO8601
    status: str = "ok"          # "ok" | "error" | "verify_failed" | "partial"
    params: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    tool_version: str | None = None
    notes: str | None = None


@dataclass
class Manifest:
    """État persistant d'une session."""
    schema_version: int = SCHEMA_VERSION
    session_id: str | None = None               # stable, dérivé de la clé métier
    canonical_name: str | None = None           # nom de dossier canonique cible
    created_at: str = field(default_factory=_now_iso)
    last_updated_at: str = field(default_factory=_now_iso)

    # Métadonnées validées
    meta: dict[str, Any] = field(default_factory=dict)
    # Données extraites (Summary.txt, fallback noms WAV, etc.)
    extracted: dict[str, Any] = field(default_factory=dict)

    # Historique d'actions
    actions: list[Action] = field(default_factory=list)

    # Drapeaux consolidés (miroir de actions, accès rapide)
    flags: dict[str, bool] = field(
        default_factory=lambda: {
            "renamed": False,
            "te10_done": False,
            "uploaded": False,
            "analyzed": False,
            "cleaned": False,
        }
    )

    # Observations (après téléchargement Vigie-Chiro)
    observations: dict[str, Any] | None = None
    # Stats pré-nettoyage (pour historique une fois les WAV purgés)
    stats_before_cleanup: dict[str, Any] | None = None

    # ---- Persistance -----------------------------------------------------

    @classmethod
    def load(cls, session_root: Path) -> "Manifest | None":
        p = session_root / MANIFEST_FILENAME
        if not p.is_file():
            return None
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        # Reconstruit proprement. Filtre les clés inconnues des actions aussi
        # (forward-compat : une version future peut ajouter un champ à Action ;
        # sans ce filtre, Action(**a) lèverait TypeError et toute la session
        # perdrait son historique).
        action_fields = {f.name for f in Action.__dataclass_fields__.values()}
        actions = []
        for a in data.get("actions", []):
            if isinstance(a, dict):
                try:
                    actions.append(Action(**{k: v for k, v in a.items()
                                             if k in action_fields}))
                except (TypeError, ValueError):
                    continue
        data["actions"] = actions
        # Tolère les clés inconnues (forward-compat)
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def load_or_create(cls, session_root: Path) -> "Manifest":
        m = cls.load(session_root)
        if m is None:
            m = cls()
        return m

    def save(self, session_root: Path) -> Path:
        """Écriture atomique (tmp + replace)."""
        p = session_root / MANIFEST_FILENAME
        p.parent.mkdir(parents=True, exist_ok=True)
        self.last_updated_at = _now_iso()
        data = asdict(self)
        tmp = p.with_suffix(p.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        tmp.replace(p)
        return p

    # ---- API haut niveau --------------------------------------------------

    def record_action(
        self,
        action_type: str,
        params: dict[str, Any] | None = None,
        stats: dict[str, Any] | None = None,
        tool_version: str | None = None,
        notes: str | None = None,
        status: str = "ok",
    ) -> Action:
        a = Action(
            type=action_type,
            at=_now_iso(),
            status=status,
            params=params or {},
            stats=stats or {},
            tool_version=tool_version,
            notes=notes,
        )
        self.actions.append(a)
        # Les flags ne passent à True que si le status est "ok".
        # Une action "error" ou "verify_failed" est consignée mais ne
        # déclare pas l'étape comme faite (idempotence respectée).
        if status == "ok":
            if action_type == "rename":
                self.flags["renamed"] = True
            elif action_type == "te10":
                self.flags["te10_done"] = True
            elif action_type == "upload":
                self.flags["uploaded"] = True
            elif action_type == "analyze":
                self.flags["analyzed"] = True
            elif action_type == "cleanup":
                self.flags["cleaned"] = True
        return a

    def last_action(self, action_type: str) -> Action | None:
        for a in reversed(self.actions):
            if a.type == action_type:
                return a
        return None

    def is_done(self, action_type: str) -> bool:
        flag_map = {
            "rename": "renamed",
            "te10": "te10_done",
            "upload": "uploaded",
            "analyze": "analyzed",
            "cleanup": "cleaned",
        }
        key = flag_map.get(action_type)
        if key is not None:
            # Le flag est la SOURCE DE VÉRITÉ : il n'est posé que sur une action
            # réussie (status="ok"). Un upload/rename/… PARTIEL ou en ERREUR
            # laisse le flag à False → l'étape reste « à reprendre ».
            # NE PAS retomber sur last_action : une action "partial"/"error" est
            # consignée dans self.actions et rendrait l'étape faussement « faite »
            # (bug de reprise d'upload : WAV manquants jamais renvoyés).
            return bool(self.flags.get(key))
        # Types sans flag dédié : on ne considère fait qu'une action RÉUSSIE.
        a = self.last_action(action_type)
        return a is not None and a.status == "ok"

    def set_meta(self, **kwargs) -> None:
        """Met à jour les métadonnées validées (merge non destructif)."""
        for k, v in kwargs.items():
            if v is not None:
                self.meta[k] = v

    def set_extracted(self, key: str, value: Any) -> None:
        self.extracted[key] = value


# ---------------------------------------------------------------------------
# CLI utilitaire : dump rapide d'un manifest existant
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

    ap = argparse.ArgumentParser(description="Affiche le manifest d'une session.")
    ap.add_argument("session", help="chemin du dossier session")
    args = ap.parse_args()

    p = Path(args.session)
    m = Manifest.load(p)
    if m is None:
        print(f"(pas de manifest dans {p})")
        return 1
    print(f"Manifest : {p / MANIFEST_FILENAME}")
    print(f"  Session ID     : {m.session_id}")
    print(f"  Canonical name : {m.canonical_name}")
    print(f"  Created at     : {m.created_at}")
    print(f"  Last updated   : {m.last_updated_at}")
    print(f"  Flags          : {m.flags}")
    if m.meta:
        print("  Meta :")
        for k, v in m.meta.items():
            print(f"    {k}: {v}")
    print(f"  Actions ({len(m.actions)}) :")
    for a in m.actions:
        print(f"    [{a.at}] {a.type}   {a.stats if a.stats else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
