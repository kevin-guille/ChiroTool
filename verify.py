"""
verify.py — vérifications indépendantes des phases du pipeline.

Pattern "Verification Indépendante" : l'implémenteur ne peut pas vérifier
son propre travail, on relit le résultat de zéro avec des checks adversariaux.

Chaque fonction ``verify_<phase>(session)`` :
  - relit l'état sur disque (sans se fier au manifest)
  - applique des invariants forts (regex, sample rate, comptage fichiers…)
  - retourne un ``VerifyResult`` avec verdict ``PASS``, ``FAIL``, ``PARTIAL``

À appeler après chaque phase, avant ``record_action(status="ok")``.
Si la vérif échoue → ``record_action(status="verify_failed", notes=...)``
+ flag non coché → l'utilisateur peut relancer avec ``--force``.

Règle anti-triche : ne jamais consulter le manifest ou les stats du runner
pour décider du verdict. Uniquement l'état réel des fichiers.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from chiro_core import (
    RAW_RE, VIGIECHIRO_RE, _dir_has_wavs, _find_raw_wav_subdir,
    classify_wav_name,
)


Verdict = Literal["PASS", "FAIL", "PARTIAL"]


@dataclass
class VerifyResult:
    verdict: Verdict
    phase: str
    checks: list[str] = field(default_factory=list)   # ["✓ ...", "✗ ..."]
    stats: dict = field(default_factory=dict)
    notes: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == "PASS"

    def add(self, ok: bool, msg: str) -> None:
        self.checks.append(("✓ " if ok else "✗ ") + msg)

    def short(self) -> str:
        """Message d'1 ligne pour le manifest notes."""
        errs = [c for c in self.checks if c.startswith("✗")]
        if not errs:
            return f"PASS ({len(self.checks)} checks)"
        return f"{self.verdict}: " + " · ".join(c[2:] for c in errs[:3])


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------

def verify_rename(session: Path, expected_serial: str | None = None) -> VerifyResult:
    """
    Invariants après ``rename`` :
      1. Le dossier session a un nom canonique (ou non-renommé si --no-folder)
      2. Tous les WAV matchent ``VIGIECHIRO_RE`` (aucun nom brut restant)
      3. La série dominante dans les noms = série attendue (si fournie)
      4. Pas de collision de noms dans le dossier
    """
    r = VerifyResult(verdict="PASS", phase="rename")

    # Localiser les WAV (racine ou Data/)
    wav_dir = session if _dir_has_wavs(session) else _find_raw_wav_subdir(session)
    if wav_dir is None:
        r.add(False, "aucun WAV trouvé dans la session")
        r.verdict = "FAIL"
        return r

    wavs = sorted(p for p in wav_dir.iterdir()
                  if p.is_file() and p.suffix.lower() == ".wav")
    r.stats["n_wav"] = len(wavs)
    if not wavs:
        r.add(False, "liste WAV vide")
        r.verdict = "FAIL"
        return r

    # Check 1 : tous les WAV matchent Vigie-Chiro
    n_raw = n_unknown = n_ok = 0
    examples_raw: list[str] = []
    for p in wavs:
        cls = classify_wav_name(p.name)
        if cls == "vigiechiro":
            n_ok += 1
        elif cls == "raw":
            n_raw += 1
            if len(examples_raw) < 3:
                examples_raw.append(p.name)
        else:
            n_unknown += 1
    r.stats.update(ok=n_ok, raw=n_raw, unknown=n_unknown)

    if n_raw > 0:
        r.add(False, f"{n_raw} WAV encore au format brut (ex: {examples_raw[0]})")
        r.verdict = "FAIL"
    else:
        r.add(True, f"{n_ok}/{len(wavs)} WAV au format Vigie-Chiro")

    if n_unknown > 0:
        r.add(False, f"{n_unknown} WAV nom non reconnu")
        if r.verdict == "PASS":
            r.verdict = "PARTIAL"

    # Check 2 : série dominante cohérente.
    # Comparaison INSENSIBLE À LA CASSE (les enregistreurs WA produisent
    # parfois 'smu' en lowercase au lieu de 'SMU' selon le firmware).
    if expected_serial:
        from naming import extract_serial_from_name
        counts: dict[str, int] = {}
        for p in wavs:
            s = extract_serial_from_name(p.name)
            if s:
                k = s.upper()
                counts[k] = counts.get(k, 0) + 1
        if counts:
            dominant = max(counts, key=counts.get)
            if dominant != expected_serial.upper():
                r.add(False, f"série dominante {dominant!r} ≠ attendue {expected_serial!r}")
                r.verdict = "FAIL"
            else:
                r.add(True, f"série dominante cohérente : {dominant}")

    # Check 3 : pas de collision de noms
    names = [p.name for p in wavs]
    if len(set(names)) != len(names):
        dupes = len(names) - len(set(names))
        r.add(False, f"{dupes} noms en double dans le dossier")
        r.verdict = "FAIL"
    else:
        r.add(True, "aucune collision de nom")

    return r


