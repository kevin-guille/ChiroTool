"""
export_sessions.py — export portable d'un sous-ensemble de sessions.

Fonctions pures (sans GUI) pour copier Data / Data_k + métadonnées vers une
arborescence relative rejouable (clé USB, partage collègue).

Usage typique
-------------
    from export_sessions import ExportSessionSpec, plan_export, run_export

    specs = [
        ExportSessionSpec(session_path=p1, include_data=False, include_data_k=True),
        ExportSessionSpec(session_path=p2, include_data=True, include_data_k=True),
    ]
    plan = plan_export(specs, dest=Path("E:/USB"))
    print(plan.estimated_bytes)          # estimation avant copie
    result = run_export(plan, dry_run=True)   # aucun fichier écrit
    result = run_export(plan, dry_run=False, progress=...)

Arborescence produite
---------------------
    <dest>/ChiroTool_export_YYYYMMDD_HHMMSS/
      EXPORT_README.txt
      export_manifest.json
      <campagne>/
        <session>/
          _session_manifest.json
          participation-*-observations*.xlsx
          *.sync.json
          _stats_before_cleanup.json
          *Summary*.txt
          Data_k/          (si include_data_k)
          Data/            (si include_data et source en Data/)
          *.wav            (si include_data et WAV à la racine source)
          ChiroSurf_nuits/ (si présent — toujours inclus)

Garde-fous
----------
- Dry-run par défaut côté run_export via ``dry_run=True``
- Estimation de taille dans le plan (avant copie)
- Erreurs fichier-par-fichier (continue, bilan final)
- Collisions de noms de session → suffixe ``_2``, ``_3``…
- Racine d'export toujours horodatée (pas d'écrasement silencieux)
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

try:
    from version import __version__ as TOOL_VERSION
except Exception:  # pragma: no cover
    TOOL_VERSION = "?"

# Noms de sous-dossiers bruts reconnus (aligné chiro_core.RAW_WAV_SUBDIR_NAMES)
_RAW_SUBDIR_NAMES = frozenset({"data", "wavs", "wave", "records", "recordings"})
_AUDIO_SUFFIXES = frozenset({".wav", ".w4v"})

# Dossiers toujours emportés s'ils existent (métadonnées / futur workflow)
_ALWAYS_DIRS = ("ChiroSurf_nuits",)

ProgressCb = Callable[[int, int, str], None] | None


# ---------------------------------------------------------------------------
# Specs / plan
# ---------------------------------------------------------------------------

@dataclass
class ExportSessionSpec:
    """Options d'export pour **une** session."""
    session_path: Path | str
    include_data: bool = False
    include_data_k: bool = True
    # Surcharge optionnelle du nom de campagne (sinon parent du dossier session)
    campaign: str | None = None


@dataclass
class PlannedFile:
    """Un fichier à copier (src → chemin relatif sous la racine d'export)."""
    src: str
    rel_dst: str
    size: int = 0
    kind: str = "meta"  # meta | data | data_k | chirosurf

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExportPlan:
    """Plan d'export calculé (aucune écriture)."""
    dest_root: str
    files: list[PlannedFile] = field(default_factory=list)
    sessions: list[dict[str, Any]] = field(default_factory=list)
    estimated_bytes: int = 0
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: _now_iso())
    tool_version: str = TOOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "dest_root": self.dest_root,
            "files": [f.to_dict() for f in self.files],
            "sessions": list(self.sessions),
            "estimated_bytes": self.estimated_bytes,
            "warnings": list(self.warnings),
            "created_at": self.created_at,
            "tool_version": self.tool_version,
            "n_files": len(self.files),
        }


# ---------------------------------------------------------------------------
# Helpers purs
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_name(name: str) -> str:
    """Nettoie un segment de chemin pour Windows (pas de / \\ : etc.)."""
    bad = '<>:"/\\|?*'
    out = "".join("_" if c in bad else c for c in (name or "").strip())
    out = out.rstrip(" .")
    return out or "unnamed"


def resolve_data_k_dir(session: Path) -> Path | None:
    """Localise le dossier TE×10 (local, 1-K, ou sibling campagne)."""
    session = Path(session)
    candidates = [
        session / "Data_k",
        session / "1-K",
        session.parent / "Data_k" / session.name,
    ]
    for c in candidates:
        try:
            if c.is_dir():
                return c
        except OSError:
            continue
    return None


