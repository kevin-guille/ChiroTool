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
import gc
import os
import shutil
import sys
import time
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
    is_audiomoth_twav,
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
    TOOL_VERSION = "?"          # version.py introuvable (improbable)


# ---------------------------------------------------------------------------
# Cœur : renommage d'une session
# ---------------------------------------------------------------------------

AV_SAFE_MARKER = "chirotool_avsafe.cfg"


def _av_safe_marker_present() -> bool:
    """True si un fichier marqueur ``chirotool_avsafe.cfg`` est posé à côté de
    l'exe (ou dans le dossier courant). Permet d'activer le mode compatible
    antivirus sur un poste verrouillé sans .bat ni variable d'environnement :
    il suffit de déposer ce fichier vide à côté de ChiroTool.exe."""
    roots = []
    try:
        if getattr(sys, "frozen", False):
            roots.append(Path(sys.executable).parent)
        else:
            roots.append(Path(__file__).resolve().parent)
    except Exception:
        pass
    try:
        roots.append(Path.cwd())
    except Exception:
        pass
    for r in roots:
        try:
            if (r / AV_SAFE_MARKER).exists():
                return True
        except Exception:
            pass
    return False


def _av_safe_pace() -> tuple[int, float] | None:
    """Mode « compatible antivirus » (opt-in) : renvoie ``(taille_lot, pause_s)``
    pour lisser le renommage en rafale, ou ``None`` si désactivé.

    Activation (dans l'ordre) :
      - variable d'environnement ``CHIROTOOL_AV_SAFE`` :
          "1"/"true" → défaut (lot 40, pause 0,25 s) ; "<lot>:<pause_ms>" → réglage
          fin (ex. "25:400") ; "0"/"off" → force désactivé (prioritaire) ;
      - sinon, fichier marqueur ``chirotool_avsafe.cfg`` à côté de l'exe → défaut.

    Sans rien, AUCUN effet → l'app reste identique et rapide sur tous les postes.
    Sert aux postes dont l'antivirus tue l'app pendant le renommage massif.
    """
    raw = os.environ.get("CHIROTOOL_AV_SAFE", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return None                       # désactivation explicite (prioritaire)
    if raw in ("1", "true", "yes", "on"):
        return (40, 0.25)
    if ":" in raw:
        try:
            batch_s, pause_ms = raw.split(":", 1)
            return (max(1, int(batch_s)), max(0.0, int(pause_ms) / 1000.0))
        except ValueError:
            return (40, 0.25)
    # Variable non posée → on regarde le fichier marqueur.
    if _av_safe_marker_present():
        return (40, 0.25)
    return None


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

    # --- 3.bis : garde-fou AudioMoth « T.WAV » brut (déclenché/concaténé)
    # Ces fichiers doivent d'abord être « expandés » (dé-concaténés + horodatés)
    # via l'AudioMoth Configuration App ou l'outil CEREMA/TWAV_splitter. Les
    # renommer/traiter tels quels donnerait des horodatages FAUX (tous les
    # événements collés au timestamp de départ). On refuse proprement.
    n_twav = sum(1 for p in wav_paths if is_audiomoth_twav(p.name))
    if n_twav:
        out["errors"].append(
            f"{n_twav} fichier(s) AudioMoth « T.WAV » brut détecté(s) "
            "(événements concaténés). Expandez-les d'abord (AudioMoth "
            "Configuration App → Expand, ou l'outil CEREMA/TWAV_splitter), "
            "puis relancez la préparation sur les fichiers .WAV obtenus."
        )
        out["audiomoth_twav_raw"] = n_twav
        return out

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

    # Aucun nom lisible (Titley usine avant le parse, Peersonic, …) : on arrête
    # AVANT d'enregistrer rename=ok et de lancer TE×10. Sinon Data_k n'a qu'une
    # tranche par fichier (collision de noms, issue #4 Mickaël).
    if unreadable and not plan and not same:
        sample = ", ".join(unreadable[:3])
        extra = "…" if len(unreadable) > 3 else ""
        out["errors"].append(
            f"Aucun nom de fichier lisible ({len(unreadable)} WAV). "
            f"Ex. : {sample}{extra}. "
            "Formats reconnus : Wildlife (SM4…), AudioMoth expandé, "
            "Titley Swift/Ranger (YYYY-MM-DD HH-MM-SS), Vigie-Chiro. "
            "Sinon, passer par XnView vers YYYYMMDD_HHMMSS.wav."
        )
        return out
    if unreadable:
        sample = ", ".join(unreadable[:3])
        extra = "…" if len(unreadable) > 3 else ""
        out["warnings"].append(
            f"{len(unreadable)} fichier(s) au nom non reconnu (ignorés) : "
            f"{sample}{extra}"
        )

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

    # Cible déjà existante sur disque (ex : relance après un run partiel
    # interrompu). On distingue deux cas :
    #   • cible IDENTIQUE à la source (même taille + même contenu) → doublon
    #     résiduel d'un renommage précédent non finalisé (typiquement casse
    #     mixte 2mu/2MU sur un système Windows insensible à la casse). La
    #     source est redondante : on l'exclut du plan et on la met en
    #     quarantaine (auto-cicatrisation), au lieu de bloquer toute la session.
    #   • cible DIFFÉRENTE → vrai conflit : on bloque (jamais d'écrasement).
    import filecmp
    real_conflicts: list[str] = []
    healed_dupes: list[tuple[Path, Path]] = []
    kept_plan: list[tuple[Path, Path]] = []
    for src, dst in plan:
        if not dst.exists():
            kept_plan.append((src, dst))
            continue
        try:
            identical = (src.stat().st_size == dst.stat().st_size
                         and filecmp.cmp(str(src), str(dst), shallow=False))
        except OSError:
            identical = False
        if identical:
            healed_dupes.append((src, dst))   # source redondante → quarantaine
        else:
            real_conflicts.append(dst.name)
    if real_conflicts:
        out["errors"].append(
            f"{len(real_conflicts)} fichier(s) cible existe(nt) déjà avec un "
            f"contenu DIFFÉRENT : {', '.join(real_conflicts[:3])}"
            f"{'…' if len(real_conflicts) > 3 else ''}. "
            "Aucun renommage effectué (risque d'écrasement)."
        )
        return out
    plan = kept_plan
    out["planned"] = [(str(s), str(d)) for s, d in plan]
    out["n_planned"] = len(plan)
    out["healed_duplicates"] = [dst.name for _, dst in healed_dupes]
    if healed_dupes:
        out["warnings"].append(
            f"{len(healed_dupes)} doublon(s) résiduel(s) identique(s) d'un run "
            f"précédent interrompu : source redondante mise en quarantaine "
            f"(_doublons_casse/), cible canonique conservée."
        )

    # --- 6. exécution
    if not dry_run:
        # Mode « compatible antivirus » (opt-in via CHIROTOOL_AV_SAFE) : lisse le
        # renommage en petits lots + micro-pauses pour rester sous le seuil
        # comportemental des antivirus. None par défaut → vitesse maximale.
        pace = _av_safe_pace()
        if pace:
            out["av_safe_mode"] = {"batch": pace[0], "pause_s": pace[1]}
        # Quarantaine des doublons résiduels identiques (auto-cicatrisation)
        if healed_dupes:
            quarantine = wav_dir / "_doublons_casse"
            quarantine.mkdir(exist_ok=True)
            for src, _dst in healed_dupes:
                try:
                    src.rename(quarantine / src.name)
                    out["quarantined"] = out.get("quarantined", 0) + 1
                except OSError as e:
                    out["warnings"].append(
                        f"doublon non déplacé {src.name} : {e}")
        _paced = 0
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
                if pace:
                    _paced += 1
                    if _paced >= pace[0]:
                        _paced = 0
                        time.sleep(pace[1])
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
            # Sous Windows, un handle encore ouvert sur un fichier du dossier
            # (scan de l'app, indexeur de recherche, antivirus) fait échouer le
            # renommage du DOSSIER, alors même que les WAV, eux, viennent d'être
            # renommés sans problème. On force un ramasse-miettes et on retente
            # brièvement pour laisser ces handles se libérer.
            err = None
            for attempt in range(4):
                try:
                    session.rename(target)
                    final_path = target
                    err = None
                    break
                except OSError as e:
                    err = e
                    gc.collect()
                    time.sleep(0.3 * (attempt + 1))
            if err is not None:
                # NON fatal : les WAV sont renommés, le TE×10 peut tourner sur le
                # dossier tel quel. On le signale clairement sans bloquer la nuit.
                out["folder_rename_failed"] = str(err)
                out["warnings"].append(
                    f"Le DOSSIER n'a pas pu être renommé en « {canonical_dir} » "
                    f"({err}). Les fichiers WAV sont bien renommés et le traitement "
                    f"continue sur le dossier actuel. Cause fréquente : l'explorateur "
                    f"Windows, un antivirus ou l'application qui garde le dossier "
                    f"ouvert. Fermez ces fenêtres et relancez « Préparer » (--force) "
                    f"pour lui donner son nom définitif.")
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
            from chiro_core import find_summary_file
            summ = find_summary_file(final_path)
            if summ is None and wav_dir_kind.startswith("subdir"):
                summ = find_summary_file(final_path / wav_dir.name)
            if summ is not None:
                s = parse_summary_txt(summ)
                if s:
                    m.set_extracted("summary", {
                        "path": summ.name,
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

def inspect_summary_vs_wav(session: Path) -> dict:
    """Compare le Summary.txt aux timestamps des WAV du dossier.

    Les WAV font foi. Un Summary cumulatif (carte SD non formatée) déclenche
    ``prefer_wav`` + ``warning`` (texte utilisateur).
    """
    from chiro_core import (
        find_summary_file,
        list_session_wav_names,
        parse_summary_txt,
        should_prefer_wav_dates,
        summary_vs_wav_warning,
    )
    from naming import wav_timestamp_range

    session = Path(session)
    wav_min, wav_max = wav_timestamp_range(list_session_wav_names(session))
    wav_dir = session if _dir_has_wavs(session) else _find_raw_wav_subdir(session)
    summ = find_summary_file(session) or (
        find_summary_file(wav_dir) if wav_dir is not None and wav_dir != session else None)
    summary_info = parse_summary_txt(summ) if summ is not None else None
    prefer = bool(should_prefer_wav_dates(summary_info, wav_min) and wav_min)
    return {
        "summary": summary_info,
        "summary_path": summ,
        "wav_min": wav_min,
        "wav_max": wav_max,
        "prefer_wav": prefer,
        "warning": summary_vs_wav_warning(summary_info, wav_min, wav_max),
    }


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

    info = inspect_summary_vs_wav(session)
    date_debut = None
    wav_min = info.get("wav_min")
    summary_info = info.get("summary")
    if info.get("prefer_wav") and wav_min:
        date_debut = wav_min
        if info.get("warning"):
            msgs.append(
                "⚠ Summary ≠ WAV (carte SD souvent non formatée) — "
                f"date prise sur les fichiers : {date_debut:%Y-%m-%d}"
            )
        else:
            msgs.append(f"date début détectée via noms WAV : {date_debut:%Y-%m-%d}")
    elif summary_info and summary_info.start_dt:
        date_debut = summary_info.start_dt
        summ_name = Path(info["summary_path"]).name if info.get("summary_path") else "Summary"
        msgs.append(
            f"date début détectée via {summ_name} : {date_debut:%Y-%m-%d}"
        )
    elif wav_min is not None:
        date_debut = wav_min
        msgs.append(f"date début détectée via noms WAV : {date_debut:%Y-%m-%d}")

    # Lookup Suivi avec ce qu'on a
    # Méta PARTIELLE à partir de ce qu'on a détecté, sans dépendre d'aucun
    # fichier externe : date + série + nom de la campagne (dossier parent).
    # On la renvoie toujours → le wizard pré-remplit ce qu'il peut et l'utilisateur
    # complète le carré / point (liste API, points récents) au lieu de voir une
    # erreur de fichier introuvable.
    contrat_guess = session.parent.name if session.parent else None
    partial = SessionMeta(
        date_debut=date_debut,
        n_serie=dominant_serial,
        nom_contrat=contrat_guess,
    )
    todo = "site/point à compléter (liste des carrés ou points récents)"

    # Enrichissement OPTIONNEL via le Suivi xlsx local, UNIQUEMENT s'il existe.
    # Son absence est le cas normal → aucun message d'erreur.
    try:
        suivi_path = _default_path(year=date_debut.year if date_debut else None)
    except Exception:
        suivi_path = None
    if not suivi_path or not suivi_path.is_file():
        msgs.append(todo)
        return partial, msgs
    try:
        suivi = Suivi(suivi_path)
    except Exception:
        msgs.append(todo)
        return partial, msgs

    matches = suivi.find_row_for_session(date_debut=date_debut, serial=dominant_serial)
    if not matches and dominant_serial:
        matches = suivi.find_row_for_session(serial=dominant_serial)
        if matches:
            msgs.append(f"{len(matches)} ligne(s) Suivi pour cette série (date différente)")
    elif matches:
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
            nom_contrat=row.nom_contrat or contrat_guess,
        )
        msgs.append(f"match unique → {row.summary()}")
        return meta, msgs
    if len(matches) > 1:
        msgs.append("plusieurs matchs Suivi → complète point + passage")
    else:
        msgs.append(todo)
    return partial, msgs


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
