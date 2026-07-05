"""
naming.py — construction des noms canoniques (dossier session + fichier WAV).

Conventions retenues (stables pour tout l'outil) :

  * Dossier session :
        YYYYMMDD_site<SITE>_<POINT>_Pass<N>_enr<NN>
    Exemple : 20250903_site212097_Z3_Pass2_enr07

  * Préfixe WAV (format Vigie-Chiro officiel, variante "série" effectivement
    utilisée) :
        Car<SITE>-<YYYY>-Pass<N>-<POINT>-<SERIAL>
    Exemple : Car212097-2025-Pass2-Z3-SMU03126

  * Nom de fichier WAV final (préfixe + horodatage d'origine) :
        <PREFIX>_<yyyymmdd>_<hhmmss>[_<mmm>].wav
    Exemple : Car212097-2025-Pass2-Z3-SMU03126_20250903_202155.wav

Fonctions clés :
  * ``SessionMeta`` : dataclass qui porte les 7 champs nécessaires au nommage
  * ``canonical_session_dirname(meta)`` : nom du dossier session
  * ``vigiechiro_wav_prefix(meta)`` : préfixe WAV
  * ``build_wav_name(meta, timestamp[, ms])`` : nom WAV complet
  * ``compute_new_wav_name(meta, original_name)`` : renomme à partir du nom brut
  * ``validate_meta(meta)`` : liste les erreurs bloquantes
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from chiro_core import AUDIOMOTH_RE, RAW_RE, VIGIECHIRO_RE


# ---------------------------------------------------------------------------
# Métadonnées pour le nommage
# ---------------------------------------------------------------------------

@dataclass
class SessionMeta:
    """
    Métadonnées minimales nécessaires au nommage d'une session.

    Tous les champs sont validés dans ``validate_meta``.
    """
    date_debut: datetime | None = None     # jour de pose (début d'enregistrement)
    n_site_tadarida: str | None = None     # 6 chiffres "212097"
    n_point_fixe: str | None = None        # "Z3", "A1", "C2", ...
    n_passage: int | None = None           # 1, 2, 3
    n_enregistreur: int | None = None      # 1-28 (numéro court)
    n_serie: str | None = None             # "SMU03126", "S4U04784", ...
    nom_contrat: str | None = None         # informatif, non utilisé dans le nom


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_SITE_RE = re.compile(r"^\d{6}$")
_POINT_RE = re.compile(r"^[A-Za-z]\d+$")
_SERIAL_RE = re.compile(r"^[A-Za-z0-9]+$")


def validate_meta(meta: SessionMeta) -> list[str]:
    """Retourne la liste des erreurs (vide si tout est OK)."""
    errs: list[str] = []

    if meta.date_debut is None:
        errs.append("date_debut manquante")
    elif not isinstance(meta.date_debut, datetime):
        errs.append(f"date_debut doit être datetime, reçu {type(meta.date_debut).__name__}")

    if not meta.n_site_tadarida:
        errs.append("n_site_tadarida manquant")
    elif not _SITE_RE.match(str(meta.n_site_tadarida)):
        errs.append(f"n_site_tadarida doit être 6 chiffres, reçu {meta.n_site_tadarida!r}")

    if not meta.n_point_fixe:
        errs.append("n_point_fixe manquant")
    elif not _POINT_RE.match(str(meta.n_point_fixe)):
        errs.append(f"n_point_fixe doit être lettre+chiffre(s) (Z3, A1, ...), reçu {meta.n_point_fixe!r}")

    if meta.n_passage is None:
        errs.append("n_passage manquant")
    elif not (1 <= int(meta.n_passage) <= 9):
        errs.append(f"n_passage doit être entre 1 et 9, reçu {meta.n_passage!r}")

    if meta.n_enregistreur is None:
        errs.append("n_enregistreur manquant")
    elif not (1 <= int(meta.n_enregistreur) <= 99):
        errs.append(f"n_enregistreur doit être entre 1 et 99, reçu {meta.n_enregistreur!r}")

    if not meta.n_serie:
        errs.append("n_serie manquant")
    elif not _SERIAL_RE.match(str(meta.n_serie)):
        errs.append(f"n_serie contient des caractères invalides : {meta.n_serie!r}")

    return errs


# ---------------------------------------------------------------------------
# Construction des noms
# ---------------------------------------------------------------------------

def canonical_session_dirname(meta: SessionMeta) -> str:
    """
    Retourne le nom de dossier canonique.
    Exemple : 20250903_site212097_Z3_Pass2_enr07
    """
    errs = validate_meta(meta)
    if errs:
        raise ValueError(f"metadonnées invalides : {'; '.join(errs)}")
    # Post-validation : garde explicite (pas d'assert qui saute avec python -O / PyInstaller)
    if not (meta.date_debut and meta.n_site_tadarida and meta.n_point_fixe):
        raise RuntimeError("canonical_session_dirname: champs requis manquants après validation")
    if meta.n_passage is None or meta.n_enregistreur is None:
        raise RuntimeError("canonical_session_dirname: n_passage ou n_enregistreur manquant")
    return (
        f"{meta.date_debut:%Y%m%d}"
        f"_site{meta.n_site_tadarida}"
        f"_{meta.n_point_fixe.upper()}"
        f"_Pass{meta.n_passage}"
        f"_enr{meta.n_enregistreur:02d}"
    )


def vigiechiro_wav_prefix(meta: SessionMeta) -> str:
    """
    Retourne le préfixe WAV Vigie-Chiro (sans le `_yyyymmdd_hhmmss`).
    Exemple : Car212097-2025-Pass2-Z3-SMU03126
    """
    errs = validate_meta(meta)
    if errs:
        raise ValueError(f"metadonnées invalides : {'; '.join(errs)}")
    if not (meta.date_debut and meta.n_site_tadarida and meta.n_point_fixe):
        raise RuntimeError("vigiechiro_wav_prefix: champs requis manquants après validation")
    if meta.n_passage is None or meta.n_serie is None:
        raise RuntimeError("vigiechiro_wav_prefix: n_passage ou n_serie manquant")
    return (
        f"Car{meta.n_site_tadarida}"
        f"-{meta.date_debut:%Y}"
        f"-Pass{meta.n_passage}"
        f"-{meta.n_point_fixe.upper()}"
        f"-{meta.n_serie}"
    )


def build_wav_name(meta: SessionMeta, timestamp: datetime, ms: int | None = None,
                   segment_suffix: int | None = None) -> str:
    """
    Construit un nom de fichier WAV complet.
    """
    prefix = vigiechiro_wav_prefix(meta)
    dt_s = f"{timestamp:%Y%m%d}_{timestamp:%H%M%S}"
    if ms is not None:
        dt_s += f"_{ms:03d}"
    name = f"{prefix}_{dt_s}"
    if segment_suffix is not None:
        name += f"_{segment_suffix:03d}"
    return name + ".wav"


# ---------------------------------------------------------------------------
# Renommage d'un nom existant
# ---------------------------------------------------------------------------

def extract_timestamp_from_name(name: str) -> tuple[datetime, int | None] | None:
    """
    Extrait (datetime, ms) depuis n'importe quel nom reconnu (brut ou Vigie-Chiro).
    None si aucun format reconnu.
    """
    # Ordre : Vigie-Chiro, puis Wildlife (série en tête), puis AudioMoth (date en
    # tête, sans série) en dernier — AudioMoth ne matche que les noms date-first
    # que RAW_RE ne couvre pas, donc aucun risque de collision.
    for rx in (VIGIECHIRO_RE, RAW_RE, AUDIOMOTH_RE):
        m = rx.match(name)
        if m:
            date = m.group("date")
            time = m.group("time")
            try:
                dt = datetime.strptime(date + time, "%Y%m%d%H%M%S")
            except ValueError:
                continue
            # On ne renvoie jamais de ms : le suffixe _NNN peut être soit des
            # millisecondes soit un n° de segment Kaleidoscope (000), impossible
            # à distinguer côté regex. Les noms Vigie-Chiro officiels n'en ont
            # quasiment jamais et Kaleidoscope met systématiquement 000.
            return dt, None
    return None


def extract_serial_from_name(name: str) -> str | None:
    """
    Essaie d'extraire le numéro de série depuis un nom de fichier.
    - Cas brut `SMU03252_YYYYMMDD_...` → 'SMU03252'
    - Cas Vigie-Chiro `Car...-Point-SMU03252_YYYYMMDD_...` → 'SMU03252'

    Retourne TOUJOURS en uppercase : les enregistreurs Wildlife produisent
    parfois la série en minuscules (smu03252) selon le firmware, ce qui
    fait planter la vérification de cohérence. La convention en aval est
    uppercase, on normalise dès l'extraction.
    """
    m = VIGIECHIRO_RE.match(name)
    if m and m.group("extra"):
        extra = m.group("extra")
        return extra.rsplit("-", 1)[-1].upper()
    m = RAW_RE.match(name)
    if m:
        return m.group("serial").upper()
    return None


def compute_new_wav_name(meta: SessionMeta, original_name: str,
                         keep_segment_suffix: bool = True) -> str | None:
    """
    À partir d'un nom existant (brut ou Vigie-Chiro), retourne le nouveau nom
    Vigie-Chiro canonique. Retourne None si le nom n'est pas interprétable.

    Si keep_segment_suffix=True et que le nom d'origine a un suffixe _NNN, on le
    préserve.
    """
    tsinfo = extract_timestamp_from_name(original_name)
    if tsinfo is None:
        return None
    dt, _ms = tsinfo
    # Segment suffix (Kaleidoscope) : on le préserve pour ne pas écraser de fichiers
    seg = None
    if keep_segment_suffix:
        m = (VIGIECHIRO_RE.match(original_name) or RAW_RE.match(original_name)
             or AUDIOMOTH_RE.match(original_name))
        if m:
            suf = m.groupdict().get("suffix")
            if suf is not None:
                try:
                    seg = int(suf)
                except ValueError:
                    seg = None
    return build_wav_name(meta, dt, ms=None, segment_suffix=seg)


# ---------------------------------------------------------------------------
# Vérifications auto (cohérence série observée vs série dans meta)
# ---------------------------------------------------------------------------

def check_serial_consistency(meta: SessionMeta, wav_names: Iterable[str]) -> dict:
    """
    Parcourt une liste de noms WAV, extrait la série et vérifie la cohérence
    avec meta.n_serie.
    """
    serials_found: dict[str, int] = {}
    unreadable = 0
    for name in wav_names:
        s = extract_serial_from_name(name)
        if s:
            serials_found[s] = serials_found.get(s, 0) + 1
        else:
            unreadable += 1
    top = sorted(serials_found.items(), key=lambda kv: -kv[1])
    dominant = top[0][0] if top else None
    # Comparaison insensible à la casse (extract_serial_from_name normalise
    # déjà en uppercase, meta.n_serie peut venir d'une saisie en casse libre).
    consistent = None
    if dominant and meta.n_serie:
        consistent = (dominant.upper() == meta.n_serie.upper())
    return {
        "expected": meta.n_serie,
        "dominant_in_files": dominant,
        "distribution": top,
        "unreadable": unreadable,
        "consistent": consistent,
    }
