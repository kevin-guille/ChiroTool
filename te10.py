"""
te10.py — remplacement local de Kaleidoscope (point fixe, TE×10).

Reproduit le comportement observé de Kaleidoscope Free sur nos enregistrements :

  1. Pour chaque WAV d'entrée, découpage en tranches de 5 secondes RAW maximum
     (= 50 secondes en temps étendu ×10). Les fichiers plus courts que 5 s raw
     sortent en un seul segment (durée préservée).
  2. Chaque tranche est écrite en tant que WAV indépendant. Le sample rate
     déclaré dans l'en-tête est divisé par le facteur TE (10 par défaut), les
     échantillons PCM sont recopiés tels quels (zéro perte).
  3. Le timestamp encodé dans le nom du fichier (YYYYMMDD_HHMMSS) est
     incrémenté de +5 secondes par tranche. Chaque sortie se voit ajouter le
     suffixe `_000` (comme Kaleidoscope).

Usage :
    python te10.py <dossier_source> [<dossier_sortie>] [options]

Exemples :
    # Dossier source contenant des WAV bruts 384 kHz, sortie dans un
    # sous-dossier Data_k/ à côté :
    python te10.py \\
        "D:/Chiros/MonContrat/20250903_123456_Z1_Pass2/Data"

    # Comparer avec le Data_k déjà produit par Kaleidoscope, sans écrire :
    python te10.py \\
        "D:/Chiros/MonContrat/20250919_123456_Z1_Pass1" \\
        --dry-run --compare-with "D:/Chiros/MonContrat/Data_k/20250919_123456_Z1_Pass1"

Options :
    --factor N           facteur TE (défaut : 10)
    --segment-s N        durée de segment en secondes RAW (défaut : 5.0)
    --dry-run            n'écrit rien, affiche juste ce qui serait fait
    --compare-with DIR   compare le résultat prévu au contenu d'un dossier existant
    -j N                 parallélisme (défaut : nb_coeurs - 1, min 1)
    --overwrite          écrase les fichiers déjà présents dans la sortie
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import re
import sys
import threading
import wave
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

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


# -- Backend Rust (optionnel) ------------------------------------------------
# Si le module chirotool_fast est installé (maturin develop / wheel), on
# l'utilise automatiquement. Sinon, fallback sur la version Python pure.
try:
    import chirotool_fast
    RUST_ENGINE = True
    RUST_VERSION = getattr(chirotool_fast, "__version__", "?")
except ImportError:
    chirotool_fast = None
    RUST_ENGINE = False
    RUST_VERSION = None


TIMESTAMP_RE = re.compile(r"^(?P<prefix>.*_)(?P<date>\d{8})_(?P<time>\d{6})(?P<rest>.*)$")


@dataclass
class SegmentPlan:
    """Description d'un segment à produire."""
    src: Path
    dst: Path
    start_frame: int            # indice du 1er échantillon (dans le WAV source)
    n_frames: int               # nombre d'échantillons à copier
    sr_te: int                  # sample rate à écrire dans l'en-tête de sortie


def _reframe_timestamp(name_stem: str, offset_seconds: int) -> str:
    """
    Ajoute `offset_seconds` au timestamp YYYYMMDD_HHMMSS encodé dans le stem.
    Exemple : ('Car..._20250919_200134', 5) -> 'Car..._20250919_200139'.
    """
    m = TIMESTAMP_RE.match(name_stem)
    if m is None:
        # Pas de timestamp détectable : on retourne tel quel + offset en suffixe
        return name_stem if offset_seconds == 0 else f"{name_stem}+{offset_seconds}s"
    dt = datetime.strptime(m.group("date") + m.group("time"), "%Y%m%d%H%M%S")
    dt = dt + timedelta(seconds=offset_seconds)
    return f'{m.group("prefix")}{dt:%Y%m%d_%H%M%S}{m.group("rest")}'