def resolve_data_dir(session: Path) -> Path | None:
    """Sous-dossier de WAV bruts (Data/, recordings/…) s'il existe."""
    session = Path(session)
    try:
        for child in session.iterdir():
            if child.is_dir() and child.name.lower() in _RAW_SUBDIR_NAMES:
                return child
    except OSError:
        return None
    return None


def _file_size(p: Path) -> int:
    try:
        return int(p.stat().st_size)
    except OSError:
        return 0


def _iter_files_under(root: Path) -> Iterator[Path]:
    """Fichiers réguliers sous ``root`` (y compris root s'il est un fichier)."""
    import os
    root = Path(root)
    try:
        if root.is_file():
            yield root
            return
        if not root.is_dir():
            return
    except OSError:
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Ignore dossiers techniques cachés (`.git`, etc.)
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                if p.is_file() and not p.is_symlink():
                    yield p
            except OSError:
                continue


def collect_metadata_files(session: Path) -> list[Path]:
    """Fichiers de métadonnées toujours inclus (racine de session)."""
    session = Path(session)
    found: list[Path] = []
    if not session.is_dir():
        return found

    try:
        children = list(session.iterdir())
    except OSError:
        return found

    for p in children:
        try:
            if not p.is_file():
                continue
        except OSError:
            continue
        name = p.name
        low = name.lower()

        if name == "_session_manifest.json":
            found.append(p)
            continue
        if name == "_stats_before_cleanup.json":
            found.append(p)
            continue
        # Observations + sidecars de synchro
        if low.startswith("participation-") and "observations" in low:
            if low.endswith((".xlsx", ".csv", ".sync.json")):
                if "_cleanup" in low:
                    continue
                found.append(p)
            continue
        if low.endswith(".sync.json"):
            found.append(p)
            continue
        # Summary (nom canonique ou contenu-agnostique : *summary*.txt)
        if low.endswith(".txt") and ("summary" in low or low == "summary.txt"):
            found.append(p)
            continue

    # Fallback Summary par contenu (chiro_core) si rien trouvé par nom
    if not any("summary" in Path(f).name.lower() for f in found):
        try:
            from chiro_core import find_summary_file
            summ = find_summary_file(session)
            if summ is not None and summ not in found:
                found.append(summ)
        except Exception:
            pass

    return found


def collect_always_dirs(session: Path) -> list[Path]:
    """Dossiers toujours emportés s'ils existent (ex. ChiroSurf_nuits/)."""
    session = Path(session)
    out: list[Path] = []
    for name in _ALWAYS_DIRS:
        d = session / name
        try:
            if d.is_dir():
                out.append(d)
        except OSError:
            continue
    return out


def collect_root_audio(session: Path) -> list[Path]:
    """WAV/W4V directement à la racine de la session (pas dans un sous-dossier)."""
    session = Path(session)
    out: list[Path] = []
    try:
        for p in session.iterdir():
            try:
                if p.is_file() and p.suffix.lower() in _AUDIO_SUFFIXES:
                    out.append(p)
            except OSError:
                continue
    except OSError:
        return out
    return out


def _unique_rel_session(
    campaign: str,
    session_name: str,
    used: set[str],
) -> str:
    """Retourne ``campagne/session`` unique (suffixe _2, _3… si collision)."""
    camp = _safe_name(campaign)
    base = _safe_name(session_name)
    rel = f"{camp}/{base}"
    if rel not in used:
        used.add(rel)
        return rel
    n = 2
    while True:
        cand = f"{camp}/{base}_{n}"
        if cand not in used:
            used.add(cand)
            return cand
        n += 1


def make_export_root(dest: Path | str, *, stamp: str | None = None) -> Path:
    """Calcule le chemin racine d'export (horodaté, sans collision)."""
    dest = Path(dest)
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    root = dest / f"ChiroTool_export_{stamp}"
    if not root.exists():
        return root
    n = 2
    while True:
        cand = dest / f"ChiroTool_export_{stamp}_{n}"
        if not cand.exists():
            return cand
        n += 1


# ---------------------------------------------------------------------------
# plan_export
# ---------------------------------------------------------------------------