# ---------------------------------------------------------------------------
# TE×10
# ---------------------------------------------------------------------------

def verify_te10(session: Path, expected_factor: int = 10,
                sample_size: int = 5) -> VerifyResult:
    """
    Invariants après ``te10`` :
      1. Un dossier Data_k/ existe avec des WAV
      2. Les WAV ont un nom Vigie-Chiro avec suffixe ``_NNN``
      3. Sur un échantillon, le sample rate est ≤ 60 kHz (= TE appliqué)
      4. Le nombre de segments ≥ nombre de WAV sources
    """
    r = VerifyResult(verdict="PASS", phase="te10")

    # 2 topologies supportées :
    #   A) <session>/Data_k/               (créé par te10.py nominal)
    #   B) <campagne>/Data_k/<session>/    (layout historique)
    candidates = [
        session / "Data_k",
        session.parent / "Data_k" / session.name,
        session / "1-K",
    ]
    data_k = next((p for p in candidates if p.is_dir() and _dir_has_wavs(p)), None)
    if data_k is None:
        # Cas particulier : pas de miroir, mais les WAV de la session sont
        # peut-être déjà en TE (SR ≤ 60 kHz). Considéré comme PARTIAL.
        wav_dir = session if _dir_has_wavs(session) else _find_raw_wav_subdir(session)
        if wav_dir is not None:
            sample_sr = []
            for p in list(wav_dir.glob("*.wav"))[:sample_size]:
                try:
                    with wave.open(str(p), "rb") as w:
                        sample_sr.append(w.getframerate())
                except (wave.Error, OSError):
                    continue
            if sample_sr and max(sample_sr) <= 60_000:
                r.add(True, f"pas de Data_k/ mais WAV déjà en TE (SR={sample_sr})")
                r.add(False, "miroir Data_k/ absent (TE appliqué in-place ?)")
                r.verdict = "PARTIAL"
                r.stats["sr_sample"] = sample_sr
                r.stats["n_segments"] = sum(1 for _ in wav_dir.glob("*.wav"))
                return r
        r.add(False, f"aucun Data_k/ trouvé et WAV pas en TE")
        r.verdict = "FAIL"
        return r
    r.add(True, f"Data_k/ trouvé : {data_k.relative_to(session.parent)}")

    segments = sorted(p for p in data_k.iterdir()
                      if p.is_file() and p.suffix.lower() == ".wav")
    r.stats["n_segments"] = len(segments)
    if not segments:
        r.add(False, "Data_k/ vide")
        r.verdict = "FAIL"
        return r
    r.add(True, f"{len(segments)} segments dans Data_k/")

    # Check 2 : format Vigie-Chiro + suffixe _NNN
    n_with_suffix = 0
    n_invalid = 0
    for p in segments[:200]:   # échantillonne pour rester rapide
        m = VIGIECHIRO_RE.match(p.name)
        if m:
            if m.group("suffix"):
                n_with_suffix += 1
        else:
            n_invalid += 1

    if n_invalid:
        r.add(False, f"{n_invalid} segment(s) au nom non canonique")
        r.verdict = "FAIL"
    else:
        r.add(True, "tous les noms matchent Vigie-Chiro")
    r.stats["with_000_suffix"] = n_with_suffix

    # Check 3 : sample rate divisé (échantillonnage)
    sr_values: list[int] = []
    for p in segments[:sample_size]:
        try:
            with wave.open(str(p), "rb") as w:
                sr_values.append(w.getframerate())
        except (wave.Error, OSError):
            continue
    r.stats["sr_sample"] = sr_values
    if sr_values:
        max_sr = max(sr_values)
        # SR > 60 kHz → la TE n'a probablement pas été appliquée
        if max_sr > 60_000:
            r.add(False, f"sample rate {max_sr} Hz > 60 kHz (TE non appliquée ?)")
            r.verdict = "FAIL"
        else:
            r.add(True, f"SR échantillonnés ≤ 60 kHz ({sr_values})")

    # Check 4 : couverture PAR SOURCE. Un simple total global masquerait
    # l'absence complète des segments d'un WAV court (le surplus de segments des
    # WAV longs compenserait le compte). On vérifie donc que CHAQUE WAV brut a au
    # moins son 1er segment dérivé, nommé "<stem_source>_000.wav" (le segment
    # d'offset 0 conserve le timestamp de la source ; cf te10.plan_file).
    wav_dir = session if _dir_has_wavs(session) else _find_raw_wav_subdir(session)
    if wav_dir and wav_dir != data_k:
        raws = [p for p in wav_dir.iterdir()
                if p.is_file() and p.suffix.lower() == ".wav"]
        n_raws = len(raws)
        r.stats["n_raws"] = n_raws
        seg_names = {p.name for p in segments}
        missing = [p.name for p in raws
                   if f"{p.stem}_000.wav" not in seg_names]
        r.stats["sources_sans_segment"] = len(missing)
        if missing:
            sample = ", ".join(missing[:3]) + ("…" if len(missing) > 3 else "")
            r.add(False,
                  f"{len(missing)}/{n_raws} source(s) sans segment TE×10 : {sample}")
            r.verdict = "FAIL"
        elif n_raws:
            r.add(True,
                  f"couverture par source OK ({n_raws} raws → chacun a ≥1 segment)")

    return r


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def verify_cleanup(session: Path) -> VerifyResult:
    """
    Invariants après ``cleanup`` :
      1. Un ``*_cleanup.xlsx`` a été produit
      2. Un ``_stats_before_cleanup.json`` est présent
      3. Cohérence xlsx ↔ WAV physiques :
         - tous les contacts ``deleted_*`` n'ont PAS leur WAV sur disque
           (ou si présents, aucun autre contact ne le "sauvait")
         - tous les ``kept`` ont leur WAV sur disque
      4. L'original xlsx est intact (non écrasé)
    """
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
    import openpyxl

    r = VerifyResult(verdict="PASS", phase="cleanup")

    # Check 1 + 4 : fichiers attendus
    cleanup_xlsx = None
    original_xlsx = None
    stats_json = session / "_stats_before_cleanup.json"

    for p in session.iterdir():
        if not p.is_file():
            continue
        n = p.name.lower()
        if n.endswith(".xlsx") and "participation-" in n and "observations" in n:
            if "_cleanup" in n:
                cleanup_xlsx = p
            elif "_cleanup" not in n:
                original_xlsx = p

    if cleanup_xlsx is None:
        r.add(False, "fichier _cleanup.xlsx absent")
        r.verdict = "FAIL"
        return r
    r.add(True, f"fichier annoté : {cleanup_xlsx.name}")

    if not stats_json.is_file():
        r.add(False, "_stats_before_cleanup.json absent")
        r.verdict = "PARTIAL"
    else:
        r.add(True, "stats pré-cleanup persistées")

    if original_xlsx is None:
        r.add(False, "xlsx original non retrouvé (non-bloquant)")
    else:
        r.add(True, f"xlsx original préservé : {original_xlsx.name}")

    # Check 3 : cohérence xlsx ↔ disque
    try:
        wb = openpyxl.load_workbook(cleanup_xlsx, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception as e:
        r.add(False, f"lecture xlsx impossible : {e}")
        r.verdict = "FAIL"
        return r

    if not rows:
        r.add(False, "xlsx cleanup vide")
        r.verdict = "FAIL"
        return r

    headers = [str(h).strip().lower() if h else "" for h in rows[0]]
    try:
        i_name = headers.index("nom du fichier")
        i_decision = headers.index("cleanup_decision")
    except ValueError:
        r.add(False, "colonnes cleanup_decision/nom du fichier manquantes")
        r.verdict = "FAIL"
        return r

    # Regrouper décisions par fichier (règle OR)
    by_file: dict[str, list[str]] = {}
    for row in rows[1:]:
        if not row or row[i_name] is None:
            continue
        stem = Path(str(row[i_name])).stem
        decision = str(row[i_decision] or "").strip()
        by_file.setdefault(stem, []).append(decision)

    # Fichier conservé = au moins 1 kept
    # Fichier supprimé = 0 kept (tous deleted_*)
    kept_expected: set[str] = set()
    deleted_expected: set[str] = set()
    for stem, decisions in by_file.items():
        if any(d == "kept" for d in decisions):
            kept_expected.add(stem)
        elif decisions and all(d.startswith("deleted_") for d in decisions):
            deleted_expected.add(stem)

    # Confronter au disque
    data_k = session / "Data_k"
    physical: set[str] = set()
    if data_k.is_dir():
        physical = {p.stem for p in data_k.iterdir()
                    if p.is_file() and p.suffix.lower() == ".wav"}

    kept_missing_on_disk = kept_expected - physical
    deleted_still_on_disk = deleted_expected & physical

    r.stats.update(
        kept_expected=len(kept_expected),
        deleted_expected=len(deleted_expected),
        physical_now=len(physical),
        kept_missing_on_disk=len(kept_missing_on_disk),
        deleted_still_on_disk=len(deleted_still_on_disk),
    )

    if kept_missing_on_disk:
        r.add(False, f"{len(kept_missing_on_disk)} WAV 'kept' absents du disque")
        r.verdict = "FAIL"
    else:
        r.add(True, f"{len(kept_expected)} WAV 'kept' tous présents")

    if deleted_still_on_disk:
        r.add(False, f"{len(deleted_still_on_disk)} WAV 'deleted' encore sur disque")
        if r.verdict == "PASS":
            r.verdict = "PARTIAL"
    else:
        r.add(True, f"{len(deleted_expected)} WAV 'deleted' bien purgés")

    return r


# ---------------------------------------------------------------------------
# CLI diagnostic
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

    ap = argparse.ArgumentParser(description="Vérifie indépendamment l'état d'une session.")
    ap.add_argument("session", type=Path)
    ap.add_argument("--phase", choices=("rename", "te10", "cleanup", "all"),
                    default="all")
    ap.add_argument("--serial", help="série attendue (rename)")
    args = ap.parse_args()

    if not args.session.is_dir():
        print(f"❌ session introuvable : {args.session}")
        return 2

    results: list[VerifyResult] = []
    if args.phase in ("rename", "all"):
        results.append(verify_rename(args.session, expected_serial=args.serial))
    if args.phase in ("te10", "all"):
        results.append(verify_te10(args.session))
    if args.phase in ("cleanup", "all"):
        results.append(verify_cleanup(args.session))

    any_fail = False
    for r in results:
        print(f"\n=== {r.phase.upper()} : {r.verdict} ===")
        for c in r.checks:
            print(f"  {c}")
        if r.stats:
            print(f"  stats : {r.stats}")
        if not r.ok:
            any_fail = True

    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(_cli())