def plan_file(src: Path, out_dir: Path, factor: int, segment_s: float) -> list[SegmentPlan]:
    """Retourne la liste des segments à produire pour un fichier source."""
    with wave.open(str(src), "rb") as w:
        sr = w.getframerate()
        n_frames = w.getnframes()
    if sr <= 0 or n_frames <= 0:
        return []

    sr_te = sr // factor
    frames_per_segment = int(round(segment_s * sr))   # en raw
    if frames_per_segment <= 0:
        frames_per_segment = n_frames

    plans: list[SegmentPlan] = []
    idx = 0
    start = 0
    while start < n_frames:
        take = min(frames_per_segment, n_frames - start)
        offset_s = idx * int(round(segment_s))
        new_stem = _reframe_timestamp(src.stem, offset_s)
        dst = out_dir / f"{new_stem}_000.wav"
        plans.append(SegmentPlan(src=src, dst=dst, start_frame=start, n_frames=take, sr_te=sr_te))
        start += take
        idx += 1
    return plans


def write_segment(plan: SegmentPlan, overwrite: bool = False) -> tuple[bool, str]:
    if plan.dst.exists() and not overwrite:
        return False, f"SKIP (existe déjà) : {plan.dst.name}"
    plan.dst.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(plan.src), "rb") as wr:
        nch = wr.getnchannels()
        sw = wr.getsampwidth()
        wr.setpos(plan.start_frame)
        frames = wr.readframes(plan.n_frames)

    # Écriture atomique : fichier temporaire puis renommage
    tmp = plan.dst.with_suffix(plan.dst.suffix + ".tmp")
    try:
        with wave.open(str(tmp), "wb") as ww:
            ww.setnchannels(nch)
            ww.setsampwidth(sw)
            ww.setframerate(plan.sr_te)
            ww.writeframes(frames)
        tmp.replace(plan.dst)
    except Exception as e:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        return False, f"ERREUR : {plan.dst.name} ({e})"
    return True, f"OK : {plan.dst.name} ({plan.n_frames/plan.sr_te:.2f}s TE)"


