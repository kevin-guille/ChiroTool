"""
chiro_core.py
-------------
Fonctions partagées pour le traitement des enregistrements chiroptères.

Rien de spécifique à la GUI ici, juste de la logique pure testable.
Zéro dépendance hors stdlib (on utilisera openpyxl ailleurs uniquement pour le Suivi).
"""

from __future__ import annotations

import re
import wave
from dataclasses import dataclass, field, asdict
from datetime import datetime
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

# Nom "brut" typique sortie d'enregistreur (SMU03126_20250903_194608.wav, Audiomoth, etc.)
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


def classify_wav_name(name: str) -> str:
    """Retourne 'vigiechiro', 'raw' ou 'unknown' pour un nom de fichier WAV."""
    if VIGIECHIRO_RE.match(name):
        return "vigiechiro"
    if RAW_RE.match(name):
        return "raw"
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


def analyze_session(folder: Path, sample_wav_for_sr: int = 3) -> SessionState:
    """
    Inspecte un dossier de session et renvoie son état.

    Gère 2 dispositions :
      (A) WAV directement dans le dossier session
      (B) WAV dans un sous-dossier 'Data/'  (ex. enregistreurs SM4BAT)

    Dans les 2 cas, les annexes (Summary.txt, observations.xlsx) sont cherchées
    à la fois à la racine de la session ET dans le sous-dossier WAV.

    Un miroir TE×10 peut exister dans `<campagne>/Data_k/<nom-session>/` ou
    dans `<session>/Data_k/`.
    """
    folder = folder.resolve()
    s = SessionState(
        path=folder,
        name=folder.name,
        campaign=folder.parent.name,
    )

    # Déterminer où vivent les WAV
    wav_dir = folder if _dir_has_wavs(folder) else _find_raw_wav_subdir(folder)
    if wav_dir is not None:
        _scan_wavs(wav_dir, s, sample_wav_for_sr=sample_wav_for_sr)

    # Annexes : on regarde la racine de la session et le dossier WAV
    _collect_annexes(folder, s)
    if wav_dir is not None and wav_dir != folder:
        _collect_annexes(wav_dir, s)

    # Détection du miroir TE×10 :
    #   - sibling au niveau campagne : <campagne>/Data_k/<nom>/
    #   - sous-dossier local         : <session>/Data_k/
    mirror_candidates = [
        folder.parent / "Data_k" / folder.name,
        folder / "Data_k",
        folder / "1-K",
    ]
    for m in mirror_candidates:
        if m.is_dir() and _dir_has_wavs(m):
            s.has_data_k_mirror = True
            break

    # Drapeaux haut niveau
    s.flag_renamed = s.n_wav > 0 and s.n_wav_vigiechiro >= s.n_wav_raw and s.n_wav_vigiechiro > 0
    s.flag_te10_done = s.looks_time_expanded is True or s.has_data_k_mirror or s.n_wav_with_000_suffix > 0
    s.flag_analyzed = s.has_observations_xlsx
    s.flag_cleaned = s.has_stats_snapshot
    s.flag_uploaded_hint = s.flag_analyzed

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
        ou s'il contient un sous-dossier 'Data/' avec des WAV.
      - On ignore les dossiers sous un parent Data_k/ (miroirs TE×10).
      - On ignore les dossiers techniques (commencent par . ou _).
      - On ne descend pas dans un dossier déjà identifié comme session.
    """
    root = root.resolve()
    out: list[Path] = []

    def _rec(d: Path, depth: int):
        if depth > max_depth:
            return
        if d.name.startswith(".") or d.name.startswith("_"):
            return
        # Miroir : on saute tout le sous-arbre
        if d.parent.name.lower() in MIRROR_PARENT_NAMES:
            return

        # (A) WAV directement ici ?
        if _dir_has_wavs(d):
            out.append(d)
            return

        # (B) WAV dans un sous-dossier 'Data/' ?
        if _find_raw_wav_subdir(d) is not None:
            out.append(d)
            return

        try:
            for child in sorted(d.iterdir()):
                if child.is_dir():
                    _rec(child, depth + 1)
        except (OSError, PermissionError):
            return

    _rec(root, 0)
    return out
