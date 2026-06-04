"""
rename.py — renommage d'une session et de ses WAV au format canonique.

Prend une session (dossier brut ou déjà partiellement traité) et :

  1. détermine où vivent les WAV (racine du dossier OU sous-dossier ``Data/``)
  2. vérifie la cohérence entre la série attendue (meta.n_serie) et la série
     observée dans les noms de fichier
  3. calcule les nouveaux noms Vigie-Chiro
  4. renomme les WAV (idempotent : si déjà OK, skip)
  5. renomme éventuellement le dossier session au format canonique
  6. enregistre l'action dans le manifest

Usage en CLI (généralement appelé par la GUI, mais pratique pour tester) :

    python rename.py <session> \\
        --site 212097 --point Z3 --pass 2 --enr 7 \\
        --serial SMU03126 --date 2025-09-03 --contrat "MonContrat" \\
        [--dry-run] [--force]

Ou avec auto-résolution depuis le Suivi :

    python rename.py <session> --auto

(le mode --auto essaie de résoudre meta en matchant sur le nom de dossier brut
et les séries observées dans les WAV, via suivi.py)
"""

from __future__ import annotations

import argparse
import shutil
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

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

from chiro_core import (
    RAW_WAV_SUBDIR_NAMES,
    VIGIECHIRO_RE,
    _dir_has_wavs,
    _find_raw_wav_subdir,
    parse_summary_txt,
)
from manifest import Manifest
from naming import (
    SessionMeta,
    canonical_session_dirname,
    check_serial_consistency,
    compute_new_wav_name,
    extract_serial_from_name,
    validate_meta,
    vigiechiro_wav_prefix,
)


try:
    from version import __version__ as TOOL_VERSION
except Exception:
    TOOL_VERSION = "0.1-dev"


# ---------------------------------------------------------------------------
# Cœur : renommage d'une session
# ---------------------------------------------------------------------------