def process_folder(
    src_dir: Path,
    out_dir: Path,
    factor: int = 10,
    segment_s: float = 5.0,
    jobs: int = 1,
    dry_run: bool = False,
    overwrite: bool = False,
    force_python: bool = False,
    progress=None,
) -> dict:
    """Traite un dossier entier.

    Si l'extension Rust ``chirotool_fast`` est installée et que ``force_python``
    est False, on utilise le backend Rust (~12× plus rapide). Sinon, fallback
    pur Python (fonctionne partout sans compilation).

    ``progress`` : callback ``(done, total, label)`` appelé à chaque segment
    traité. Le backend Rust n'expose pas (encore) de hook par segment, donc
    pour Rust on n'appelle progress qu'au début et à la fin. Le backend
    Python alimente progress à chaque segment écrit.
    """
    # Backend Rust si disponible
    if RUST_ENGINE and not force_python:
        try:
            # Le moteur Rust est opaque (pas de hook par segment). Pour offrir une
            # VRAIE progression (sinon l'UI semble figée puis saute à 100 % d'un
            # coup), on procède en deux temps :
            #  1. pré-scan léger des en-têtes WAV → nombre de segments attendus ;
            #  2. un thread sonde le dossier de sortie pendant l'écriture Rust.
            total_expected = 0
            if progress is not None and not dry_run:
                try:
                    srcs = sorted(src_dir.glob("*.wav"))
                    n_src = max(1, len(srcs))
                    for i, s in enumerate(srcs):
                        try:
                            total_expected += len(
                                plan_file(s, out_dir, factor, segment_s))
                        except (wave.Error, OSError):
                            pass
                        if i % 25 == 0:
                            progress(i, n_src, "Analyse des fichiers…")
                except Exception:
                    total_expected = 0

            stop_evt = threading.Event()
            if progress is not None and total_expected > 0 and not dry_run:
                def _monitor(total=total_expected):
                    while not stop_evt.wait(0.7):
                        try:
                            n = sum(1 for _ in out_dir.glob("*.wav"))
                            progress(min(n, total), total, "TE×10")
                        except Exception:
                            pass
                threading.Thread(target=_monitor, daemon=True).start()
            elif progress is not None:
                progress(0, 100, "TE×10 (Rust)")

            try:
                stats = chirotool_fast.process_folder(
                    src=str(src_dir), dst=str(out_dir),
                    factor=factor, segment_s=segment_s,
                    jobs=jobs, dry_run=dry_run, overwrite=overwrite,
                )
            finally:
                stop_evt.set()

            if progress is not None:
                t = total_expected or 100
                progress(t, t, "TE×10")
            # Normalise les clés pour matcher l'API Python existante
            return {
                "src_dir": str(src_dir),
                "out_dir": str(out_dir),
                "n_source_wavs": stats.get("n_source_wavs", 0),
                "n_planned_segments": stats.get("n_planned_segments", 0),
                "factor": factor,
                "segment_s": segment_s,
                "dry_run": dry_run,
                "written": stats.get("written", 0),
                "skipped": stats.get("skipped", 0),
                "errors": stats.get("errors", 0),
                "elapsed_s": stats.get("elapsed_s", 0.0),
                "engine": "rust",
            }
        except Exception as e:
            # En cas d'erreur Rust → on tombe sur Python (ceinture + bretelles)
            print(f"⚠  extension Rust a échoué ({e}), fallback Python", file=sys.stderr)

    # Backend Python
    sources = sorted(src_dir.glob("*.wav"))
    if not sources:
        return {"error": f"Aucun WAV trouvé dans {src_dir}"}

    # Plan complet
    all_plans: list[SegmentPlan] = []
    for src in sources:
        try:
            all_plans.extend(plan_file(src, out_dir, factor, segment_s))
        except wave.Error as e:
            print(f"⚠  fichier illisible (ignoré) : {src.name}  ({e})", file=sys.stderr)

    stats = {
        "src_dir": str(src_dir),
        "out_dir": str(out_dir),
        "n_source_wavs": len(sources),
        "n_planned_segments": len(all_plans),
        "factor": factor,
        "segment_s": segment_s,
        "dry_run": dry_run,
        "written": 0,
        "skipped": 0,
        "errors": 0,
        "engine": "python",
    }

    if dry_run:
        return stats

    total = len(all_plans)
    done = [0]   # mutable closure-friendly counter
    label = "TE×10"

    def _tick():
        done[0] += 1
        if progress is not None and (done[0] % 5 == 0 or done[0] == total):
            try:
                progress(done[0], total, label)
            except Exception:
                pass

    if jobs > 1:
        with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
            futures = [ex.submit(write_segment, p, overwrite) for p in all_plans]
            for fut in cf.as_completed(futures):
                ok, _msg = fut.result()
                if ok:
                    stats["written"] += 1
                else:
                    stats["skipped"] += 1
                _tick()
    else:
        for p in all_plans:
            ok, _msg = write_segment(p, overwrite)
            if ok:
                stats["written"] += 1
            else:
                stats["skipped"] += 1
            _tick()

    return stats


def compare_with(planned: list[SegmentPlan], existing_dir: Path) -> dict:
    """Compare la liste prévue avec le contenu effectif d'un dossier existant
    (typiquement le Data_k/ sorti par Kaleidoscope). Vérifie juste les noms
    et les durées / sample rates."""
    existing = {p.name: p for p in existing_dir.glob("*.wav")}
    planned_names = {p.dst.name for p in planned}
    missing = sorted(planned_names - existing.keys())
    extra = sorted(set(existing.keys()) - planned_names)
    common = planned_names & existing.keys()

    durations_ok = 0
    durations_mismatch: list[tuple[str, float, float]] = []
    for name in sorted(common)[:50]:  # limité à 50 pour la vitesse
        p_plan = next(p for p in planned if p.dst.name == name)
        expected_dur = p_plan.n_frames / p_plan.sr_te
        try:
            with wave.open(str(existing[name]), "rb") as w:
                actual_dur = w.getnframes() / w.getframerate()
        except wave.Error:
            continue
        if abs(actual_dur - expected_dur) < 0.02:
            durations_ok += 1
        else:
            durations_mismatch.append((name, expected_dur, actual_dur))

    return {
        "planned": len(planned_names),
        "existing": len(existing),
        "common": len(common),
        "missing_in_existing": missing,
        "extra_in_existing": extra,
        "durations_checked": min(50, len(common)),
        "durations_ok": durations_ok,
        "durations_mismatch": durations_mismatch[:10],
    }