def plan_export(
    specs: list[ExportSessionSpec] | list[dict],
    dest: Path | str,
    *,
    stamp: str | None = None,
) -> ExportPlan:
    """Construit un plan d'export (aucune écriture disque).

    Parameters
    ----------
    specs
        Liste de :class:`ExportSessionSpec` (ou dicts compatibles).
    dest
        Dossier parent où créer ``ChiroTool_export_<stamp>/``.
    stamp
        Horodatage forcé (tests) ; défaut = maintenant.

    Returns
    -------
    ExportPlan
        Fichiers planifiés, estimation de taille, warnings.
    """
    dest = Path(dest)
    root = make_export_root(dest, stamp=stamp)
    plan = ExportPlan(dest_root=str(root))
    used_rel: set[str] = set()
    planned_dst: set[str] = set()  # évite doublons src→même rel

    normalized: list[ExportSessionSpec] = []
    for s in specs or []:
        if isinstance(s, ExportSessionSpec):
            normalized.append(s)
        elif isinstance(s, dict):
            normalized.append(ExportSessionSpec(
                session_path=s.get("session_path") or s.get("path"),
                include_data=bool(s.get("include_data", False)),
                include_data_k=bool(s.get("include_data_k", True)),
                campaign=s.get("campaign"),
            ))
        else:
            plan.warnings.append(f"spec ignorée (type {type(s).__name__})")

    for spec in normalized:
        session = Path(spec.session_path).resolve()
        if not session.is_dir():
            plan.warnings.append(f"session introuvable : {session}")
            continue

        campaign = spec.campaign or session.parent.name or "campagne"
        rel_session = _unique_rel_session(campaign, session.name, used_rel)

        sess_info: dict[str, Any] = {
            "source": str(session),
            "campaign": campaign,
            "session": session.name,
            "rel_path": rel_session,
            "include_data": bool(spec.include_data),
            "include_data_k": bool(spec.include_data_k),
            "n_files": 0,
            "bytes": 0,
        }

        def _add(src: Path, rel_under_session: str, kind: str) -> None:
            rel_dst = f"{rel_session}/{rel_under_session}".replace("\\", "/")
            if rel_dst in planned_dst:
                return
            try:
                if not src.is_file():
                    return
            except OSError as e:
                plan.warnings.append(f"inaccessible {src}: {e}")
                return
            size = _file_size(src)
            planned_dst.add(rel_dst)
            plan.files.append(PlannedFile(
                src=str(src),
                rel_dst=rel_dst,
                size=size,
                kind=kind,
            ))
            sess_info["n_files"] += 1
            sess_info["bytes"] += size

        # --- Métadonnées (toujours) ---------------------------------------
        for mf in collect_metadata_files(session):
            _add(mf, mf.name, "meta")

        # --- ChiroSurf_nuits / dossiers toujours ---------------------------
        for adir in collect_always_dirs(session):
            for f in _iter_files_under(adir):
                try:
                    rel = f.relative_to(session).as_posix()
                except ValueError:
                    rel = f"{adir.name}/{f.name}"
                kind = "chirosurf" if adir.name == "ChiroSurf_nuits" else "meta"
                _add(f, rel, kind)

        # --- Data_k -------------------------------------------------------
        if spec.include_data_k:
            dk = resolve_data_k_dir(session)
            if dk is None:
                plan.warnings.append(
                    f"{session.name}: Data_k/ introuvable (include_data_k=True)"
                )
            else:
                # Normalise toujours vers <session>/Data_k/ dans l'export
                # (même si source = sibling campagne/Data_k/<session>/)
                for f in _iter_files_under(dk):
                    try:
                        rel_inside = f.relative_to(dk).as_posix()
                    except ValueError:
                        rel_inside = f.name
                    _add(f, f"Data_k/{rel_inside}", "data_k")

        # --- Data bruts ---------------------------------------------------
        if spec.include_data:
            data_dir = resolve_data_dir(session)
            if data_dir is not None:
                for f in _iter_files_under(data_dir):
                    try:
                        rel_inside = f.relative_to(data_dir).as_posix()
                    except ValueError:
                        rel_inside = f.name
                    # Conserve le nom réel du sous-dossier (souvent Data)
                    _add(f, f"{data_dir.name}/{rel_inside}", "data")
            # WAV à la racine (layout sans sous-dossier Data/)
            for f in collect_root_audio(session):
                _add(f, f.name, "data")
            if data_dir is None and not collect_root_audio(session):
                plan.warnings.append(
                    f"{session.name}: aucun brut Data/ ni WAV racine "
                    f"(include_data=True)"
                )

        plan.sessions.append(sess_info)

    plan.estimated_bytes = sum(f.size for f in plan.files)
    return plan


