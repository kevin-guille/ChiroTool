"""
chiro_core.py
-------------
Fonctions partagées pour le traitement des enregistrements chiroptères.

Rien de spécifique à la GUI ici, juste de la logique pure testable.
Zéro dépendance hors stdlib (on utilisera openpyxl ailleurs uniquement pour le Suivi).
"""

from __future__ import annotations

import csv
import re
import wave
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Regex de nommage
# ---------------------------------------------------------------------------

# Nom canonique Vigie-Chiro. Format officiel (FAQ §5) :
#   CarXXXXXX-AAAA-PassN-YY-0_yyyymmdd_hhmmss_mmm.wav
# En pratique les fichiers observés acceptent un bloc "extra" (n° série, micro, boîtier)
# avant le séparateur _yyyymmdd :
#   Car300371-2025-Pass1-Z6-SMU03252_20250919_191542.wav
#   Car340728-2014-Pass1-A1-VC4-1715-0_20200322_230545_354.wav
# Après passage Kaleidoscope/TE10, un suffixe _NNN (numéro de segment) peut être ajouté
# avant l'extension.
VIGIECHIRO_RE = re.compile(
    r"""^
    Car(?P<site>\d{6})              # 6 chiffres du carré (département = 2 premiers)
    -(?P<year>\d{4})                # année
    -Pass(?P<pass_num>\d+)          # numéro de passage
    -(?P<point>[A-Za-z]\d+)         # code du point (A1, C2, Z4, ...)
    (?:-(?P<extra>.+?))?            # bloc optionnel (série, micro, n° boîtier) - non greedy
    _(?P<date>\d{8})                # yyyymmdd
    _(?P<time>\d{6})                # hhmmss
    (?:_(?P<suffix>\d{3}))?         # suffixe segment optionnel (_000, _001, ...)
    \.(?P<ext>wav|w4v)$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Nom "brut" Wildlife Acoustics (SM4/SMU/Song Meter) : SMU03126_20250903_194608.wav
RAW_RE = re.compile(
    r"""^
    (?P<serial>[A-Za-z0-9]+)
    _(?P<date>\d{8})
    _(?P<time>\d{6})
    (?:_(?P<suffix>\d{3}))?
    \.(?P<ext>wav|w4v)$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Nom AudioMoth EXPANDÉ (après « Expand » via AudioMoth Config App ou
# CEREMA/TWAV_splitter) : date en tête, PAS de série, millisecondes en suffixe.
# Ex. : 20220721_033014_451.WAV, 20260615_212501.WAV
# La série n'y figure pas → fournie par l'utilisateur (wizard / parc matériel).
AUDIOMOTH_RE = re.compile(
    r"""^
    (?P<date>\d{8})
    _(?P<time>\d{6})
    (?:_(?P<suffix>\d{3}))?         # millisecondes (fichier expandé), optionnel
    \.(?P<ext>wav|w4v)$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Nom AudioMoth BRUT "T.WAV" (déclenché, événements CONCATÉNÉS) : à REFUSER tant
# qu'il n'a pas été « expandé » (dé-concaténé + horodaté). Le traiter tel quel
# donnerait des horodatages faux. Ex. : 20260615_212501T.WAV
AUDIOMOTH_TWAV_RE = re.compile(
    r"^(?P<date>\d{8})_(?P<time>\d{6})T\.(?:wav)$",
    re.IGNORECASE,
)

# Titley Anabat Swift / Ranger (Insight), noms usine — issue #4 Mickaël 2026-08-27.
#   2026-08-21 20-45-29.wav
#   2026-08-21_20-45-29.wav
#   669178 2026-08-21 20-45-29.wav
#   669178_2026-08-21_20-45-29.wav
# Ce n'est pas un « format » WAV différent (PCM standard) : seul le NOM diffère
# de Wildlife / AudioMoth / Vigie-Chiro. Le n° d'enregistreur en préfixe n'est
# PAS une série Wildlife ; la série vient du wizard / parc matériel.
TITLEY_RE = re.compile(
    r"""^
    (?:(?P<device>[A-Za-z0-9]+)[ _])?
    (?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})
    [ _]
    (?P<h>\d{2})[-:](?P<mi>\d{2})[-:](?P<s>\d{2})
    (?:_(?P<suffix>\d{3}))?
    \.(?P<ext>wav|w4v)$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_audiomoth_twav(name: str) -> bool:
    """True si le nom est un AudioMoth BRUT « T.WAV » (déclenché/concaténé), qui
    doit être « expandé » avant tout traitement."""
    return bool(AUDIOMOTH_TWAV_RE.match(name))


def classify_wav_name(name: str) -> str:
    """Retourne 'vigiechiro', 'raw', 'audiomoth_twav' ou 'unknown'.

    'raw' couvre Wildlife (SERIAL_date_time), AudioMoth EXPANDÉ (date_time_ms)
    et Titley Swift/Ranger (YYYY-MM-DD HH-MM-SS).
    'audiomoth_twav' = AudioMoth brut concaténé (à expandre d'abord).
    """
    if VIGIECHIRO_RE.match(name):
        return "vigiechiro"
    if RAW_RE.match(name) or AUDIOMOTH_RE.match(name) or TITLEY_RE.match(name):
        return "raw"
    if AUDIOMOTH_TWAV_RE.match(name):
        return "audiomoth_twav"
    return "unknown"


def parse_vigiechiro_name(name: str) -> dict | None:
    m = VIGIECHIRO_RE.match(name)
    return m.groupdict() if m else None


def parse_raw_name(name: str) -> dict | None:
    m = RAW_RE.match(name)
    return m.groupdict() if m else None


# ---------------------------------------------------------------------------
# Lecture WAV (header seulement, pas de décodage PCM)
# ---------------------------------------------------------------------------

@dataclass
class WavInfo:
    path: Path
    sample_rate: int
    n_frames: int
    n_channels: int
    sample_width: int  # bytes per sample
    duration_s: float

    @property
    def size_bytes(self) -> int:
        return self.path.stat().st_size


def read_wav_info(path: Path) -> WavInfo | None:
    """Lit l'en-tête WAV. None si fichier illisible."""
    try:
        with wave.open(str(path), "rb") as w:
            fr = w.getframerate()
            nf = w.getnframes()
            return WavInfo(
                path=path,
                sample_rate=fr,
                n_frames=nf,
                n_channels=w.getnchannels(),
                sample_width=w.getsampwidth(),
                duration_s=nf / fr if fr else 0.0,
            )
    except (wave.Error, OSError, EOFError):
        return None


def is_time_expanded(info: WavInfo) -> bool:
    """
    Heuristique : après TE×10 le sample rate est divisé par 10.
    - Brut ultrasons : 192 kHz, 256 kHz, 384 kHz, 500 kHz...
    - Après TE×10     : 19.2 kHz, 25.6 kHz, 38.4 kHz, 50 kHz...
    On considère TE si sample rate <= 60 kHz.
    """
    return 0 < info.sample_rate <= 60_000


# ---------------------------------------------------------------------------
# Summary.txt (Wildlife Acoustics SM4BAT etc.)
# ---------------------------------------------------------------------------

@dataclass
class SummaryInfo:
    path: Path
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    n_lines: int = 0
    # (datetime, T°) de chaque ligne — pour extraire UNE nuit d'un Summary
    # cumulatif (carte SD non formatée). Non sérialisé dans SessionState.
    samples: list[tuple[datetime, float | None]] = field(default_factory=list)
    temp_start: float | None = None
    temp_end: float | None = None
    temp_min: float | None = None
    temp_max: float | None = None
    lat: float | None = None
    lon: float | None = None
    battery_start: float | None = None
    battery_end: float | None = None
    n_fs_files_total: int = 0

    @property
    def temp_range_str(self) -> str:
        if self.temp_start is not None and self.temp_end is not None:
            return f"{self.temp_start:.0f}-{self.temp_end:.0f}"
        return ""


@dataclass
class TitleyLogInfo:
    path: Path
    device_model: str | None = None
    device_id: str | None = None
    rec_start: datetime | None = None
    rec_stop: datetime | None = None
    night_start_hm: str | None = None
    night_end_hm: str | None = None
    temp_start: float | None = None
    temp_end: float | None = None
    n_files: int = 0
    samples: list[tuple[datetime, float | None]] = field(default_factory=list)

    @property
    def start_dt(self) -> datetime | None:
        return self.rec_start

    @property
    def end_dt(self) -> datetime | None:
        return self.rec_stop


def parse_titley_log(path: Path) -> TitleyLogInfo | None:
    """Lit un log Titley Insight (heures locales, dernière fenêtre d'enregistrement)."""
    path = Path(path)
    try:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            rows = list(csv.reader(stream))
    except OSError:
        return None
    info = TitleyLogInfo(path)
    day = None
    # Le firmware peut émettre Recording start juste avant la première DATE.
    for row in rows:
        if len(row) >= 3 and row[1].strip() == "DATE":
            try:
                day = datetime.strptime(row[2].strip(), "%Y-%m-%d").date()
                break
            except ValueError:
                pass
    previous = None
    power_on = None
    schedule = None
    active = None
    pairs = []
    schedules = []
    temperatures = []
    files = []
    totals = []
    recognized = False
    for row in rows:
        if len(row) < 3:
            continue
        clock, event, value = (part.strip() for part in row[:3])
        if event == "DATE":
            try:
                day = datetime.strptime(value, "%Y-%m-%d").date()
                previous = None
            except ValueError:
                continue
        if event == "TIME":
            clock = value.split()[0] if value else clock
        try:
            time = datetime.strptime(clock, "%H:%M:%S").time()
        except ValueError:
            time = None
        dt = None
        if day is not None and time is not None:
            seconds = time.hour * 3600 + time.minute * 60 + time.second
            if previous is not None and previous - seconds > 12 * 3600:
                day += timedelta(days=1)
            previous = seconds
            dt = datetime.combine(day, time)
        if event == "POWER" and value == "on":
            power_on = dt
            schedule = None
        if event == "INFO":
            if value in ("Anabat Swift", "Anabat Ranger", "Anabat Scout"):
                info.device_model = value
                recognized = True
            if value.startswith("Device ID "):
                info.device_id = value[len("Device ID "):].strip()
            match = re.fullmatch(r"night mode start (\d{1,2}:\d{2}) end (\d{1,2}:\d{2})", value)
            if match and dt is not None:
                try:
                    start_time, end_time = [datetime.strptime(hm, "%H:%M").time() for hm in match.groups()]
                except ValueError:
                    continue
                start = datetime.combine(dt.date(), start_time)
                end = datetime.combine(dt.date(), end_time)
                if end <= start:
                    end += timedelta(days=1)
                    if dt.time() < end_time:
                        start -= timedelta(days=1)
                        end -= timedelta(days=1)
                candidate = (start, end, match.groups(), power_on)
                # Un night mode lu au stop décrit la nuit suivante, pas celle-ci.
                if schedule is None:
                    schedule = candidate
                    schedules.append(candidate)
                recognized = True
            if value == "Recording start" and dt is not None:
                active = (dt, schedule, power_on)
                recognized = True
            elif value == "Recording stop" and dt is not None and active:
                if dt >= active[0]:
                    pairs.append((active[0], dt, active[1], active[2]))
                active = None
        if event == "TEMP" and dt is not None:
            try:
                temperatures.append((dt, float(value)))
            except ValueError:
                pass
        if event == "FILE" and dt is not None:
            files.append(dt)
        if event == "SUMM" and dt is not None:
            match = re.fullmatch(r"Recorded (\d+) files", value)
            if match:
                totals.append((dt, int(match[1])))
    if not recognized:
        return None
    chosen_schedule = None
    if pairs:
        info.rec_start, info.rec_stop, chosen_schedule, power_on = pairs[-1]
    elif schedules:
        useful = [s for s in schedules if any(s[0] <= dt <= s[1] for dt in files)]
        chosen_schedule = max(useful, key=lambda s: s[1] - s[0]) if useful else schedules[-1]
        info.rec_start, info.rec_stop, _, power_on = chosen_schedule
    if chosen_schedule:
        info.night_start_hm, info.night_end_hm = chosen_schedule[2]
    if info.rec_start is not None and info.rec_stop is not None:
        lower = info.rec_start
        if power_on is not None and power_on.replace(second=0, microsecond=0) == lower.replace(second=0, microsecond=0):
            lower = power_on
        info.samples = [(dt, t) for dt, t in temperatures if lower <= dt <= info.rec_stop]
        if info.samples:
            info.temp_start = info.samples[0][1]
            info.temp_end = info.samples[-1][1]
        info.n_files = sum(info.rec_start <= dt <= info.rec_stop for dt in files)
        for dt, total in totals:
            if dt == info.rec_stop:
                info.n_files = total
    return info


def collect_wizard_prefill(session: Path, *,
                           n_enregistreur=None,
                           date_debut=None,
                           wav_names: list[str] | None = None) -> dict:
    """Pré-remplissage du wizard participation, sans GUI.

    Ordre : log Titley (dates + T°) → Summary → WAV seulement si encore
    besoin. Une session Titley de 4000 WAV ne doit plus lister Data_k/
    juste pour ouvrir la fenêtre (issue #9).
    """
    session = Path(session)
    pre: dict = {}

    log_path = find_titley_log(session)
    if log_path is None:
        sub = _find_raw_wav_subdir(session)
        if sub is not None:
            log_path = find_titley_log(sub)
    titley = parse_titley_log(log_path) if log_path else None
    if titley and titley.start_dt and titley.end_dt:
        pre["date_debut"] = titley.start_dt
        pre["date_fin"] = titley.end_dt
        pre["_dates_from_titley"] = True
        if titley.temp_start is not None:
            pre["temperature_debut"] = int(round(titley.temp_start))
        if titley.temp_end is not None:
            pre["temperature_fin"] = int(round(titley.temp_end))
        if titley.device_model:
            try:
                from vigiechiro_enums import DETECTEUR_ENREGISTREUR_TYPES
                allowed = titley.device_model in DETECTEUR_ENREGISTREUR_TYPES
            except Exception:
                allowed = True
            if allowed:
                pre["detecteur_enregistreur_type"] = titley.device_model

    s = None
    summ = find_summary_file(session)
    if summ is None:
        sub = _find_raw_wav_subdir(session)
        if sub is not None:
            summ = find_summary_file(sub)
    if summ is not None:
        s = parse_summary_txt(summ)
        if s:
            if "temperature_debut" not in pre and s.temp_start is not None:
                pre["temperature_debut"] = int(round(s.temp_start))
            if "temperature_fin" not in pre and s.temp_end is not None:
                pre["temperature_fin"] = int(round(s.temp_end))
            if not pre.get("_dates_from_titley"):
                if s.start_dt:
                    pre["date_debut"] = s.start_dt
                if s.end_dt:
                    pre["date_fin"] = s.end_dt

    if not pre.get("_dates_from_titley"):
        names = wav_names
        if names is None:
            # Pas de Titley : on liste. Si Titley était là, on ne passe pas ici.
            names = list_session_wav_names(session)
        from naming import wav_timestamp_range
        wav_min, wav_max = wav_timestamp_range(names)
        if should_prefer_wav_dates(s, wav_min) and wav_min:
            pre["date_debut"] = wav_min
            if wav_max:
                pre["date_fin"] = wav_max
            pre["_dates_from_wav"] = True
            t0, t1 = summary_temps_in_window(s, wav_min, wav_max)
            if t0 is not None:
                pre["temperature_debut"] = int(round(t0))
            elif not s:
                pre.pop("temperature_debut", None)
            if t1 is not None:
                pre["temperature_fin"] = int(round(t1))
            elif not s:
                pre.pop("temperature_fin", None)
        pre["_wav_listed"] = True
    else:
        pre["_wav_listed"] = False

    used_materiels = False
    try:
        from materiels import find_by_id, load_materiels
        if n_enregistreur is not None:
            m = find_by_id(load_materiels(), n_enregistreur)
            if m is not None and not m.is_empty():
                used_materiels = True
                if m.modele:
                    pre["detecteur_enregistreur_type"] = m.modele
                if m.micro_modele:
                    pre["micro0_modele"] = m.micro_modele
                if m.hauteur_m is not None:
                    pre["micro0_hauteur"] = str(m.hauteur_m)
                if m.stereo and m.micro2_modele:
                    pre["stereo"] = True
                    pre["micro1_modele"] = m.micro2_modele
    except Exception:
        pass

    if (titley and titley.device_model
            and not pre.get("detecteur_enregistreur_type")):
        pre["detecteur_enregistreur_type"] = titley.device_model

    pre["_used_materiels"] = used_materiels
    pre["_auto_temperature_debut"] = pre.get("temperature_debut")
    pre["_auto_temperature_fin"] = pre.get("temperature_fin")

    try:
        from manifest import Manifest
        mfest = Manifest.load(session)
    except Exception:
        mfest = None
    if mfest and mfest.meta:
        part_cached = mfest.meta.get("participation_payload") or {}
        wav_day = None
        if pre.get("_dates_from_wav") and pre.get("date_debut") is not None:
            try:
                wav_day = pre["date_debut"].date().isoformat()
            except Exception:
                wav_day = None
        overlay_participation_cache(pre, part_cached, wav_day=wav_day)
    return pre


def find_titley_log(folder: Path) -> Path | None:
    """Trouve un log Titley validé à la racine de session ou dans Data/."""
    folder = Path(folder)
    roots = [folder, folder / "Data"]
    if folder.name.lower().startswith("data"):
        roots.extend([folder.parent, folder.parent / "Data"])
    for root in dict.fromkeys(roots):
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if path.is_file() and path.name.lower().startswith("log") and path.suffix.lower() == ".csv":
                if parse_titley_log(path) is not None:
                    return path
    return None


def build_participation_configuration(detecteur, n_serie=None, mic0=None,
                                      mic0_h=None, mic1=None, mic1_h=None) -> dict:
    """Champs configuration API, sans importer la GUI."""
    configuration = {"detecteur_enregistreur_type": detecteur}
    if n_serie:
        configuration["detecteur_enregistreur_serie"] = n_serie
    for index, model, height in ((0, mic0, mic0_h), (1, mic1, mic1_h)):
        if model:
            configuration[f"micro{index}_modele"] = model
        if height is not None:
            configuration[f"micro{index}_hauteur"] = str(height)
    return configuration


def temperatures_are_user_set(auto_debut, auto_fin, user_debut, user_fin) -> bool:
    """True si les T° saisies s'écartent du préremplissage auto (Summary / log)."""
    return user_debut != auto_debut or user_fin != auto_fin


def _as_int_temp(value):
    if value is None or value is False:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _as_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def overlay_participation_cache(
    pre: dict,
    cached: dict | None,
    *,
    wav_day: str | None = None,
) -> dict:
    """Applique le cache wizard. Les T° forcées par l'utilisateur gagnent.

    Les horaires Titley / WAV restent prioritaires sur d'anciennes dates
    de cache (sauf T° marquées ``temperature_user_set``).
    """
    if not isinstance(cached, dict):
        return pre
    for k, v in cached.items():
        if k in ("_auto_temperature_debut", "_auto_temperature_fin"):
            continue
        if k in ("temperature_debut", "temperature_fin"):
            if cached.get("temperature_user_set"):
                if v is None:
                    pre.pop(k, None)
                else:
                    parsed = _as_int_temp(v)
                    if parsed is not None:
                        pre[k] = parsed
            continue
        if k == "temperature_user_set":
            pre[k] = bool(v)
            continue
        if v is None:
            continue
        if pre.get("_dates_from_titley") and k in ("date_debut", "date_fin"):
            continue
        if k in ("date_debut", "date_fin") and isinstance(v, str):
            parsed_dt = _as_dt(v)
            if parsed_dt is None:
                continue
            v = parsed_dt
        if k in ("date_debut", "date_fin") and wav_day:
            try:
                cached_day = v.date().isoformat() if hasattr(v, "date") else str(v)[:10]
            except Exception:
                cached_day = None
            if cached_day and cached_day != wav_day:
                continue
        pre[k] = v
    return pre


def coerce_participation_payload(raw: dict | None) -> dict:
    """Normalise wizard imbriqué ou cache manifest plat vers le contrat API.

    Sortie : ``date_debut`` / ``date_fin`` en datetime, ``meteo`` et
    ``configuration`` imbriqués (ou None).
    """
    if not isinstance(raw, dict) or not raw:
        return {}
    out = dict(raw)
    for k in ("date_debut", "date_fin"):
        out[k] = _as_dt(out.get(k))
    meteo = out.get("meteo")
    if not isinstance(meteo, dict):
        meteo = {}
        for k in ("temperature_debut", "temperature_fin"):
            t = _as_int_temp(out.get(k))
            if t is not None:
                meteo[k] = t
        for k in ("vent", "couverture"):
            if out.get(k):
                meteo[k] = out[k]
        out["meteo"] = meteo or None
    else:
        clean = dict(meteo)
        for k in ("temperature_debut", "temperature_fin"):
            if k not in clean:
                continue
            t = _as_int_temp(clean.get(k))
            if t is None:
                clean.pop(k, None)
            else:
                clean[k] = t
        out["meteo"] = clean or None
    config = out.get("configuration")
    if not isinstance(config, dict):
        det = out.get("detecteur_enregistreur_type")
        if det:
            out["configuration"] = build_participation_configuration(
                det,
                out.get("detecteur_enregistreur_serie"),
                out.get("micro0_modele") or None,
                out.get("micro0_hauteur"),
                out.get("micro1_modele") or None,
                out.get("micro1_hauteur"),
            )
        else:
            out["configuration"] = None
    elif out.get("detecteur_enregistreur_serie") and not config.get(
            "detecteur_enregistreur_serie"):
        config = dict(config)
        config["detecteur_enregistreur_serie"] = out["detecteur_enregistreur_serie"]
        out["configuration"] = config
    return out


def _field_blank(value) -> bool:
    return value is None or value == "" or value == {} or value == []


def _dt_key(value):
    dt = _as_dt(value)
    if dt is None and isinstance(value, str):
        for fmt in ("%a, %d %b %Y %H:%M:%S GMT", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute)


def _parse_participation_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    parsed = _as_dt(value.replace("Z", "+00:00") if "Z" in value else value)
    if parsed is not None:
        return parsed
    for fmt in ("%a, %d %b %Y %H:%M:%S GMT", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def server_fields_from_participation(raw: dict | None) -> dict:
    """Extrait dates / meteo / configuration d'une participation API brute."""
    raw = raw if isinstance(raw, dict) else {}
    meteo = raw.get("meteo") if isinstance(raw.get("meteo"), dict) else {}
    config = raw.get("configuration") if isinstance(raw.get("configuration"), dict) else {}
    return {
        "date_debut": _parse_participation_dt(raw.get("date_debut")),
        "date_fin": _parse_participation_dt(raw.get("date_fin")),
        "meteo": dict(meteo),
        "configuration": dict(config),
    }


def collect_local_participation_fields(session: Path) -> dict:
    """Assemble le payload local (cache wizard, log Titley, série, parc)."""
    session = Path(session)
    try:
        from manifest import Manifest
        m = Manifest.load(session)
    except Exception:
        m = None
    meta = (m.meta if m else {}) or {}
    cached = meta.get("participation_payload")
    cached = cached if isinstance(cached, dict) else {}
    user_set = bool(cached.get("temperature_user_set"))
    pp = coerce_participation_payload(cached)
    pp["_temperature_user_set"] = user_set

    cfg = dict(pp.get("configuration") or {})
    serie = cfg.get("detecteur_enregistreur_serie") or meta.get("n_serie")
    if serie:
        cfg["detecteur_enregistreur_serie"] = str(serie)
        pp["configuration"] = cfg

    log_path = find_titley_log(session)
    titley = parse_titley_log(log_path) if log_path else None
    if titley:
        if titley.rec_start:
            pp["date_debut"] = titley.rec_start
            pp["date_fin"] = titley.rec_stop
            pp["_from_titley_dates"] = True
        if not user_set:
            meteo = dict(pp.get("meteo") or {})
            if titley.temp_start is not None:
                meteo["temperature_debut"] = int(round(titley.temp_start))
            if titley.temp_end is not None:
                meteo["temperature_fin"] = int(round(titley.temp_end))
            pp["meteo"] = meteo or None
            pp["_from_titley_temps"] = True
        model = (titley.device_model or "").strip()
        if model and not cfg.get("detecteur_enregistreur_type"):
            try:
                from vigiechiro_enums import DETECTEUR_ENREGISTREUR_TYPES
                allowed = model in DETECTEUR_ENREGISTREUR_TYPES
            except Exception:
                allowed = True
            if allowed:
                cfg["detecteur_enregistreur_type"] = model
                pp["configuration"] = cfg

    n_enr = meta.get("n_enregistreur")
    if n_enr is not None:
        try:
            from materiels import find_by_id, load_materiels
            mat = find_by_id(load_materiels(), int(n_enr))
        except Exception:
            mat = None
        if mat is not None and not mat.is_empty():
            cfg = dict(pp.get("configuration") or {})
            if mat.modele and not cfg.get("detecteur_enregistreur_type"):
                cfg["detecteur_enregistreur_type"] = mat.modele
            if mat.micro_modele and not cfg.get("micro0_modele"):
                cfg["micro0_modele"] = mat.micro_modele
            if mat.hauteur_m is not None and cfg.get("micro0_hauteur") in (None, ""):
                cfg["micro0_hauteur"] = str(mat.hauteur_m)
            if mat.serie_enr and not cfg.get("detecteur_enregistreur_serie"):
                cfg["detecteur_enregistreur_serie"] = mat.serie_enr
            pp["configuration"] = cfg or None
    return pp


def diff_participation_update(
    server: dict | None,
    local: dict | None,
    *,
    only_changes: list[str] | None = None,
) -> dict:
    """Champs à PATCH : absents serveur, T° forcées, dates Titley, série.

    Ne remplace pas une T° / un type déjà saisis sur le portail, sauf T°
    marquées ``_temperature_user_set``. Les dates Titley (Recording start/stop)
    corrigent un 1er WAV si elles diffèrent. Nested meteo/configuration
    fusionnés avec le serveur (Eve remplace le sous-document entier).
    """
    server = server if isinstance(server, dict) else {}
    local = local if isinstance(local, dict) else {}
    changes: list[str] = []
    out: dict = {}
    user_set = bool(local.get("_temperature_user_set"))
    from_titley = bool(local.get("_from_titley_dates"))
    allowed = set(only_changes) if only_changes is not None else None

    ld = local.get("date_debut")
    lf = local.get("date_fin")
    sd = server.get("date_debut")
    sf = server.get("date_fin")
    if ld and (
        _field_blank(sd)
        or (from_titley and (_dt_key(ld) != _dt_key(sd) or _dt_key(lf) != _dt_key(sf)))
    ) and (allowed is None or "horaires d'enregistrement" in allowed):
        out["date_debut"] = ld
        if lf:
            out["date_fin"] = lf
        changes.append("horaires d'enregistrement")

    sm = server.get("meteo") if isinstance(server.get("meteo"), dict) else {}
    lm = local.get("meteo") if isinstance(local.get("meteo"), dict) else {}
    meteo_overlay: dict = {}
    labels = {
        "temperature_debut": "T° début",
        "temperature_fin": "T° fin",
        "vent": "vent",
        "couverture": "couverture",
    }
    for k in ("temperature_debut", "temperature_fin", "vent", "couverture"):
        lv, sv = lm.get(k), sm.get(k)
        if _field_blank(lv):
            continue
        if allowed is not None and labels[k] not in allowed:
            continue
        if k.startswith("temperature_"):
            lv = _as_int_temp(lv)
            sv = _as_int_temp(sv) if not _field_blank(sv) else None
        if _field_blank(sv) or (k.startswith("temperature_") and user_set and lv != sv):
            meteo_overlay[k] = lv
            changes.append(labels[k])
    if meteo_overlay:
        merged = dict(sm)
        merged.update(meteo_overlay)
        out["meteo"] = merged

    sc = server.get("configuration") if isinstance(server.get("configuration"), dict) else {}
    lc = local.get("configuration") if isinstance(local.get("configuration"), dict) else {}
    cfg_overlay: dict = {}
    cfg_labels = {
        "detecteur_enregistreur_type": "type d'enregistreur",
        "detecteur_enregistreur_serie": "n° de série",
        "micro0_modele": "micro",
        "micro0_hauteur": "hauteur micro",
        "micro1_modele": "micro droit",
        "micro1_hauteur": "hauteur micro droit",
    }
    for k, label in cfg_labels.items():
        lv, sv = lc.get(k), sc.get(k)
        if _field_blank(lv):
            continue
        if allowed is not None and label not in allowed:
            continue
        lv_s, sv_s = str(lv).strip(), ("" if _field_blank(sv) else str(sv).strip())
        missing = _field_blank(sv)
        serial_diff = k == "detecteur_enregistreur_serie" and sv_s and lv_s != sv_s
        if missing or serial_diff:
            cfg_overlay[k] = lv
            changes.append(label)
    if cfg_overlay:
        merged_c = dict(sc)
        merged_c.update(cfg_overlay)
        out["configuration"] = merged_c

    if changes:
        out["changes"] = changes
    return out


def _parse_summary_dt(date_s: str, time_s: str) -> datetime | None:
    # Format "2025-Sep-03", "19:46:00"
    for fmt in ("%Y-%b-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(f"{date_s} {time_s}", fmt)
        except ValueError:
            continue
    return None


def parse_summary_txt(path: Path) -> SummaryInfo | None:
    """
    Parse un fichier SMxxxxx_Summary.txt (Wildlife Acoustics).
    Colonnes attendues : DATE,TIME,LAT,NS,LON,EW,POWER(V),TEMP(C),#FSFILES,#ZCFILES,#SCRUBBED
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
    except OSError:
        return None
    if len(lines) < 2:
        return None

    header = [h.strip() for h in lines[0].split(",")]
    try:
        idx = {
            "date": header.index("DATE"),
            "time": header.index("TIME"),
            "lat": header.index("LAT"),
            "ns": header.index("NS"),
            "lon": header.index("LON"),
            "ew": header.index("EW"),
            "power": header.index("POWER(V)"),
            "temp": header.index("TEMP(C)"),
            "fs": header.index("#FSFILES"),
        }
    except ValueError:
        return None

    info = SummaryInfo(path=path)
    temps: list[float] = []
    first = last = None
    fs_total = 0
    for ln in lines[1:]:
        cols = [c.strip() for c in ln.split(",")]
        if len(cols) < max(idx.values()) + 1:
            continue
        dt = _parse_summary_dt(cols[idx["date"]], cols[idx["time"]])
        try:
            t = float(cols[idx["temp"]])
            temps.append(t)
        except ValueError:
            t = None
        try:
            bat = float(cols[idx["power"]])
        except ValueError:
            bat = None
        try:
            fs_total += int(cols[idx["fs"]])
        except ValueError:
            pass
        if first is None:
            first = (dt, t, bat, cols[idx["lat"]], cols[idx["lon"]])
        last = (dt, t, bat)
        if dt is not None:
            info.samples.append((dt, t))
        info.n_lines += 1

    if first:
        info.start_dt = first[0]
        info.temp_start = first[1]
        info.battery_start = first[2]
        try:
            info.lat = float(first[3])
        except ValueError:
            pass
        try:
            info.lon = float(first[4])
        except ValueError:
            pass
    if last:
        info.end_dt = last[0]
        info.temp_end = last[1]
        info.battery_end = last[2]
    if temps:
        info.temp_min = min(temps)
        info.temp_max = max(temps)
    info.n_fs_files_total = fs_total
    return info


def should_prefer_wav_dates(
    summary: SummaryInfo | None,
    wav_min: datetime | None,
    *,
    max_span_hours: float = 18.0,
) -> bool:
    """True si les dates de participation / dossier doivent venir des WAV.

    Les WAV du dossier sont la vérité. Un Summary SM4 peut couvrir plus que
    cette nuit : carte SD non formatée entre deux poses (l'ancienne nuit
    reste, la nouvelle s'ajoute), ou copie locale incomplète.

    - pas de WAV horodaté → False (on garde le Summary) ;
    - pas de Summary mais des WAV → True ;
    - jour calendaire WAV ≠ jour de début Summary → True ;
    - Summary plus long qu'une nuit (défaut 18 h) → True.
    """
    if wav_min is None:
        return False
    if summary is None or summary.start_dt is None:
        return True
    if wav_min.date() != summary.start_dt.date():
        return True
    if summary.end_dt is not None:
        span_h = (summary.end_dt - summary.start_dt).total_seconds() / 3600.0
        if span_h > max_span_hours:
            return True
    return False


def _fmt_short_dt(dt: datetime | None) -> str:
    return dt.strftime("%d/%m %H:%M") if dt is not None else "?"


def summary_vs_wav_warning(
    summary: SummaryInfo | None,
    wav_min: datetime | None,
    wav_max: datetime | None = None,
) -> str | None:
    """Message utilisateur si le Summary ne décrit pas les WAV du dossier.

    None si rien à signaler (pas de Summary, pas de WAV, ou même nuit).
    """
    if summary is None or summary.start_dt is None or wav_min is None:
        return None
    if not should_prefer_wav_dates(summary, wav_min):
        return None
    wav_end = wav_max or wav_min
    return (
        f"Le Summary.txt ({_fmt_short_dt(summary.start_dt)} → "
        f"{_fmt_short_dt(summary.end_dt)}) ne correspond pas aux WAV du "
        f"dossier ({_fmt_short_dt(wav_min)} → {_fmt_short_dt(wav_end)}).\n\n"
        "Les fichiers WAV font foi. Cause fréquente : carte SD non formatée "
        "entre deux nuits — le Summary accumule l'ancienne pose.\n\n"
        "La date retenue est celle des WAV. Vérifiez les températures "
        "(le Summary peut mélanger plusieurs nuits)."
    )


def summary_temps_in_window(
    summary: SummaryInfo | None,
    t0: datetime | None,
    t1: datetime | None,
) -> tuple[float | None, float | None]:
    """T° début/fin des lignes Summary dans [t0, t1]. (None, None) si rien."""
    if summary is None or t0 is None or t1 is None:
        return None, None
    lo, hi = (t0, t1) if t0 <= t1 else (t1, t0)
    temps = [
        t for dt, t in (summary.samples or [])
        if dt is not None and lo <= dt <= hi and t is not None
    ]
    if not temps:
        return None, None
    return temps[0], temps[-1]


def list_session_wav_names(session: Path) -> list[str]:
    """Noms WAV de la session (Data_k après TE×10, sinon Data/ ou racine)."""
    session = Path(session)
    dirs: list[Path] = []
    dk = session / "Data_k"
    if dk.is_dir():
        dirs.append(dk)
    if _dir_has_wavs(session):
        dirs.append(session)
    sub = _find_raw_wav_subdir(session)
    if sub is not None and sub not in dirs:
        dirs.append(sub)
    names: list[str] = []
    seen: set[str] = set()
    for d in dirs:
        try:
            for p in d.iterdir():
                if p.is_file() and p.suffix.lower() == ".wav" and p.name not in seen:
                    seen.add(p.name)
                    names.append(p.name)
        except OSError:
            continue
    return names


# ---------------------------------------------------------------------------
# Session : état détecté d'un dossier d'enregistrement
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    path: Path
    name: str                       # nom du dossier
    campaign: str                   # dossier parent (= projet/campagne)
    n_wav: int = 0
    n_w4v: int = 0                  # fichiers compressés Wildlife Acoustics
    n_wav_vigiechiro: int = 0       # fichiers déjà préfixés Car...
    n_wav_raw: int = 0              # fichiers nommés SMUxxxxx_date_time.wav
    n_wav_unknown: int = 0
    n_wav_with_000_suffix: int = 0  # sortis de Kaleidoscope (ou équivalent)
    total_bytes: int = 0

    # Détection TE
    sr_samples: list[int] = field(default_factory=list)
    looks_time_expanded: bool | None = None

    # Fichiers annexes
    has_summary_txt: bool = False
    summary: SummaryInfo | None = None
    has_observations_xlsx: bool = False
    observations_paths: list[Path] = field(default_factory=list)
    has_stats_snapshot: bool = False  # _stats_before_cleanup.json
    has_data_k_mirror: bool = False   # dossier Data_k/ sibling ou sous-dossier

    # Drapeaux pipeline
    flag_renamed: bool = False
    flag_te10_done: bool = False
    flag_uploaded_hint: bool = False   # heuristique, pas fiable à 100%
    flag_analyzed: bool = False
    flag_cleaned: bool = False
    # Détection d'état incomplet : participation créée côté serveur mais
    # xlsx pas encore récupéré → soit Tadarida en cours, soit upload
    # interrompu. Dans les deux cas, l'utilisateur peut relancer "Upload +
    # Tadarida" pour reprendre. Affiché en sidebar via un glyph dédié.
    flag_pending_fetch: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        d["observations_paths"] = [str(p) for p in self.observations_paths]
        if self.summary:
            d["summary"] = {
                "path": str(self.summary.path),
                "start_dt": self.summary.start_dt.isoformat() if self.summary.start_dt else None,
                "end_dt": self.summary.end_dt.isoformat() if self.summary.end_dt else None,
                "n_lines": self.summary.n_lines,
                "temp_start": self.summary.temp_start,
                "temp_end": self.summary.temp_end,
                "temp_min": self.summary.temp_min,
                "temp_max": self.summary.temp_max,
                "lat": self.summary.lat,
                "lon": self.summary.lon,
                "battery_start": self.summary.battery_start,
                "battery_end": self.summary.battery_end,
                "n_fs_files_total": self.summary.n_fs_files_total,
            }
        return d


# Noms de sous-dossiers où les WAV bruts peuvent être logés
RAW_WAV_SUBDIR_NAMES = {"data", "wavs", "wave", "records", "recordings"}
# Dossiers qui servent de miroirs TE×10 (à ne PAS considérer comme sessions séparées)
MIRROR_PARENT_NAMES = {"data_k", "1-k", "1k", "data_te", "te10"}


def resolve_session_root(folder: Path | str) -> Path:
    """Si ``folder`` est un miroir TE×10 (Data_k, 1-K, …), remonte au parent.

    Cas typique : export USB Data_k-only, ou Data/ déjà nettoyé. Les WAV
    vivent dans ``<session>/Data_k/`` ; le scan ne doit pas prendre Data_k
    pour la session (sinon xlsx / Summary / manifest restent invisibles).
    """
    folder = Path(folder)
    try:
        folder = folder.resolve()
    except OSError:
        pass
    if folder.name.lower() not in MIRROR_PARENT_NAMES:
        return folder
    parent = folder.parent
    if parent == folder:
        return folder
    return parent


def _count_top_wavs(p: Path) -> int:
    """Nombre de WAV directement dans ``p`` (pas les sous-dossiers)."""
    n = 0
    try:
        for child in p.iterdir():
            if child.is_file() and child.suffix.lower() == ".wav":
                n += 1
    except OSError:
        return 0
    return n


def _pick_te10_mirror(folder: Path) -> Path | None:
    """Miroir TE×10 le plus fourni.

    Un dossier campagne ``Data_k/<session>/`` presque vide ne doit pas
    masquer le ``Data_k/`` local complet. À nombre égal, le dossier local gagne.
    """
    candidates = [
        folder.parent / "Data_k" / folder.name,
        folder / "Data_k",
        folder / "1-K",
    ]
    best: Path | None = None
    best_key = (-1, -1)
    for mirror in candidates:
        if not mirror.is_dir() or not _dir_has_wavs(mirror):
            continue
        local = 1 if mirror.parent == folder else 0
        key = (_count_top_wavs(mirror), local)
        if key > best_key:
            best_key = key
            best = mirror
    return best


def _dir_has_wavs(p: Path) -> bool:
    try:
        for child in p.iterdir():
            if child.is_file() and child.suffix.lower() in (".wav", ".w4v"):
                return True
    except (OSError, PermissionError):
        pass
    return False


def _find_raw_wav_subdir(session_root: Path) -> Path | None:
    """Si les WAV sont logés dans un sous-dossier (ex: Data/), le retourner."""
    try:
        for child in session_root.iterdir():
            if child.is_dir() and child.name.lower() in RAW_WAV_SUBDIR_NAMES:
                if _dir_has_wavs(child):
                    return child
    except (OSError, PermissionError):
        pass
    return None


def _find_data_k_subdir(session_root: Path) -> Path | None:
    """Sous-dossier miroir TE×10 local (Data_k/, 1-K/, …) s'il contient des WAV."""
    try:
        for child in session_root.iterdir():
            if child.is_dir() and child.name.lower() in MIRROR_PARENT_NAMES:
                if _dir_has_wavs(child):
                    return child
    except (OSError, PermissionError):
        pass
    return None


def _has_session_markers(folder: Path) -> bool:
    """True si le dossier porte un manifest ou un tableur d'observations."""
    try:
        for child in folder.iterdir():
            if not child.is_file():
                continue
            if child.name == "_session_manifest.json":
                return True
            low = child.name.lower()
            if low.startswith("participation-") and "observations" in low:
                if low.endswith((".xlsx", ".csv")):
                    return True
    except (OSError, PermissionError):
        pass
    return False


def find_summary_file(folder: Path) -> Path | None:
    """Trouve le fichier Summary d'une session, par NOM puis par CONTENU.

    Certains enregistreurs renomment le .txt avec le nom de projet paramétré
    dans le boîtier (au lieu de ``<serie>_Summary.txt``). On cherche donc :
      1. d'abord un nom canonique (``*_summary.txt`` ou ``summary.txt``) ;
      2. sinon, tout autre ``.txt`` dont le contenu est un vrai tableau Summary
         (en-tête ``DATE,TIME,LAT,…`` validé par ``parse_summary_txt``).
    """
    try:
        txts = [c for c in folder.iterdir()
                if c.is_file() and c.suffix.lower() == ".txt"]
    except (OSError, PermissionError):
        return None
    for c in txts:                       # 1. nom canonique (rapide)
        low = c.name.lower()
        if low.endswith("_summary.txt") or low == "summary.txt":
            return c
    for c in txts:                       # 2. fallback par contenu
        if parse_summary_txt(c) is not None:
            return c
    return None


def _collect_annexes(folder: Path, state: SessionState) -> None:
    """Cherche Summary.txt, observations xlsx/csv et stats json dans `folder`."""
    summ = find_summary_file(folder)
    if summ is not None:
        state.has_summary_txt = True
        if state.summary is None:
            state.summary = parse_summary_txt(summ)
    try:
        for child in folder.iterdir():
            if not child.is_file():
                continue
            low = child.name.lower()
            if low.startswith("participation-") and (low.endswith(".xlsx") or low.endswith(".csv")):
                if "observations" in low:
                    state.has_observations_xlsx = True
                    state.observations_paths.append(child)
            elif low == "_stats_before_cleanup.json":
                state.has_stats_snapshot = True
    except (OSError, PermissionError):
        pass


def _scan_wavs(wav_dir: Path, state: SessionState, sample_wav_for_sr: int = 3) -> None:
    wav_files: list[Path] = []
    try:
        for child in wav_dir.iterdir():
            if not child.is_file():
                continue
            low = child.name.lower()
            if low.endswith(".wav"):
                state.n_wav += 1
                wav_files.append(child)
                cls = classify_wav_name(child.name)
                if cls == "vigiechiro":
                    state.n_wav_vigiechiro += 1
                    m = VIGIECHIRO_RE.match(child.name)
                    if m and m.group("suffix"):
                        state.n_wav_with_000_suffix += 1
                elif cls == "raw":
                    state.n_wav_raw += 1
                else:
                    state.n_wav_unknown += 1
                try:
                    state.total_bytes += child.stat().st_size
                except OSError:
                    pass
            elif low.endswith(".w4v"):
                state.n_w4v += 1
    except (OSError, PermissionError):
        pass

    for wav in wav_files[:sample_wav_for_sr]:
        info = read_wav_info(wav)
        if info:
            state.sr_samples.append(info.sample_rate)
    if state.sr_samples:
        te_hits = sum(1 for sr in state.sr_samples if sr <= 60_000)
        state.looks_time_expanded = te_hits > len(state.sr_samples) / 2


def _te10_mirror_incomplete(wav_dir: Path, mirror: Path) -> bool:
    """True si Data_k n'a pas toutes les tranches de 5 s.

    Compare les dest de ``te10.plan_file`` (en-têtes seulement) aux WAV du
    miroir, pour les 3 plus gros bruts. Couvre le trou Titley 0.7.2 (1:1)
    et un découpage partiel (ex. 2/3 d'un WAV de 12 s).
    """
    try:
        raws = [p for p in wav_dir.iterdir()
                if p.is_file() and p.suffix.lower() == ".wav"]
        if not raws:
            return False
        k_names = {p.name.lower() for p in mirror.iterdir()
                   if p.is_file() and p.suffix.lower() == ".wav"}
        if len(k_names) < len(raws):
            return True
        from te10 import plan_file
        largest = sorted(raws, key=lambda p: p.stat().st_size, reverse=True)[:3]
        for source in largest:
            try:
                plans = plan_file(source, mirror, 10, 5.0)
            except (OSError, ValueError, EOFError, wave.Error):
                return True
            for plan in plans:
                if plan.dst.name.lower() not in k_names:
                    return True
    except OSError:
        return True
    return False


def analyze_session(folder: Path, sample_wav_for_sr: int = 3) -> SessionState:
    """
    Inspecte un dossier de session et renvoie son état.

    Gère 3 dispositions :
      (A) WAV directement dans le dossier session
      (B) WAV dans un sous-dossier 'Data/'  (ex. enregistreurs SM4BAT)
      (C) WAV uniquement dans Data_k/ (export USB Data_k-only, Data/ nettoyé)

    Si ``folder`` est lui-même un miroir Data_k/, on remonte au parent
    (xlsx / Summary / manifest vivent à la racine de session).

    Les annexes (Summary.txt, observations.xlsx) sont cherchées à la racine
    de la session ET dans le sous-dossier WAV.

    Un miroir TE×10 peut exister dans `<campagne>/Data_k/<nom-session>/` ou
    dans `<session>/Data_k/`.
    """
    folder = resolve_session_root(folder)
    s = SessionState(
        path=folder,
        name=folder.name,
        campaign=folder.parent.name,
    )

    # Déterminer où vivent les WAV. Data_k n'est le wav_dir que s'il n'y a
    # plus de bruts (sinon on garderait Data/ comme source pour le contrôle
    # de couverture TE×10).
    wav_dir = folder if _dir_has_wavs(folder) else _find_raw_wav_subdir(folder)
    data_k_local = _find_data_k_subdir(folder)
    if wav_dir is None and data_k_local is not None:
        wav_dir = data_k_local
    if wav_dir is not None:
        _scan_wavs(wav_dir, s, sample_wav_for_sr=sample_wav_for_sr)

    # Annexes : on regarde la racine de la session et le dossier WAV
    _collect_annexes(folder, s)
    if wav_dir is not None and wav_dir != folder:
        _collect_annexes(wav_dir, s)

    # Détection du miroir TE×10 :
    #   - sibling au niveau campagne : <campagne>/Data_k/<nom>/
    #   - sous-dossier local         : <session>/Data_k/
    te10_mirror = _pick_te10_mirror(folder)
    if te10_mirror is not None:
        s.has_data_k_mirror = True

    # Drapeaux haut niveau
    s.flag_renamed = s.n_wav > 0 and s.n_wav_vigiechiro >= s.n_wav_raw and s.n_wav_vigiechiro > 0
    s.flag_te10_done = s.looks_time_expanded is True or s.has_data_k_mirror or s.n_wav_with_000_suffix > 0
    s.flag_analyzed = s.has_observations_xlsx
    s.flag_cleaned = s.has_stats_snapshot
    s.flag_uploaded_hint = s.flag_analyzed
    # Contrôle Titley (Data_k incomplet vs bruts) : seulement tant que le
    # nettoyage n'a pas eu lieu. Après cleanup, Data_k est un sous-ensemble
    # volontaire (contacts sous seuil purgés) : 783 k vs 895 bruts n'est
    # PAS un TE×10 raté, sinon la pastille reste jaune et Préparer ressort.
    if (not s.flag_cleaned
            and wav_dir is not None and te10_mirror is not None
            and wav_dir.resolve() != te10_mirror.resolve()
            and _te10_mirror_incomplete(wav_dir, te10_mirror)):
        s.flag_te10_done = False

    # Détection "participation créée côté serveur mais xlsx local absent" :
    # le manifest a un vigiechiro_participation_id mais on n'a pas trouvé
    # d'xlsx d'observations sur disque. Soit Tadarida est encore en cours,
    # soit l'upload a été interrompu. Un Sync API + relance Upload+Tadarida
    # remet d'équerre.
    try:
        from manifest import Manifest as _Manifest
        m = _Manifest.load(folder)
        if (m and m.meta
                and m.meta.get("vigiechiro_participation_id")
                and not s.flag_analyzed):
            s.flag_pending_fetch = True
    except Exception:
        pass

    return s


def walk_sessions(root: Path, max_depth: int = 4) -> list[Path]:
    """
    Retourne la liste des dossiers candidats 'session' sous `root`.

    Règles :
      - Un dossier est une session s'il contient directement des WAV,
        un sous-dossier Data/ avec des WAV, un Data_k/ local avec des WAV,
        un ``_session_manifest.json``, ou un tableur participation-*-observations.
      - Data_k/ (et 1-K, …) n'est JAMAIS une session : c'est le miroir TE×10.
        S'il contient des WAV, le parent est la session (export USB Data_k-only).
      - On ignore les dossiers sous un parent Data_k/ (layout sibling campagne).
      - On ignore les dossiers techniques (commencent par . ou _).
      - On ne descend pas dans un dossier déjà identifié comme session.
    """
    root = root.resolve()
    out: list[Path] = []
    seen: set[Path] = set()

    def _add(p: Path) -> None:
        try:
            p = p.resolve()
        except OSError:
            pass
        if p in seen:
            return
        seen.add(p)
        out.append(p)

    def _rec(d: Path, depth: int):
        if depth > max_depth:
            return
        if d.name.startswith(".") or d.name.startswith("_"):
            return
        # Enfants d'un miroir sibling (campagne/Data_k/<session>/) : pas une session
        if d.parent.name.lower() in MIRROR_PARENT_NAMES:
            return

        # Le miroir lui-même n'est jamais une session. Le parent l'est.
        if d.name.lower() in MIRROR_PARENT_NAMES:
            if _dir_has_wavs(d):
                parent = d.parent
                try:
                    parent.resolve().relative_to(root)
                    _add(parent)
                except ValueError:
                    # Workspace = Data_k ouvert tel quel (dernier recours)
                    _add(d)
            return

        if (_dir_has_wavs(d)
                or _find_raw_wav_subdir(d) is not None
                or _find_data_k_subdir(d) is not None
                or _has_session_markers(d)):
            _add(d)
            return

        try:
            for child in sorted(d.iterdir()):
                if child.is_dir():
                    _rec(child, depth + 1)
        except (OSError, PermissionError):
            return

    _rec(root, 0)
    return out
