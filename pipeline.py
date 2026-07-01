"""
pipeline.py — orchestrateur du traitement complet d'une session.

Chaîne les briques dans le bon ordre, en s'arrêtant proprement aux points
d'interaction humaine non-automatisables.

Phases :

  1. PREP (local)     : rename --auto  →  te10  →  suivi_write (Lupas+Kal ✓)
  2. UPLOAD (cloud)   : create_participation  →  upload WAVs  →  trigger_compute
                         →  suivi_write (Tadarida ✓)
  3. WAIT (cloud)     : poll l'API jusqu'à l'état TERMINE/FINI
  4. FETCH (cloud)    : download_observations_as_xlsx
  5. CLEANUP (local)  : nettoyage seuils  →  suivi_write (état fini)

Chaque phase :
  - est idempotente (vérifie le manifest avant d'agir)
  - peut être lancée individuellement (--only PHASE)
  - journalise dans le manifest + stdout
  - sait s'interrompre proprement (Ctrl+C) sans corrompre l'état

Usage :

    # Tout faire, stop à la première étape humaine manquante
    python pipeline.py <session> --advance

    # Une phase précise (utile pour déboguer)
    python pipeline.py <session> --only prep
    python pipeline.py <session> --only cleanup --threshold-chiros 0.5

    # Avec API (nécessite un token enregistré)
    python pipeline.py <session> --advance --use-api

Conventions :
  - Le dossier session doit être déjà classé sous une campagne, avec WAV
    bruts dans <session>/ ou <session>/Data/, et (si SM4BAT) un Summary.txt.
  - Les métadonnées sont résolues dans l'ordre :
      1. Arguments CLI (--site --point --pass --enr ...)
      2. Manifest existant (si déjà tourné une fois)
      3. Auto-résolution via le Suivi
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

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

from campaign_log import log_to_campaign
from chiro_core import _dir_has_wavs, _find_raw_wav_subdir, parse_summary_txt
from manifest import Manifest
from naming import SessionMeta, canonical_session_dirname
from verify import verify_cleanup, verify_rename, verify_te10


PHASES = ("prep", "upload", "wait", "fetch", "cleanup")
try:
    from version import __version__ as TOOL_VERSION
except Exception:
    TOOL_VERSION = "?"          # version.py introuvable (improbable)


# ---------------------------------------------------------------------------
# Résolution des métadonnées
# ---------------------------------------------------------------------------

def _find_existing_participation(client, *, site_id: str, point: str,
                                  date_debut) -> dict | None:
    """Cherche une participation déjà créée sur (site, point, date).

    Match sur : même site_id, même point (insensible casse), même jour
    calendaire (date_debut). Évite les doublons en cas de double-clic
    wizard ou de crash pipeline entre POST participation et save manifest.
    Retourne le dict brut de l'API ou None si aucun match.
    """
    if not (site_id and point and date_debut):
        return None
    point_norm = str(point).upper().strip()
    # Le format date_debut peut être datetime ou string ISO
    try:
        if hasattr(date_debut, "date"):
            target_day = date_debut.date().isoformat()
        else:
            target_day = str(date_debut)[:10]
    except Exception:
        return None

    try:
        for p in client.iter_participations(mine_only=True):
            # site peut être un ObjectId string ou un embedded dict
            site_ref = p.get("site")
            p_site_id = site_ref.get("_id") if isinstance(site_ref, dict) \
                else str(site_ref or "")
            if p_site_id != site_id:
                continue
            p_point = str(p.get("point") or "").upper().strip()
            if p_point != point_norm:
                continue
            p_date = str(p.get("date_debut") or "")[:10]
            if p_date != target_day:
                continue
            return p
    except Exception:
        return None
    return None


def _participation_window(date_debut, date_fin=None):
    """Calcule ``(date_debut, date_fin)`` pour la création d'une participation.

    - ``date_fin`` fourni (wizard GUI) → inchangé.
    - sinon, on modélise une nuit : si ``date_debut`` est à MINUIT (on ne
      connaît que la date : match Suivi / --date CLI), on le décale à ~20:00 ;
      ``date_fin`` = 06:00, reporté au lendemain si nécessaire. Évite une
      participation de 6 h démarrant à minuit dans la base nationale.

    Fonction PURE → testable (voir tests/test_core.py :: TestParticipationWindow).
    """
    from datetime import timedelta
    if date_debut is None:
        return None, date_fin
    if date_fin is not None:
        return date_debut, date_fin
    if date_debut.hour == 0 and date_debut.minute == 0:
        date_debut = date_debut.replace(hour=20)
    date_fin = date_debut.replace(hour=6, minute=0)
    if date_fin <= date_debut:
        date_fin = date_fin + timedelta(days=1)
    return date_debut, date_fin


def resolve_meta(
    session: Path,
    cli_args: argparse.Namespace,
) -> tuple[SessionMeta | None, list[str]]:
    """
    Essaie de construire un SessionMeta à partir de plusieurs sources :
      1. Arguments CLI explicites
      2. Manifest existant
      3. Auto-résolution via le Suivi (nom dossier / série WAV / Summary.txt)

    Retourne (meta, messages). meta=None si impossible.
    """
    msgs: list[str] = []

    # 1. Arguments CLI
    cli_has_all = all([
        cli_args.site, cli_args.point, cli_args.pass_num is not None,
        cli_args.enr is not None, cli_args.serial, cli_args.date,
    ])
    if cli_has_all:
        try:
            dt = datetime.strptime(cli_args.date, "%Y-%m-%d")
        except ValueError:
            msgs.append(f"date invalide : {cli_args.date!r}")
            return None, msgs
        meta = SessionMeta(
            date_debut=dt,
            n_site_tadarida=str(cli_args.site).zfill(6),
            n_point_fixe=cli_args.point,
            n_passage=cli_args.pass_num,
            n_enregistreur=cli_args.enr,
            n_serie=cli_args.serial,
            nom_contrat=cli_args.contrat,
        )
        msgs.append("meta issues des arguments CLI")
        return meta, msgs

    # 2. Manifest
    m = Manifest.load(session)
    if m and m.meta and all(k in m.meta for k in
                            ("n_site_tadarida", "n_point_fixe", "n_passage",
                             "n_enregistreur", "n_serie", "date_debut")):
        try:
            dt = datetime.fromisoformat(m.meta["date_debut"])
        except (TypeError, ValueError):
            dt = None
        if dt:
            meta = SessionMeta(
                date_debut=dt,
                n_site_tadarida=m.meta["n_site_tadarida"],
                n_point_fixe=m.meta["n_point_fixe"],
                n_passage=int(m.meta["n_passage"]),
                n_enregistreur=int(m.meta["n_enregistreur"]),
                n_serie=m.meta["n_serie"],
                nom_contrat=m.meta.get("nom_contrat"),
            )
            msgs.append("meta issue du manifest existant")
            return meta, msgs

    # 3. Auto via Suivi
    try:
        from rename import try_auto_meta
        meta, auto_msgs = try_auto_meta(session)
        msgs.extend(auto_msgs)
        return meta, msgs
    except Exception as e:
        msgs.append(f"auto-résolution en échec : {e}")
        return None, msgs


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

class PipelineResult:
    def __init__(self):
        self.stopped_at: str | None = None     # phase où on s'est arrêté
        self.waiting_for: str | None = None    # intervention humaine attendue
        self.phases_done: list[str] = []
        self.errors: list[str] = []
        self.final_session_path: Path | None = None

    def to_dict(self) -> dict:
        return {
            "stopped_at": self.stopped_at,
            "waiting_for": self.waiting_for,
            "phases_done": self.phases_done,
            "errors": self.errors,
            "final_session_path": str(self.final_session_path) if self.final_session_path else None,
        }


def run_phase_prep(session: Path, meta: SessionMeta, dry_run: bool,
                    force: bool, progress=None) -> dict:
    """Phase 1 : renommage + TE×10 + update Suivi local.

    ``progress`` : callback ``(done, total, label)`` appelé pendant TE×10
    pour alimenter la barre de progression GUI. Le renommage est trop rapide
    pour mériter un tracking (souvent < 1s même sur 2000 WAV) — on signale
    juste "rename en cours" puis "TE×10 en cours" via le label.
    """
    from rename import rename_session
    from te10 import process_folder

    out: dict = {"phase": "prep", "steps": []}

    # 1.a : renommage
    if progress is not None:
        progress(0, 100, "rename")
    r = rename_session(session, meta, dry_run=dry_run, rename_folder=True, force=force)
    out["steps"].append({"step": "rename", **r})
    if r.get("errors"):
        out["error"] = f"rename a échoué : {r['errors']}"
        return out
    final = Path(r.get("final_session_path") or session)

    # 1.b : TE×10 — progress fin tranche par fichier traité
    wav_dir = final if _dir_has_wavs(final) else _find_raw_wav_subdir(final)
    if wav_dir is None:
        out["error"] = "aucun WAV trouvé pour TE×10"
        return out
    te_out = final / "Data_k"
    te_jobs = max(1, (os.cpu_count() or 2) - 1)
    te_r = process_folder(wav_dir, te_out, factor=10, segment_s=5.0,
                          jobs=te_jobs, dry_run=dry_run, overwrite=False,
                          progress=progress)
    out["steps"].append({"step": "te10", **te_r})

    # 1.c : manifest + journal campagne + vérification indépendante
    m = Manifest.load_or_create(final)
    if not dry_run and "error" not in te_r:
        # -- rename : verif indépendante --
        try:
            vr = verify_rename(final, expected_serial=meta.n_serie)
            rename_status = "ok" if vr.ok else "verify_failed"
            rename_notes = vr.short() if not vr.ok else None
        except Exception as e:
            rename_status = "error"
            rename_notes = f"verify crash: {e}"
        m.record_action(
            "rename", status=rename_status, notes=rename_notes,
            params={"prefix_meta": meta.n_site_tadarida},
            stats={"n_planned": r.get("n_planned"), "executed": r.get("executed")},
            tool_version=TOOL_VERSION,
        )
        log_to_campaign(final, phase="prep", action="rename",
                        status=rename_status,
                        stats={"n_planned": r.get("n_planned"),
                               "executed": r.get("executed")},
                        notes=rename_notes,
                        tool_version=TOOL_VERSION)

        # -- te10 : verif indépendante --
        try:
            vt = verify_te10(final)
            te_status = "ok" if vt.ok else "verify_failed"
            te_notes = vt.short() if not vt.ok else None
        except Exception as e:
            te_status = "error"
            te_notes = f"verify crash: {e}"
        # Ceinture + bretelles : si le backend a signalé des erreurs d'écriture
        # ou de planification (fichier verrouillé, disque plein…), on refuse le
        # "ok" même si la vérif globale passe → l'étape reste reprenable.
        if te_r.get("errors", 0) > 0 and te_status == "ok":
            te_status = "error"
            te_notes = f"{te_r['errors']} erreur(s) TE×10 signalée(s) par le backend"
        m.record_action(
            "te10", status=te_status, notes=te_notes,
            params={"factor": 10, "segment_s": 5.0},
            stats={"n_source_wavs": te_r.get("n_source_wavs"),
                   "n_segments": te_r.get("n_planned_segments"),
                   "written": te_r.get("written", 0)},
            tool_version=TOOL_VERSION,
        )
        m.save(final)
        log_to_campaign(final, phase="prep", action="te10",
                        status=te_status,
                        stats={"n_source_wavs": te_r.get("n_source_wavs"),
                               "written": te_r.get("written", 0)},
                        notes=te_notes,
                        tool_version=TOOL_VERSION)

        # Remonter un warning dans out si vérif a échoué
        if rename_status != "ok" or te_status != "ok":
            out.setdefault("warnings", []).append(
                f"Vérification indépendante : rename={rename_status} "
                f"te10={te_status} — voir manifest")

    # 1.d : Suivi write (flag_lupas_kaleidoscope = True)
    try:
        from suivi import _default_path
        from suivi_write import SuiviWriter, RowKey, SuiviFileLockedError
        suivi_path = _default_path(meta.date_debut.year if meta.date_debut else None)
        if suivi_path.is_file():
            w = SuiviWriter(suivi_path)
            key = RowKey(
                nom_contrat=meta.nom_contrat,
                date_debut=meta.date_debut,
                n_site_tadarida=meta.n_site_tadarida,
                n_point_fixe=meta.n_point_fixe,
                n_passage=meta.n_passage,
                n_enregistreur=meta.n_enregistreur,
            )
            if not dry_run:
                res = w.update_row(
                    key,
                    {"flag_lupas_kaleidoscope": True,
                     "n_serie": meta.n_serie,
                     "etat": "pré-traitement OK"},
                    create_if_missing=True,
                )
                out["steps"].append({"step": "suivi_write", **res})
            else:
                out["steps"].append({"step": "suivi_write", "dry_run": True})
    except SuiviFileLockedError as e:
        out["steps"].append({"step": "suivi_write", "warning": str(e)})
    except Exception as e:
        out["steps"].append({"step": "suivi_write", "warning": f"skipped: {e}"})

    out["final_session_path"] = str(final)
    return out


def run_phase_upload(session: Path, meta: SessionMeta, dry_run: bool,
                     token: str | None,
                     participation_payload: dict | None = None,
                     progress=None,
                     max_workers: int = 4) -> dict:
    """Phase 2 : create_participation + upload WAVs + trigger_compute.

    Args:
        progress: callback optionnel `progress(done, total, phase_label)`
                  appelé depuis le thread worker à chaque WAV uploadé.
                  Thread-safe : la GUI wrappera via after(0, ...) côté
                  appelant.
        max_workers: nombre de connexions simultanées S3 (défaut 4). Sur
                     fibre avec bande passante montante correcte, 4 est un
                     bon compromis (n'étouffe pas l'API Eve pour les
                     POST /fichiers, et sature la bande passante montante
                     de la plupart des connexions BE).
    """
    out: dict = {"phase": "upload", "steps": []}

    if token is None:
        return {"phase": "upload", "error": "aucun token API, phase upload requiert --use-api"}

    from vigiechiro_api import VigieChiroClient

    m = Manifest.load_or_create(session)
    if m.is_done("upload"):
        out["skipped"] = "déjà uploadé selon le manifest"
        return out

    # Besoin de l'ID site Vigie-Chiro (pas juste le n° Tadarida)
    # On le récupère depuis le manifest (si stocké) ou via API (cherche par numéro)
    site_id = m.meta.get("vigiechiro_site_id") if m.meta else None
    if not site_id:
        if dry_run:
            out["steps"].append({"step": "resolve_site_id",
                                 "dry_run": True,
                                 "note": f"devra chercher site n°{meta.n_site_tadarida} via API"})
            return out
        client = VigieChiroClient(token)
        # Résolution globale : le carré peut appartenir à un AUTRE observateur
        # (modèle v0.2 — on dépose sa nuit sur le carré d'autrui). On ne se
        # limite donc plus à mine_only.
        match = client.find_site_by_numero(meta.n_site_tadarida)
        if match is None:
            return {"phase": "upload",
                    "error": (f"aucun carré Vigie-Chiro ne correspond au "
                              f"n° {meta.n_site_tadarida} (ni dans vos sites, "
                              f"ni chez un autre observateur). Créez-le via "
                              f"l'onglet Carte si besoin.")}
        site_id = match.id
        m.set_meta(vigiechiro_site_id=site_id)
        m.save(session)
    out["steps"].append({"step": "resolve_site_id", "site_id": site_id})

    # create_participation
    part_id = m.meta.get("vigiechiro_participation_id")
    if not part_id:
        if dry_run:
            out["steps"].append({"step": "create_participation", "dry_run": True,
                                 "payload": {"site": site_id, "point": meta.n_point_fixe,
                                             "date_debut": meta.date_debut.isoformat() if meta.date_debut else None}})
            return out
        # Payload enrichi (wizard GUI) ou défauts
        pp = participation_payload or {}
        date_debut = pp.get("date_debut") or meta.date_debut
        # Fenêtre temporelle (helper pur testable). Le dédoublonnage matche par
        # JOUR calendaire (cf _find_existing_participation), donc décaler l'heure
        # dans la même journée ne casse pas la détection de doublon.
        date_debut, date_fin = _participation_window(date_debut, pp.get("date_fin"))

        client = VigieChiroClient(token)

        # --- Détection de doublon AVANT la création ---
        # Protection contre les double-cliques et reprises après crash : si
        # une participation existe déjà sur (site_id, date_debut, point), on
        # la réutilise au lieu d'en créer une seconde qui polluerait la base
        # Vigie-Chiro. Les participations mal synchronisées côté manifest
        # (vigiechiro_participation_id absent mais créée côté serveur) sont
        # rattrapées ici.
        try:
            same_day_existing = _find_existing_participation(
                client, site_id=site_id, point=meta.n_point_fixe,
                date_debut=date_debut,
            )
            if same_day_existing:
                part_id_existing = same_day_existing.get("_id") or \
                    same_day_existing.get("id")
                if part_id_existing:
                    print(
                        f"  ⚠ participation existante détectée "
                        f"(ID={part_id_existing}) — réutilisée au lieu d'en "
                        f"créer une seconde.",
                        flush=True,
                    )
                    out["steps"].append({
                        "step": "reuse_existing_participation",
                        "participation_id": part_id_existing,
                    })
                    m.set_meta(vigiechiro_participation_id=part_id_existing)
                    m.save(session)
                    part_id = part_id_existing
        except Exception as e:
            # Doublon non détecté par erreur réseau → on log mais on continue
            print(f"  (détection doublon impossible : {e})", flush=True)

        if part_id:
            # Réutilisation validée, on saute create_participation
            out["steps"].append({"step": "create_participation",
                                 "reused": True,
                                 "participation_id": part_id})
        else:
            part = client.create_participation(
                site_id,
                date_debut=date_debut,
                date_fin=date_fin,
                point=pp.get("point") or meta.n_point_fixe,
                meteo=pp.get("meteo"),
                configuration=pp.get("configuration"),
                commentaire=pp.get("commentaire"),
            )
            part_id = part.get("_id") or part.get("id")
            if not part_id:
                return {"phase": "upload", "error": f"pas d'_id dans la réponse : {part}"}
            m.set_meta(vigiechiro_participation_id=part_id)
            m.save(session)
            out["steps"].append({"step": "create_participation",
                                 "participation_id": part_id})

    # upload des WAVs de Data_k/
    data_k = session / "Data_k"
    if not data_k.is_dir():
        return {"phase": "upload", "error": f"Data_k/ introuvable : {data_k}"}
    wavs = sorted(data_k.glob("*.wav"))
    out["steps"].append({"step": "list_wavs", "n": len(wavs)})

    if dry_run:
        out["steps"].append({"step": "upload_wavs", "dry_run": True,
                             "would_upload": len(wavs)})
    else:
        client = VigieChiroClient(token)
        uploaded: list[str] = []
        failed: list[tuple[str, str]] = []

        # REPRISE D'UPLOAD : si la participation existait déjà (création
        # précédente interrompue), on liste les fichiers déjà uploadés côté
        # serveur et on les exclut de la queue. Évite de créer des doublons
        # et fait gagner un temps massif en cas de reprise après crash.
        already_uploaded: set[str] = set()
        try:
            already_uploaded = set(client.list_participation_files(part_id))
        except Exception:
            already_uploaded = set()
        if already_uploaded:
            wavs_before = len(wavs)
            wavs = [w for w in wavs if w.name not in already_uploaded]
            n_skipped = wavs_before - len(wavs)
            if n_skipped > 0:
                print(
                    f"  ↻ reprise : {n_skipped}/{wavs_before} WAV déjà sur le "
                    f"serveur — saut de l'upload pour ceux-là",
                    flush=True,
                )
                out["steps"].append({
                    "step": "resume_upload",
                    "already_uploaded": n_skipped,
                    "remaining": len(wavs),
                })
        if not wavs:
            # Tout est déjà uploadé → on saute direct au trigger_compute
            # (qui est idempotent côté serveur).
            print("  ✓ tous les WAV sont déjà sur le serveur", flush=True)
            out["steps"].append({"step": "upload_wavs", "uploaded": 0,
                                  "failed": [], "all_already_present": True})
            try:
                client.trigger_compute(part_id)
                out["steps"].append({"step": "trigger_compute",
                                      "participation_id": part_id})
            except Exception as e:
                print(f"  ⚠ trigger_compute : {e}", flush=True)
            m.flags["uploaded"] = True
            m.save(session)
            return out

        # Parallélisation : sur 500 WAV × 3 MB, l'upload séquentiel cumule
        # ~3 RTT/WAV en latence (POST /fichiers + PUT S3 + POST finalize) et
        # ne sature jamais la bande passante. Avec 4 workers en parallèle,
        # on chevauche les latences et on exploite mieux la ligne montante.
        # Gain typique : ×3 à ×5 sur cette phase (la plus longue du workflow).
        #
        # Thread-safety :
        # - requests.Session utilisé par VigieChiroClient est thread-safe
        #   pour .request() (connection pool interne de urllib3 partagé)
        # - uploaded/failed sont protégés par un lock court pour les appends
        # - le client est partagé entre workers (token auth basic stateless)
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time

        lock = threading.Lock()
        start_ts = time.monotonic()
        total = len(wavs)
        done_counter = {"n": 0}

        def _upload_one(wav):
            try:
                client.upload_wav(part_id, wav)
                with lock:
                    uploaded.append(wav.name)
                    done_counter["n"] += 1
                    n_done = done_counter["n"]
            except Exception as e:
                with lock:
                    failed.append((wav.name, str(e)))
                    done_counter["n"] += 1
                    n_done = done_counter["n"]

            # Rapport vers la GUI (toutes les 1 file, la GUI applique son
            # propre throttling si besoin). Format : (done, total, label).
            if progress is not None:
                try:
                    progress(n_done, total, "upload WAV")
                except Exception:
                    pass
            # Log console en plus, tous les 20 fichiers ou à la fin
            if n_done % 20 == 0 or n_done == total:
                elapsed = time.monotonic() - start_ts
                rate = n_done / elapsed if elapsed > 0 else 0
                eta = int((total - n_done) / rate) if rate > 0 else -1
                with lock:
                    print(
                        f"  upload : {n_done}/{total}  "
                        f"(erreurs: {len(failed)})  "
                        f"~{rate:.1f} WAV/s  "
                        f"ETA {eta}s" if eta >= 0 else
                        f"  upload : {n_done}/{total}  (erreurs: {len(failed)})",
                        flush=True,
                    )

        # `max_workers` borné à [1, 8] — au-delà de 8, on risque le 429 sur
        # Eve POST /fichiers, et la bande passante montante sature de toute
        # façon. En dessous de 1, on traite séquentiellement (fallback).
        mw = max(1, min(8, int(max_workers)))
        with ThreadPoolExecutor(max_workers=mw) as pool:
            futures = [pool.submit(_upload_one, w) for w in wavs]
            # Attend la complétion de toutes les tasks
            for _ in as_completed(futures):
                pass
        out["steps"].append({
            "step": "upload_wavs",
            "uploaded": len(uploaded),
            "failed": failed[:10],
            "workers": mw,
        })

        # trigger compute — UNIQUEMENT si tous les WAV sont passés.
        # Sinon Tadarida analyserait un jeu incomplet et l'utilisateur croirait
        # la nuit entièrement traitée (risque scientifique : sous-estimation
        # d'activité). On bloque et on remonte une erreur explicite ; le manifest
        # n'est PAS marqué uploaded → la session reste "à reprendre" et un
        # nouveau clic Upload reprendra les WAV manquants (reprise d'upload).
        if failed:
            print(
                f"  ⚠ {len(failed)} WAV en échec — analyse Tadarida NON déclenchée "
                f"(éviter une analyse sur données incomplètes).",
                flush=True,
            )
            out["steps"].append({
                "step": "trigger_compute",
                "skipped": True,
                "reason": f"{len(failed)} échecs d'upload",
            })
            out["error"] = (
                f"{len(failed)}/{len(wavs)} WAV n'ont pas pu être uploadés. "
                "L'analyse n'a pas été lancée pour éviter un résultat partiel. "
                "Relance « Upload + Tadarida » : seuls les WAV manquants seront "
                "renvoyés (reprise automatique)."
            )
            # On enregistre quand même l'action en 'partial' pour la traçabilité
            m.record_action("upload", status="partial",
                            params={"participation_id": part_id},
                            stats={"n_wavs": len(wavs),
                                   "uploaded_now": len(uploaded),
                                   "failed": len(failed)},
                            notes=f"{len(failed)} échecs — compute non déclenché",
                            tool_version=TOOL_VERSION)
            m.save(session)
            log_to_campaign(session, phase="upload", action="upload_wavs",
                            status="partial",
                            stats={"n_wavs": len(wavs),
                                   "uploaded": len(uploaded),
                                   "failed": len(failed)},
                            tool_version=TOOL_VERSION)
            return out

        client.trigger_compute(part_id)
        out["steps"].append({"step": "trigger_compute", "participation_id": part_id})

        upload_status = "ok"
        n_skipped = len(already_uploaded.intersection(
            set(w.name for w in sorted(data_k.glob("*.wav")))))
        stats_upload = {
            "n_wavs": len(wavs) + n_skipped,
            "uploaded_now": len(uploaded),
            "already_present": n_skipped,
            "failed": len(failed),
        }
        notes_bits = []
        if n_skipped:
            notes_bits.append(f"{n_skipped} déjà présents (reprise)")
        if failed:
            notes_bits.append(f"{len(failed)} échecs")
        notes = " · ".join(notes_bits) if notes_bits else None
        m.record_action("upload",
                        status=upload_status,
                        params={"participation_id": part_id},
                        stats=stats_upload,
                        notes=notes,
                        tool_version=TOOL_VERSION)
        m.save(session)
        log_to_campaign(session, phase="upload", action="upload_wavs",
                        status=upload_status,
                        stats=stats_upload,
                        tool_version=TOOL_VERSION)

    return out


def run_phase_wait(session: Path, token: str | None, poll_interval: int = 60,
                    progress=None) -> dict:
    """Phase 3 : poll jusqu'à TERMINE/FINI.

    ``progress`` : si fourni, appelé à chaque poll avec
    ``(elapsed_seconds, max_seconds, label_with_state)`` pour alimenter la
    barre GUI. Comme on ne connaît pas d'avance la durée Tadarida (typiquement
    1-30 min mais ça peut aller jusqu'à 3h sur le plus gros), la barre se
    remplit en référence à `max_wait` (3h). Pas idéal pour les petites
    sessions mais ça donne une indication "ça tourne, pas planté".
    """
    if token is None:
        return {"phase": "wait", "error": "token API requis"}
    m = Manifest.load_or_create(session)
    part_id = (m.meta or {}).get("vigiechiro_participation_id")
    if not part_id:
        return {"phase": "wait", "error": "pas d'ID participation dans le manifest"}

    from vigiechiro_api import VigieChiroClient
    client = VigieChiroClient(token)

    MAX_WAIT = 3 * 3600  # cf. wait_for_completion défaut

    def _report(etat, elapsed):
        print(f"  [{elapsed:>5}s] état = {etat}", flush=True)
        if progress is not None:
            try:
                progress(min(elapsed, MAX_WAIT), MAX_WAIT,
                         f"wait Tadarida ({etat})")
            except Exception:
                pass

    etat = client.wait_for_completion(part_id, poll_interval=poll_interval,
                                       max_wait=MAX_WAIT, on_poll=_report)
    done = etat in ("TERMINE", "FINI")
    log_to_campaign(session, phase="wait", action="wait_for_completion",
                    status="ok" if done else "warning",
                    stats={"final_state": etat},
                    tool_version=TOOL_VERSION)
    out = {"phase": "wait", "final_state": etat}
    if not done:
        # État non terminal : ERROR/ERREUR (échec Tadarida) ou délai dépassé
        # (EN_COURS). On NE poursuit PAS vers fetch/cleanup — éviter d'analyser
        # ou de nettoyer sur un xlsx absent/incomplet (un échec PARTIEL passe
        # sous le garde-fou mass-delete >80 %). L'utilisateur relancera plus tard.
        out["error"] = (f"analyse Tadarida non terminée (état={etat}) — "
                        f"fetch/cleanup non lancés")
    return out


def run_phase_fetch(session: Path, token: str | None, force: bool = False,
                     progress=None) -> dict:
    """Phase 4 : télécharge l'xlsx d'observations dans la racine de session.

    ``progress`` : appelé pendant le download avec
    (donnees_lues, donnees_total, "fetch xlsx").
    """
    if token is None:
        return {"phase": "fetch", "error": "token API requis"}
    m = Manifest.load_or_create(session)
    part_id = (m.meta or {}).get("vigiechiro_participation_id")
    if not part_id:
        return {"phase": "fetch", "error": "pas d'ID participation dans le manifest"}

    # Si déjà un xlsx "participation-…-observations.xlsx", skip sauf --force
    existing = [p for p in session.iterdir()
                if p.is_file() and p.name.lower().startswith("participation-")
                and "observations" in p.name.lower()
                and p.suffix.lower() in (".xlsx", ".csv")
                and "_cleanup" not in p.name.lower()]
    if existing and not force:
        return {"phase": "fetch", "skipped": f"xlsx déjà présent : {existing[0].name}"}

    from vigiechiro_api import VigieChiroClient
    client = VigieChiroClient(token)
    dst = session / f"participation-{part_id}-observations.xlsx"

    last = [0]
    def _p(seen, total):
        import time
        now = time.monotonic()
        if now - last[0] > 1.0 or seen == total:
            last[0] = now
            pct = (seen / total * 100) if total else 0
            print(f"\r  progress : {seen}/{total} ({pct:.1f}%)", end="", flush=True)
        # Propage aussi vers la barre GUI si fournie
        if progress is not None:
            try:
                progress(seen, max(total, 1), "fetch xlsx")
            except Exception:
                pass

    res = client.download_observations_as_xlsx(part_id, dst, on_progress=_p)
    print()  # fin de la ligne progress
    m.record_action("fetch_observations",
                    status="ok",
                    params={"participation_id": part_id},
                    stats=res, tool_version=TOOL_VERSION)
    m.save(session)
    log_to_campaign(session, phase="fetch", action="download_observations",
                    stats={"n_files": res.get("n_files"),
                           "n_contacts": res.get("n_contacts")},
                    tool_version=TOOL_VERSION)
    return {"phase": "fetch", **res}


def run_phase_cleanup(
    session: Path,
    thresholds: dict[str, float],
    disabled: set[str],
    silent_policy: str,
    unknown_action: str,
    dry_run: bool,
    force: bool,
    meta: SessionMeta | None = None,
    progress=None,
) -> dict:
    """Phase 5 : purge des observations + annotation xlsx + update Suivi.

    ``progress`` propagé à ``cleanup_session`` qui l'appelle pour chaque WAV
    supprimé (gros volumes : 60-80% de plusieurs milliers de WAV).
    """
    from cleanup import cleanup_session

    res = cleanup_session(
        session=session,
        thresholds=thresholds,
        disabled=disabled,
        silent_policy=silent_policy,
        unknown_action=unknown_action,
        dry_run=dry_run,
        force=force,
        progress=progress,
    )

    # Vérification indépendante (non-dry-run uniquement)
    if not dry_run and not res.get("errors"):
        try:
            vc = verify_cleanup(session)
            cleanup_status = "ok" if vc.ok else "verify_failed"
            cleanup_notes = vc.short() if not vc.ok else None
        except Exception as e:
            cleanup_status = "error"
            cleanup_notes = f"verify crash: {e}"
        # Écraser la dernière action cleanup du manifest avec le vrai status
        m = Manifest.load_or_create(session)
        # Chercher la dernière action cleanup pour la patcher
        for a in reversed(m.actions):
            if a.type == "cleanup":
                a.status = cleanup_status
                if cleanup_notes:
                    a.notes = cleanup_notes
                break
        m.save(session)
        if cleanup_status != "ok":
            res.setdefault("warnings", []).append(
                f"Vérification indépendante cleanup : {cleanup_status} "
                f"({cleanup_notes})")

    # 5.b : écriture dans le Suivi du récap cleanup (visibilité contrat)
    if not dry_run and meta and not res.get("errors"):
        try:
            from suivi import _default_path
            from suivi_write import SuiviWriter, RowKey, SuiviFileLockedError
            suivi_path = _default_path(meta.date_debut.year if meta.date_debut else None)
            if suivi_path.is_file():
                w = SuiviWriter(suivi_path)
                key = RowKey(
                    nom_contrat=meta.nom_contrat,
                    date_debut=meta.date_debut,
                    n_site_tadarida=meta.n_site_tadarida,
                    n_point_fixe=meta.n_point_fixe,
                    n_passage=meta.n_passage,
                    n_enregistreur=meta.n_enregistreur,
                )
                stats = res.get("stats", {})
                files = stats.get("files", {})
                mb = files.get("bytes_to_delete", 0) / (1024 * 1024)
                disabled_txt = (" disabled=" + ",".join(sorted(disabled))) if disabled else ""
                comment = (
                    f"[{datetime.now():%Y-%m-%d}] Cleanup "
                    f"chiros≥{thresholds['chiros']} ortho≥{thresholds['orthos']} "
                    f"mam≥{thresholds['micromam']} oisx≥{thresholds['oiseaux']}"
                    f"{disabled_txt} silent={silent_policy} "
                    f"→ {files.get('planned_kept', 0)} gardés, "
                    f"{files.get('planned_deleted', 0)} supprimés "
                    f"({mb:.0f} MB libérés)"
                )
                w.set_state(key, etat="nettoyé", commentaire=comment,
                            create_if_missing=True)
                res["suivi_updated"] = True
                # Journal campagne
                log_to_campaign(session, phase="cleanup", action="cleanup",
                                stats={
                                    "thresholds": thresholds,
                                    "disabled": sorted(disabled),
                                    "kept": files.get("planned_kept", 0),
                                    "deleted": files.get("planned_deleted", 0),
                                    "bytes_freed": files.get("bytes_to_delete", 0),
                                },
                                notes=comment,
                                tool_version=TOOL_VERSION)
        except SuiviFileLockedError as e:
            res.setdefault("warnings", []).append(f"Suivi verrouillé : {e}")
        except Exception as e:
            res.setdefault("warnings", []).append(f"Suivi non mis à jour : {e}")

    return {"phase": "cleanup", **res}


# ---------------------------------------------------------------------------
# Orchestrateur
# ---------------------------------------------------------------------------

def advance(
    session: Path,
    meta: SessionMeta | None,
    *,
    thresholds: dict[str, float],
    disabled: set[str],
    silent_policy: str,
    unknown_action: str,
    use_api: bool,
    token: str | None,
    dry_run: bool,
    force: bool,
    stop_after: str | None = None,
    poll_interval: int = 60,
    verbose: bool = False,
) -> PipelineResult:
    """Avance le pipeline au maximum possible. S'arrête proprement aux
    points humains manquants."""
    result = PipelineResult()
    final_session = session

    # Phase 1 — prep
    if meta is None:
        result.stopped_at = "prep"
        result.waiting_for = "metadata"
        result.errors.append("impossible de résoudre les metadata (ni CLI, ni manifest, ni Suivi)")
        return result

    print(f"\n━━━ Phase 1/5 : PREP (rename + TE×10) ━━━")
    r = run_phase_prep(session, meta, dry_run=dry_run, force=force)
    _print_steps(r, verbose=verbose)
    if r.get("error"):
        result.stopped_at = "prep"
        result.errors.append(r["error"])
        return result
    result.phases_done.append("prep")
    if r.get("final_session_path"):
        final_session = Path(r["final_session_path"])
    result.final_session_path = final_session
    if stop_after == "prep":
        return result

    # Phase 2 — upload
    print(f"\n━━━ Phase 2/5 : UPLOAD ━━━")
    if not use_api:
        print("  use_api=False → upload skipped (à faire manuellement sur le portail)")
        result.stopped_at = "upload"
        result.waiting_for = "manual_upload"
        return result

    r = run_phase_upload(final_session, meta, dry_run=dry_run, token=token)
    _print_steps(r, verbose=verbose)
    if r.get("error"):
        result.stopped_at = "upload"
        result.errors.append(r["error"])
        return result
    result.phases_done.append("upload")
    if stop_after == "upload":
        return result

    # Phase 3 — wait
    print(f"\n━━━ Phase 3/5 : WAIT Tadarida ━━━")
    if dry_run:
        print("  dry-run → skip wait")
    else:
        r = run_phase_wait(final_session, token=token, poll_interval=poll_interval)
        _print_steps(r, verbose=verbose)
        if r.get("error"):
            result.stopped_at = "wait"
            result.errors.append(r["error"])
            return result
    result.phases_done.append("wait")
    if stop_after == "wait":
        return result

    # Phase 4 — fetch
    print(f"\n━━━ Phase 4/5 : FETCH observations ━━━")
    if dry_run:
        print("  dry-run → skip fetch")
    else:
        r = run_phase_fetch(final_session, token=token, force=force)
        _print_steps(r, verbose=verbose)
        if r.get("error"):
            result.stopped_at = "fetch"
            result.errors.append(r["error"])
            return result
    result.phases_done.append("fetch")
    if stop_after == "fetch":
        return result

    # Phase 5 — cleanup
    print(f"\n━━━ Phase 5/5 : CLEANUP ━━━")
    r = run_phase_cleanup(
        final_session, thresholds, disabled, silent_policy, unknown_action,
        dry_run=dry_run, force=force, meta=meta,
    )
    _print_steps(r, verbose=verbose)
    if r.get("errors"):
        result.stopped_at = "cleanup"
        result.errors.extend(r["errors"])
        return result
    result.phases_done.append("cleanup")
    return result


# Résumé 1-liner par étape pour le mode non-verbose
def _summarize_step(step: dict) -> str:
    s = step.get("step", "")
    if s == "rename":
        n = step.get("n_planned", 0)
        ok = step.get("executed", 0)
        skipped = step.get("skipped_same_name", 0)
        if step.get("dry_run"):
            return f"rename : {n} à renommer (dry-run)"
        return f"rename : {ok} OK, {skipped} déjà OK"
    if s == "te10":
        if step.get("dry_run"):
            return f"te10   : {step.get('n_planned_segments', 0)} segments (dry-run)"
        return (f"te10   : {step.get('written', 0)} écrits, "
                f"{step.get('skipped', 0)} déjà là, {step.get('errors', 0)} erreurs")
    if s == "suivi_write":
        if step.get("dry_run"):
            return "suivi  : (dry-run)"
        act = step.get("action", "?")
        ch = step.get("changed", []) or []
        if act == "noop":
            return "suivi  : déjà à jour"
        return f"suivi  : {act} (ligne {step.get('row_index')}, {len(ch)} champs)"
    if s == "resolve_site_id":
        return f"site   : {step.get('site_id', '?')}"
    if s == "create_participation":
        return f"créé   : participation {step.get('participation_id', '?')}"
    if s == "upload_wavs":
        if step.get("dry_run"):
            return f"upload : {step.get('would_upload', 0)} WAV (dry-run)"
        return f"upload : {step.get('uploaded', 0)} OK, {len(step.get('failed', []))} KO"
    if s == "trigger_compute":
        return "compute: lancé"
    if s == "list_wavs":
        return f"list   : {step.get('n', 0)} WAV"
    return s


def _print_steps(phase_result: dict, verbose: bool = False) -> None:
    for step in phase_result.get("steps", []):
        if verbose:
            parts = [f"{k}={v}" for k, v in step.items()
                     if k != "step" and v not in (None, "", [], {})]
            print(f"  · {step.get('step')}: " + ", ".join(parts))
        else:
            print(f"  {_summarize_step(step)}")

    # Phase cleanup (pas de "steps")
    if not phase_result.get("steps") and phase_result.get("phase") == "cleanup":
        s = phase_result.get("stats", {})
        f = s.get("files", {}) if s else {}
        if phase_result.get("dry_run"):
            print(f"  cleanup: {f.get('planned_kept', 0)} gardés, "
                  f"{f.get('planned_deleted', 0)} supprimés (dry-run)")
        else:
            mb = f.get("bytes_to_delete", 0) / (1024 * 1024)
            print(f"  cleanup: {f.get('planned_kept', 0)} gardés, "
                  f"{phase_result.get('n_deleted', 0)} supprimés ({mb:.0f} MB)")

    # Phase wait / fetch
    if phase_result.get("phase") == "wait" and phase_result.get("final_state"):
        print(f"  wait   : état final {phase_result['final_state']}")
    if phase_result.get("phase") == "fetch" and phase_result.get("n_contacts") is not None:
        print(f"  fetch  : {phase_result.get('n_files', 0)} fichiers, "
              f"{phase_result.get('n_contacts', 0)} contacts")

    # Erreurs / warnings (toujours visibles)
    if phase_result.get("error"):
        print(f"  ⚠  {phase_result['error']}")
    if phase_result.get("skipped"):
        print(f"  ↷  {phase_result['skipped']}")
    for w in phase_result.get("warnings", []) or []:
        print(f"  ⚠  {w}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", type=Path)
    ap.add_argument("--advance", action="store_true", help="enchaîne les phases")
    ap.add_argument("--only", choices=PHASES, help="exécute UNE phase et s'arrête")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--use-api", action="store_true", help="active les phases cloud")
    ap.add_argument("--token", help="token API (sinon chargé depuis keyring)")
    ap.add_argument("--poll-interval", type=int, default=60)
    ap.add_argument("--verbose", "-v", action="store_true", help="log détaillé")
    ap.add_argument("--quiet", "-q", action="store_true", help="strict minimum (erreurs seules)")

    g = ap.add_argument_group("metadata explicites (sinon auto-résolution)")
    g.add_argument("--site"); g.add_argument("--point")
    g.add_argument("--pass", dest="pass_num", type=int)
    g.add_argument("--enr", type=int); g.add_argument("--serial")
    g.add_argument("--date"); g.add_argument("--contrat")

    g2 = ap.add_argument_group("cleanup")
    for grp in ("chiros", "orthos", "micromam", "oiseaux"):
        g2.add_argument(f"--threshold-{grp}", type=float, default=0.5)
        g2.add_argument(f"--disable-{grp}", action="store_true")
    g2.add_argument("--silent-policy", choices=("delete", "keep"), default="delete")
    g2.add_argument("--unknown-action", choices=("keep", "delete"), default="keep")

    args = ap.parse_args()

    if not args.session.is_dir():
        print(f"❌ session introuvable : {args.session}", file=sys.stderr)
        return 2

    # Résolution meta
    meta, msgs = resolve_meta(args.session, args)
    if args.verbose:
        for m in msgs:
            print(f"  · {m}")
    if meta and not args.quiet:
        print(f"Session : {args.session.name}")
        print(f"Meta    : site={meta.n_site_tadarida} pt={meta.n_point_fixe} "
              f"pass{meta.n_passage} enr#{meta.n_enregistreur} ({meta.n_serie}) "
              f"{meta.date_debut:%Y-%m-%d}")
    elif meta is None and not args.quiet:
        # Seul cas où on montre toujours les msgs : l'échec
        print("Résolution meta : échec")
        for m in msgs:
            print(f"  · {m}")

    # Token
    token = args.token
    if args.use_api and not token:
        from credentials import load_token
        token = load_token()
        if not token:
            print("❌ --use-api mais aucun token (utilise save-token d'abord)", file=sys.stderr)
            return 2

    thresholds = {
        "chiros": args.threshold_chiros,
        "orthos": args.threshold_orthos,
        "micromam": args.threshold_micromam,
        "oiseaux": args.threshold_oiseaux,
    }
    disabled: set[str] = {g for g in ("chiros", "orthos", "micromam", "oiseaux")
                          if getattr(args, f"disable_{g}")}

    # Phase unique
    if args.only:
        if args.only == "prep":
            r = run_phase_prep(args.session, meta, args.dry_run, args.force)
        elif args.only == "upload":
            r = run_phase_upload(args.session, meta, args.dry_run, token)
        elif args.only == "wait":
            r = run_phase_wait(args.session, token, args.poll_interval)
        elif args.only == "fetch":
            r = run_phase_fetch(args.session, token, args.force)
        elif args.only == "cleanup":
            r = run_phase_cleanup(args.session, thresholds, disabled,
                                  args.silent_policy, args.unknown_action,
                                  args.dry_run, args.force, meta=meta)
        _print_steps(r, verbose=args.verbose)
        if r.get("error") or r.get("errors"):
            return 1
        return 0

    # Pipeline complet
    if not args.advance:
        print("ℹ  Rien à faire. Utilise --advance ou --only PHASE.", file=sys.stderr)
        return 2

    res = advance(
        args.session, meta,
        thresholds=thresholds, disabled=disabled,
        silent_policy=args.silent_policy, unknown_action=args.unknown_action,
        use_api=args.use_api, token=token,
        dry_run=args.dry_run, force=args.force,
        poll_interval=args.poll_interval,
        verbose=args.verbose,
    )
    print(f"\n━━━ Récap ━━━")
    print(f"  Phases terminées : {res.phases_done}")
    if res.stopped_at:
        print(f"  Stoppé à         : {res.stopped_at}")
    if res.waiting_for:
        print(f"  En attente de    : {res.waiting_for}")
    if res.errors:
        print(f"  Erreurs          :")
        for e in res.errors:
            print(f"    - {e}")
        return 1
    if res.final_session_path:
        print(f"  Session finale   : {res.final_session_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