# ---------------------------------------------------------------------------
# run_export
# ---------------------------------------------------------------------------

def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_readme(plan: ExportPlan, result_stats: dict) -> str:
    lines = [
        "ChiroTool — paquet d'export de sessions",
        "======================================",
        "",
        f"Créé le        : {plan.created_at}",
        f"Version outil  : {plan.tool_version}",
        f"Racine         : {plan.dest_root}",
        f"Sessions       : {len(plan.sessions)}",
        f"Fichiers plan  : {len(plan.files)}",
        f"Taille estimée : {_fmt_bytes(plan.estimated_bytes)}",
        "",
        "Contenu par session",
        "-------------------",
    ]
    for s in plan.sessions:
        lines.append(
            f"  • {s.get('rel_path')}"
            f"  data_k={'oui' if s.get('include_data_k') else 'non'}"
            f"  data={'oui' if s.get('include_data') else 'non'}"
            f"  ({s.get('n_files', 0)} fichiers, {_fmt_bytes(s.get('bytes', 0))})"
        )
        lines.append(f"    source : {s.get('source')}")
    lines += [
        "",
        "Métadonnées toujours incluses",
        "-----------------------------",
        "  _session_manifest.json, observations xlsx/csv + sidecar .sync.json,",
        "  _stats_before_cleanup.json, Summary*.txt, ChiroSurf_nuits/ (si présent).",
        "",
        "Réutilisation",
        "-------------",
        "  Placez le dossier de campagne sous un workspace ChiroTool et lancez",
        "  un scan : les pastilles d'état se reconstruisent depuis le disque",
        "  (xlsx, Data_k, manifest).",
        "",
        "Fichiers de contrôle",
        "--------------------",
        "  export_manifest.json — inventaire machine-readable",
        "  EXPORT_README.txt    — ce fichier",
        "",
        f"Résultat copie : {result_stats.get('n_copied', 0)} copiés, "
        f"{result_stats.get('n_skipped', 0)} ignorés, "
        f"{result_stats.get('n_errors', 0)} erreur(s).",
    ]
    if result_stats.get("dry_run"):
        lines.append("")
        lines.append("Mode DRY-RUN : aucun fichier audio/meta n'a été copié.")
    return "\n".join(lines) + "\n"


def _fmt_bytes(n: int) -> str:
    x = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(x) < 1024:
            return f"{x:.1f} {unit}" if unit != "B" else f"{int(x)} B"
        x /= 1024
    return f"{x:.1f} PB"