def rename_session(
    session: Path,
    meta: SessionMeta,
    dry_run: bool = False,
    rename_folder: bool = True,
    force: bool = False,
) -> dict:
    """
    Renomme une session. Retourne un dict de stats/résultat.

    Idempotent : si le manifest dit "déjà renommé" et qu'on n'est pas en
    ``force``, aucun fichier n'est touché.
    """
    session = session.resolve()
    out = {
        "session": str(session),
        "dry_run": dry_run,
        "rename_folder": rename_folder,
        "force": force,
        "errors": [],
        "warnings": [],
        "planned": [],           # [(src, dst), ...]
        "executed": 0,
        "skipped_same_name": 0,
        "final_session_path": str(session),
    }

    # --- 1. validation metadata
    errs = validate_meta(meta)
    if errs:
        out["errors"] = errs
        return out

    # --- 2. chargement manifest + décision idempotence
    m = Manifest.load_or_create(session)
    if m.is_done("rename") and not force:
        out["warnings"].append("déjà renommé (cf manifest). Utilise --force pour recommencer.")
        return out

    # --- 3. repérage des WAV
    if _dir_has_wavs(session):
        wav_dir = session
        wav_dir_kind = "root"
    else:
        wav_sub = _find_raw_wav_subdir(session)
        if wav_sub is None:
            out["errors"].append(f"Aucun WAV trouvé dans {session} ni dans un sous-dossier Data/")
            return out
        wav_dir = wav_sub
        wav_dir_kind = f"subdir:{wav_sub.name}"

    wav_paths = sorted(p for p in wav_dir.iterdir() if p.is_file() and p.suffix.lower() == ".wav")
    out["n_wav_found"] = len(wav_paths)
    out["wav_dir"] = str(wav_dir)
    out["wav_dir_kind"] = wav_dir_kind

    # --- 4. vérification cohérence série observée vs meta
    consistency = check_serial_consistency(meta, (p.name for p in wav_paths))
    out["serial_check"] = consistency
    if consistency["consistent"] is False:
        out["warnings"].append(
            f"incohérence série : attendu {consistency['expected']!r}, "
            f"dominant dans fichiers {consistency['dominant_in_files']!r}"
        )

    # --- 5. plan de renommage des fichiers
    plan: list[tuple[Path, Path]] = []
    unreadable: list[str] = []
    same: list[str] = []
    collisions: set[str] = set()
    target_names: set[str] = set()

    prefix = vigiechiro_wav_prefix(meta)

    for src in wav_paths:
        new_name = compute_new_wav_name(meta, src.name)
        if new_name is None:
            unreadable.append(src.name)
            continue
        if new_name == src.name:
            same.append(src.name)
            continue
        if new_name in target_names:
            collisions.add(new_name)
        target_names.add(new_name)
        dst = wav_dir / new_name
        plan.append((src, dst))

    out["planned"] = [(str(s), str(d)) for s, d in plan]
    out["n_planned"] = len(plan)
    out["skipped_same_name"] = len(same)
    out["unreadable"] = unreadable
    out["collisions"] = sorted(collisions)

    # CRITIQUE : collisions de noms (plusieurs fichiers sources → même nom cible)
    # signifient une perte de données garantie (le 2e rename écraserait le 1er).
    # On bloque l'exécution et on remonte une erreur explicite.
    if collisions:
        out["errors"].append(
            f"collisions de noms détectées ({len(collisions)}) : "
            f"{', '.join(sorted(collisions)[:3])}"
            f"{'…' if len(collisions) > 3 else ''}. "
            "Aucun renommage effectué (risque d'écrasement)."
        )
        return out

    # Cible déjà existante sur disque (ex : relance après crash partiel).
    # Bloquant également : on veut éviter d'écraser.
    existing_collisions: list[str] = []
    for _, dst in plan:
        if dst.exists():
            existing_collisions.append(dst.name)
    if existing_collisions:
        out["errors"].append(
            f"{len(existing_collisions)} fichier(s) cible existe(nt) déjà sur disque : "
            f"{', '.join(existing_collisions[:3])}"
            f"{'…' if len(existing_collisions) > 3 else ''}. "
            "Supprime-les ou relance avec précaution."
        )
        return out

    # --- 6. exécution
    if not dry_run:
        for src, dst in plan:
            # Double-check : si dst a été créé entre le plan et l'exec
            # (par un autre process), ne pas écraser.
            if dst.exists():
                out["errors"].append(
                    f"cible apparue pendant l'exécution, skip : {dst.name}")
                continue
            try:
                # Renommage atomique (sur même volume → os.rename sous le capot)
                src.rename(dst)
                out["executed"] += 1
            except OSError as e:
                out["errors"].append(f"échec renommage {src.name} → {dst.name} : {e}")

    # --- 7. renommage du dossier session
    try:
        canonical_dir = canonical_session_dirname(meta)
    except ValueError as e:
        out["errors"].append(str(e))
        return out

    out["canonical_dir"] = canonical_dir
    final_path = session
    if rename_folder and session.name != canonical_dir and not dry_run:
        target = session.parent / canonical_dir
        if target.exists():
            out["warnings"].append(f"dossier cible {target} existe déjà, pas de renommage")
        else:
            try:
                session.rename(target)
                final_path = target
            except OSError as e:
                out["errors"].append(f"échec renommage dossier : {e}")
    elif rename_folder and session.name != canonical_dir and dry_run:
        out["planned_folder_rename"] = str(session.parent / canonical_dir)

    out["final_session_path"] = str(final_path)

    # --- 8. manifest
    if not dry_run and not out["errors"]:
        m.canonical_name = canonical_dir
        if not m.session_id:
            m.session_id = canonical_dir
        m.set_meta(
            nom_contrat=meta.nom_contrat,
            date_debut=meta.date_debut.isoformat() if meta.date_debut else None,
            n_site_tadarida=meta.n_site_tadarida,
            n_point_fixe=meta.n_point_fixe,
            n_passage=meta.n_passage,
            n_enregistreur=meta.n_enregistreur,
            n_serie=meta.n_serie,
        )

        # Si Summary.txt disponible, on en profite pour le parser une fois et
        # stocker le résultat dans extracted (évite de le re-parser plus tard)
        if "summary" not in m.extracted:
            for p in [final_path, final_path / (wav_dir.name if wav_dir_kind.startswith("subdir") else "")]:
                if p == final_path and wav_dir_kind.startswith("subdir"):
                    continue  # cas déjà géré au suivant
                try:
                    for child in p.iterdir():
                        if child.is_file() and child.name.lower().endswith("_summary.txt"):
                            s = parse_summary_txt(child)
                            if s:
                                m.set_extracted("summary", {
                                    "path": child.name,
                                    "start_dt": s.start_dt.isoformat() if s.start_dt else None,
                                    "end_dt": s.end_dt.isoformat() if s.end_dt else None,
                                    "temp_start": s.temp_start,
                                    "temp_end": s.temp_end,
                                    "temp_min": s.temp_min,
                                    "temp_max": s.temp_max,
                                    "lat": s.lat,
                                    "lon": s.lon,
                                    "battery_end": s.battery_end,
                                })
                                break
                except (OSError, PermissionError):
                    pass

        m.record_action(
            "rename",
            params={
                "prefix": prefix,
                "wav_dir_kind": wav_dir_kind,
                "rename_folder": rename_folder,
            },
            stats={
                "n_wav_found": out["n_wav_found"],
                "n_renamed": out["executed"],
                "n_already_ok": out["skipped_same_name"],
                "n_unreadable": len(out["unreadable"]),
                "serial_consistent": consistency["consistent"],
            },
            tool_version=TOOL_VERSION,
        )
        m.save(final_path)

    return out


