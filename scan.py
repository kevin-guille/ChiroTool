"""
scan.py — scanner de dossiers de sessions chiroptères.

Usage :
    python scan.py [dossier-racine]
    python scan.py [dossier-racine] --json rapport.json

Sans argument, scanne le dossier parent de _tool/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Windows : la console est souvent en cp1252, on force UTF-8 pour les emojis et ANSI.
# PyInstaller --windowed : sys.stdout peut être None (pas de console).
# On guard pour éviter AttributeError au démarrage du .exe.
if sys.stdout is not None and getattr(sys.stdout, "encoding", None):
    if sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            if sys.stderr is not None:
                sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

from chiro_core import SessionState, analyze_session, walk_sessions


# Codes ANSI pour la sortie terminale
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"


def _flag(ok: bool, label: str) -> str:
    if ok:
        return f"{C.GREEN}✓ {label}{C.RESET}"
    return f"{C.DIM}· {label}{C.RESET}"


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def print_session(s: SessionState) -> None:
    # Statut global : ✅ prêt, ⚠ à finir, ❌ brut
    done = sum([s.flag_renamed, s.flag_te10_done, s.flag_analyzed, s.flag_cleaned])
    if done == 4:
        status = f"{C.GREEN}✅{C.RESET}"
    elif done == 0:
        status = f"{C.RED}❌{C.RESET}"
    else:
        status = f"{C.YELLOW}⚠ {C.RESET}"

    print(f"\n{status} {C.BOLD}{s.campaign}{C.RESET} / {C.CYAN}{s.name}{C.RESET}")
    print(f"   {C.DIM}{s.path}{C.RESET}")

    # Fichiers
    parts = [f"{s.n_wav} wav"]
    if s.n_w4v:
        parts.append(f"{C.MAGENTA}{s.n_w4v} .w4v{C.RESET}")
    parts.append(_fmt_size(s.total_bytes))
    print("   📁 " + " | ".join(parts))

    # Typage des noms
    naming = []
    if s.n_wav_vigiechiro:
        naming.append(f"{C.GREEN}{s.n_wav_vigiechiro} Vigie-Chiro{C.RESET}")
    if s.n_wav_raw:
        naming.append(f"{C.YELLOW}{s.n_wav_raw} bruts{C.RESET}")
    if s.n_wav_unknown:
        naming.append(f"{C.RED}{s.n_wav_unknown} inconnus{C.RESET}")
    if naming:
        print("   🏷  " + " · ".join(naming))

    # Sample rates détectés
    if s.sr_samples:
        srs = ", ".join(f"{sr/1000:.1f}k" for sr in s.sr_samples)
        te = "TE×10 probable" if s.looks_time_expanded else "brut (pas TE)"
        print(f"   🔉 échantillon SR : {srs}  →  {te}")

    # Summary.txt
    if s.summary:
        sm = s.summary
        sm_str = f"{sm.n_lines} min enregistrées"
        if sm.start_dt and sm.end_dt:
            sm_str += f" · {sm.start_dt:%Y-%m-%d %H:%M} → {sm.end_dt:%H:%M}"
        if sm.temp_start is not None and sm.temp_end is not None:
            sm_str += f" · T {sm.temp_start:.0f}→{sm.temp_end:.0f}°C"
        if sm.lat and sm.lon:
            sm_str += f" · GPS {sm.lat:.4f},{sm.lon:.4f}"
        print(f"   📄 Summary.txt : {sm_str}")

    # Observations téléchargées
    if s.observations_paths:
        for p in s.observations_paths:
            print(f"   📊 Observations : {p.name}")

    # Drapeaux pipeline
    print(
        "   "
        + "  ".join([
            _flag(s.flag_renamed, "Renommé"),
            _flag(s.flag_te10_done, "TE×10"),
            _flag(s.flag_analyzed, "Analysé"),
            _flag(s.flag_cleaned, "Nettoyé"),
        ])
    )
    if s.has_data_k_mirror:
        print(f"   {C.DIM}(miroir Data_k/ détecté){C.RESET}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default=None, help="dossier racine à scanner")
    ap.add_argument("--json", dest="json_out", default=None, help="chemin du rapport JSON")
    ap.add_argument("--max-depth", type=int, default=4, help="profondeur max (défaut 4)")
    args = ap.parse_args()

    if args.root is None:
        # Parent du dossier _tool par défaut
        args.root = str(Path(__file__).resolve().parent.parent)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"{C.RED}Dossier introuvable : {root}{C.RESET}", file=sys.stderr)
        return 2

    print(f"{C.BOLD}Scan :{C.RESET} {root}")
    sessions_paths = walk_sessions(root, max_depth=args.max_depth)
    print(f"{len(sessions_paths)} dossier(s) de session détecté(s)\n")

    # Parallélisation I/O-bound : analyze_session ouvre plusieurs WAV headers
    # + Summary.txt par session. Gain typique ×4-8 sur SSD.
    if len(sessions_paths) >= 4:
        from concurrent.futures import ThreadPoolExecutor
        max_workers = min(8, len(sessions_paths))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            states = list(ex.map(analyze_session, sessions_paths))
    else:
        states = [analyze_session(p) for p in sessions_paths]
    # Les prints restent séquentiels pour une sortie lisible
    for s in states:
        print_session(s)

    # Récap
    print(f"\n{C.BOLD}Récap{C.RESET}")
    print(f"  Sessions scannées     : {len(states)}")
    print(f"  Renommées Vigie-Chiro : {sum(1 for s in states if s.flag_renamed)}")
    print(f"  TE×10 fait            : {sum(1 for s in states if s.flag_te10_done)}")
    print(f"  Analysées (obs xlsx)  : {sum(1 for s in states if s.flag_analyzed)}")
    print(f"  Nettoyées             : {sum(1 for s in states if s.flag_cleaned)}")
    print(f"  WAV totaux            : {sum(s.n_wav for s in states)}")
    print(f"  Taille totale WAV     : {_fmt_size(sum(s.total_bytes for s in states))}")

    if args.json_out:
        out = Path(args.json_out)
        with out.open("w", encoding="utf-8") as f:
            json.dump(
                {"root": str(root), "sessions": [s.to_dict() for s in states]},
                f,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        print(f"\n📝 Rapport JSON : {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