def run_export(
    plan: ExportPlan,
    *,
    dry_run: bool = False,
    progress: ProgressCb = None,
    skip_identical: bool = True,
) -> dict[str, Any]:
    """Exécute un plan d'export.

    Parameters
    ----------
    plan
        Produit par :func:`plan_export`.
    dry_run
        Si True : n'écrit **aucun** fichier (pas même le README) ; retourne
        le bilan « aurait copié ».
    progress
        Callback ``(done, total, label)``.
    skip_identical
        Si la cible existe déjà avec même taille, ne pas réécrire.

    Returns
    -------
    dict
        ``n_copied``, ``n_skipped``, ``n_errors``, ``errors``, ``dest_root``,
        ``dry_run``, ``bytes_copied``, …
    """
    root = Path(plan.dest_root)
    total = len(plan.files)
    result: dict[str, Any] = {
        "dest_root": str(root),
        "dry_run": bool(dry_run),
        "n_planned": total,
        "n_copied": 0,
        "n_skipped": 0,
        "n_errors": 0,
        "bytes_copied": 0,
        "errors": [],
        "estimated_bytes": plan.estimated_bytes,
        "sessions": plan.sessions,
        "tool_version": plan.tool_version,
    }

    if dry_run:
        # Simule le parcours pour la barre de progression
        for i, pf in enumerate(plan.files, 1):
            if progress is not None:
                try:
                    progress(i, max(total, 1), f"dry-run {Path(pf.rel_dst).name}")
                except Exception:
                    pass
        result["n_skipped"] = total  # rien écrit
        result["notes"] = ["dry-run : aucune écriture"]
        return result

    # Création racine
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        result["errors"].append(f"impossible de créer {root}: {e}")
        result["n_errors"] += 1
        result["error"] = str(e)
        return result

    for i, pf in enumerate(plan.files, 1):
        src = Path(pf.src)
        dst = root / pf.rel_dst
        label = Path(pf.rel_dst).name
        if progress is not None:
            try:
                progress(i - 1, max(total, 1), label)
            except Exception:
                pass

        try:
            if not src.is_file():
                result["errors"].append(f"source absente : {src}")
                result["n_errors"] += 1
                continue

            if skip_identical and dst.is_file():
                try:
                    if dst.stat().st_size == src.stat().st_size:
                        result["n_skipped"] += 1
                        continue
                except OSError:
                    pass

            dst.parent.mkdir(parents=True, exist_ok=True)
            # Copie via fichier temporaire puis replace (plus robuste)
            tmp = dst.with_suffix(dst.suffix + ".partial")
            try:
                shutil.copy2(src, tmp)
                tmp.replace(dst)
            except Exception:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                raise

            result["n_copied"] += 1
            result["bytes_copied"] += pf.size
        except PermissionError as e:
            result["errors"].append(f"permission : {src} → {dst}: {e}")
            result["n_errors"] += 1
        except OSError as e:
            result["errors"].append(f"OS error : {src} → {dst}: {e}")
            result["n_errors"] += 1
        except Exception as e:
            result["errors"].append(f"échec : {src} → {dst}: {e}")
            result["n_errors"] += 1

    if progress is not None:
        try:
            progress(total, max(total, 1), "finalisation")
        except Exception:
            pass

    # Manifest + README (toujours en mode réel)
    manifest = {
        "schema": 1,
        "tool_version": plan.tool_version,
        "created_at": plan.created_at,
        "dest_root": str(root),
        "dry_run": False,
        "sessions": plan.sessions,
        "totals": {
            "n_files_planned": total,
            "n_copied": result["n_copied"],
            "n_skipped": result["n_skipped"],
            "n_errors": result["n_errors"],
            "bytes_estimated": plan.estimated_bytes,
            "bytes_copied": result["bytes_copied"],
        },
        "warnings": plan.warnings,
        "errors": result["errors"],
        "files": [
            {"rel_dst": f.rel_dst, "size": f.size, "kind": f.kind}
            for f in plan.files
        ],
    }
    try:
        _write_text(
            root / "export_manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        _write_text(root / "EXPORT_README.txt", _build_readme(plan, result))
    except OSError as e:
        result["errors"].append(f"écriture manifeste/README : {e}")
        result["n_errors"] += 1

    if result["n_errors"] and not result["n_copied"]:
        result["error"] = f"{result['n_errors']} erreur(s), aucun fichier copié"

    return result


# ---------------------------------------------------------------------------
# CLI minimal (debug / scripts)
# ---------------------------------------------------------------------------

def _cli() -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Export portable de sessions ChiroTool.")
    ap.add_argument("dest", type=Path, help="dossier destination (parent du paquet)")
    ap.add_argument("sessions", nargs="+", type=Path, help="chemins de sessions")
    ap.add_argument("--data", action="store_true", help="inclure Data/ bruts")
    ap.add_argument("--no-data-k", action="store_true", help="exclure Data_k/")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    specs = [
        ExportSessionSpec(
            session_path=s,
            include_data=args.data,
            include_data_k=not args.no_data_k,
        )
        for s in args.sessions
    ]
    plan = plan_export(specs, args.dest)
    print(f"Plan : {len(plan.files)} fichiers, {_fmt_bytes(plan.estimated_bytes)}")
    for w in plan.warnings:
        print(f"  ⚠ {w}")
    print(f"Racine : {plan.dest_root}")

    def _p(done, total, label):
        print(f"\r  {done}/{total} {label[:40]:<40}", end="", flush=True)

    res = run_export(plan, dry_run=args.dry_run, progress=_p)
    print()
    print(f"Résultat : copiés={res['n_copied']} skip={res['n_skipped']} "
          f"err={res['n_errors']} dry_run={res['dry_run']}")
    for e in res.get("errors") or []:
        print(f"  ✗ {e}", file=sys.stderr)
    return 1 if res.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(_cli())