# ---------------------------------------------------------------------------
# Auto-résolution depuis le Suivi (best-effort)
# ---------------------------------------------------------------------------

def try_auto_meta(session: Path) -> tuple[SessionMeta | None, list[str]]:
    """
    Tente de reconstruire les metadata depuis :
      - le nom du dossier (si format reconnu)
      - les séries observées dans les WAV
      - les infos du Suivi
      - Summary.txt pour la date

    Retourne (meta, messages). meta=None si impossible avec les infos dispo.
    """
    from suivi import Suivi, _default_path
    msgs: list[str] = []

    # Série dominante dans les WAV
    wav_dir = session if _dir_has_wavs(session) else _find_raw_wav_subdir(session)
    if wav_dir is None:
        msgs.append("pas de WAV trouvés, impossible de détecter la série")
        return None, msgs
    wav_names = [p.name for p in wav_dir.iterdir() if p.suffix.lower() == ".wav"]
    serials: dict[str, int] = {}
    for n in wav_names:
        s = extract_serial_from_name(n)
        if s:
            serials[s] = serials.get(s, 0) + 1
    dominant_serial = max(serials, key=serials.get) if serials else None
    if dominant_serial:
        msgs.append(f"série dominante détectée : {dominant_serial} ({serials[dominant_serial]} fichiers)")
    else:
        msgs.append("aucune série détectable dans les WAV")

    # Date début : Summary.txt ou 1er WAV
    date_debut: datetime | None = None
    for child in session.iterdir():
        if child.is_file() and child.name.lower().endswith("_summary.txt"):
            s = parse_summary_txt(child)
            if s and s.start_dt:
                date_debut = s.start_dt
                msgs.append(f"date début détectée via Summary.txt : {date_debut:%Y-%m-%d}")
                break
    if date_debut is None and wav_names:
        # fallback : plus petit timestamp dans les noms
        from naming import extract_timestamp_from_name
        dts = []
        for n in wav_names:
            ti = extract_timestamp_from_name(n)
            if ti:
                dts.append(ti[0])
        if dts:
            date_debut = min(dts)
            msgs.append(f"date début détectée via noms WAV : {date_debut:%Y-%m-%d}")

    # Lookup Suivi avec ce qu'on a
    try:
        suivi = Suivi(_default_path(year=date_debut.year if date_debut else None))
    except Exception as e:
        msgs.append(f"impossible de charger le Suivi : {e}")
        return None, msgs

    matches = suivi.find_row_for_session(
        date_debut=date_debut,
        serial=dominant_serial,
    )
    if not matches:
        # Fallback moins strict : juste la série
        matches = suivi.find_row_for_session(serial=dominant_serial) if dominant_serial else []
        if matches:
            msgs.append(f"{len(matches)} ligne(s) Suivi pour cette série (date différente)")
    else:
        msgs.append(f"{len(matches)} ligne(s) Suivi match (date + série)")

    if len(matches) == 1:
        row = matches[0]
        meta = SessionMeta(
            date_debut=row.date_debut or date_debut,
            n_site_tadarida=row.n_site_tadarida,
            n_point_fixe=row.n_point_fixe,
            n_passage=row.n_passage,
            n_enregistreur=row.n_enregistreur,
            n_serie=row.n_serie or dominant_serial,
            nom_contrat=row.nom_contrat,
        )
        msgs.append(f"match unique → {row.summary()}")
        return meta, msgs
    elif len(matches) > 1:
        msgs.append("plusieurs matchs, ambiguïté → renseigner point + passage manuellement")
        for r in matches[:5]:
            msgs.append(f"  candidat : {r.summary()}")
        return None, msgs
    else:
        msgs.append("aucun match dans le Suivi")
        return None, msgs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-exécute même si manifest indique 'déjà renommé'")
    ap.add_argument("--no-folder", dest="rename_folder", action="store_false",
                    help="ne pas renommer le dossier lui-même")
    ap.add_argument("--auto", action="store_true", help="tenter de deviner les metadata via Suivi")

    g = ap.add_argument_group("metadata (obligatoires sauf --auto)")
    g.add_argument("--site", help="6 chiffres du carré Tadarida")
    g.add_argument("--point", help="code du point (Z3, A1, ...)")
    g.add_argument("--pass", dest="pass_num", type=int)
    g.add_argument("--enr", type=int, help="n° enregistreur court (1-28)")
    g.add_argument("--serial", help="n° de série de l'enregistreur")
    g.add_argument("--date", help="date début (YYYY-MM-DD)")
    g.add_argument("--contrat", help="nom du contrat (informatif)")

    args = ap.parse_args()

    session = args.session.resolve()
    if not session.is_dir():
        print(f"❌ session introuvable : {session}", file=sys.stderr)
        return 2

    if args.auto:
        meta, msgs = try_auto_meta(session)
        for m in msgs:
            print(f"  · {m}")
        if meta is None:
            print("❌ auto-résolution impossible, renseigne les arguments manuellement", file=sys.stderr)
            return 2
    else:
        if not all([args.site, args.point, args.pass_num, args.enr, args.serial, args.date]):
            print("❌ --site --point --pass --enr --serial --date sont requis (sauf --auto)", file=sys.stderr)
            return 2
        meta = SessionMeta(
            date_debut=datetime.strptime(args.date, "%Y-%m-%d"),
            n_site_tadarida=args.site,
            n_point_fixe=args.point,
            n_passage=args.pass_num,
            n_enregistreur=args.enr,
            n_serie=args.serial,
            nom_contrat=args.contrat,
        )

    print(f"\nSession : {session}")
    print(f"Meta    : site={meta.n_site_tadarida} point={meta.n_point_fixe} "
          f"pass={meta.n_passage} enr=#{meta.n_enregistreur} série={meta.n_serie} "
          f"date={meta.date_debut:%Y-%m-%d}")

    res = rename_session(
        session=session,
        meta=meta,
        dry_run=args.dry_run,
        rename_folder=args.rename_folder,
        force=args.force,
    )

    print(f"\nCanonical dir   : {res.get('canonical_dir','?')}")
    print(f"WAV trouvés     : {res.get('n_wav_found', 0)}  ({res.get('wav_dir_kind', '?')})")
    print(f"À renommer      : {res.get('n_planned', 0)}")
    print(f"Déjà OK         : {res.get('skipped_same_name', 0)}")
    if res.get("unreadable"):
        print(f"Non interprétés : {len(res['unreadable'])}")
    if res.get("serial_check"):
        sc = res["serial_check"]
        status = "✓" if sc.get("consistent") else ("?" if sc.get("consistent") is None else "❌")
        print(f"Cohérence série : {status}  attendu={sc['expected']}  trouvé={sc['dominant_in_files']}")

    if res.get("planned"):
        print("\nÉchantillon du plan :")
        for s, d in res["planned"][:3]:
            print(f"  {Path(s).name}\n  → {Path(d).name}")
        if len(res["planned"]) > 3:
            print(f"  ... +{len(res['planned'])-3} autres")

    if args.dry_run:
        print("\n(dry-run, rien n'a été touché)")
    else:
        print(f"\nExécutés : {res['executed']}")
        print(f"Dossier final : {res['final_session_path']}")

    if res["warnings"]:
        print("\n⚠  Avertissements :")
        for w in res["warnings"]:
            print(f"   - {w}")
    if res["errors"]:
        print("\n❌ Erreurs :", file=sys.stderr)
        for e in res["errors"]:
            print(f"   - {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