def main() -> int:
    import os
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="dossier contenant les WAV bruts")
    ap.add_argument("dst", nargs="?", help="dossier de sortie (défaut : ../Data_k/<nom-src>)")
    ap.add_argument("--factor", type=int, default=10)
    ap.add_argument("--segment-s", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--compare-with", dest="compare_with", default=None,
                    help="dossier existant (Data_k Kaleidoscope) pour comparaison")
    ap.add_argument("-j", "--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--force-python", action="store_true",
                    help="ne pas utiliser l'extension Rust (benchmark)")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    if not src.is_dir():
        print(f"❌ dossier source introuvable : {src}", file=sys.stderr)
        return 2

    if args.dst:
        dst = Path(args.dst).resolve()
    else:
        # Par défaut : <parent>/Data_k/<nom-src>/
        dst = src.parent / "Data_k" / src.name

    backend = "Rust" if (RUST_ENGINE and not args.force_python) else "Python"
    print(f"Source : {src}")
    print(f"Sortie : {dst}   {'(dry-run)' if args.dry_run else ''}")
    print(f"Réglages : factor×{args.factor}, segments {args.segment_s}s raw")
    print(f"Backend : {backend}"
          + (f" (chirotool_fast v{RUST_VERSION})" if backend == "Rust" else ""))

    # Plan complet pour affichage / comparaison
    sources = sorted(src.glob("*.wav"))
    planned: list[SegmentPlan] = []
    for s in sources:
        try:
            planned.extend(plan_file(s, dst, args.factor, args.segment_s))
        except wave.Error as e:
            print(f"⚠  illisible : {s.name} ({e})", file=sys.stderr)

    print(f"\n{len(sources)} WAV source → {len(planned)} segments prévus "
          f"(ratio {len(planned)/max(1,len(sources)):.2f})")

    if args.compare_with:
        cmp_dir = Path(args.compare_with).resolve()
        if cmp_dir.is_dir():
            res = compare_with(planned, cmp_dir)
            print(f"\n=== Comparaison avec {cmp_dir} ===")
            print(f"  Prévus          : {res['planned']}")
            print(f"  Dans dossier ref: {res['existing']}")
            print(f"  Noms en commun  : {res['common']}")
            if res["missing_in_existing"]:
                print(f"  ❌ Manquants dans ref (notre script en produit en plus) : {len(res['missing_in_existing'])}")
                for n in res["missing_in_existing"][:5]:
                    print(f"      + {n}")
            if res["extra_in_existing"]:
                print(f"  ⚠ En plus dans ref (Kaleidoscope en produit en plus) : {len(res['extra_in_existing'])}")
                for n in res["extra_in_existing"][:5]:
                    print(f"      + {n}")
            print(f"  Durées vérifiées : {res['durations_checked']} / OK : {res['durations_ok']}")
            if res["durations_mismatch"]:
                print("  ⚠ Écarts de durée :")
                for name, exp, act in res["durations_mismatch"]:
                    print(f"      {name}  prévu={exp:.2f}s  réel={act:.2f}s")
        else:
            print(f"⚠  --compare-with : dossier introuvable : {cmp_dir}", file=sys.stderr)

    if args.dry_run:
        print("\n(dry-run : rien n'a été écrit)")
        return 0

    res = process_folder(src, dst, args.factor, args.segment_s, args.jobs,
                          False, args.overwrite, force_python=args.force_python)
    print(f"\nBackend utilisé : {res.get('engine', '?')}  ·  "
          f"elapsed : {res.get('elapsed_s', '?')}s")
    print(f"\nÉcrits : {res['written']}   Passés : {res['skipped']}   Erreurs : {res['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
