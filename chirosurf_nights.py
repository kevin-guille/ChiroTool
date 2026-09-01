"""
chirosurf_nights.py — scission multi-nuits pour ChiroSurf (SPEC v0.6 / issue #3).

- 1 CSV par **nuit biologique** (coupure **midi**, jamais minuit — SPEC D12)
- Une pose 21 h → 6 h = **une** nuit. Interdit : fallback date calendaire
  sans heure (ça recréait Nuit 1 / Nuit 2 de part et d'autre de minuit).
- Naming D11 : ``Nuit{n}_{stem_origine}.csv`` / ``Nuit{n}_{stem_origine}_Vu.csv``
- Dossier ``chirosurf/`` créé **à la demande** (lazy)
- Ne jamais écraser un ``_Vu`` sans confirmation explicite
- Issue #7 : ChiroSurf 4.x glob les WAV **dans le dossier du CSV** ;
  l'ouverture passe par une copie à côté de ``Data_k/``. Lecture ``_Vu``
  élargie (``Nuit1_`` / ``Nuit_1_`` / ``Nuit_1-``) + scan Data_k/Data.

Logique pure + I/O fichier testable.
"""

from __future__ import annotations

import csv
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from activity_graph import _night_date_iso, parse_filename_time

CHIROSURF_DIRNAME = "chirosurf"  # sous-dossier session (SPEC D3)

# D11 généré : Nuit1_stem.csv — lu aussi : Nuit_1_stem / Nuit_1-stem (issue #3/#7)
_NUIT_FILE_RE = re.compile(
    r"^Nuit_?(?P<n>\d+)[_-](?P<rest>.+)\.csv$", re.IGNORECASE
)

_AUDIO_DIR_NAMES = ("Data_k", "Data")
_AUDIO_EXTS = {".wav", ".mp3"}
_CSV_SCAN_DIRNAMES = (CHIROSURF_DIRNAME, "ChiroSurf_nuits") + _AUDIO_DIR_NAMES


@dataclass
class NightSlice:
    """Une nuit biologique extraite d'un tableur multi-nuits."""
    night_index: int
    night_date: date
    headers: list[str]
    rows: list[list]
    n_contacts: int = 0

    def __post_init__(self) -> None:
        self.n_contacts = len(self.rows)


@dataclass
class ChiroSurfNightFile:
    """Fichier présent (ou prévu) sous chirosurf/ — ``_Vu`` éventuellement ailleurs."""
    night_index: int
    night_date: date | None
    raw_path: Path
    vu_path: Path
    has_raw: bool = False
    has_vu: bool = False
    n_contacts: int | None = None

    @property
    def label(self) -> str:
        d = self.night_date.strftime("%d/%m") if self.night_date else "?"
        n = f" · {self.n_contacts} contacts" if self.n_contacts is not None else ""
        vu = " · _Vu" if self.has_vu else ""
        return f"{d} · Nuit {self.night_index}{n}{vu}"


def biological_night_key(filename: str) -> str | None:
    """Date ISO YYYY-MM-DD de la nuit bio pour un nom de fichier WAV/contact.

    Coupure à midi : 21h le 16 + 6h le 17 = **une** nuit (celle du 16).
    Pas de fallback « date calendaire sans heure » : ça scindait une pose
    à minuit en deux nuits dans la Synthèse.
    """
    parsed = parse_filename_time(filename)
    if not parsed:
        return None
    date_s, mins = parsed
    return _night_date_iso(date_s, mins)


def _col_file_index(headers: list[str]) -> int:
    lower = [str(h).lower().strip() for h in headers]
    for wanted in ("nom du fichier", "fichier", "filename"):
        if wanted in lower:
            return lower.index(wanted)
    return 0


def split_rows_by_biological_night(
    headers: list[str],
    rows: Iterable[list],
) -> list[NightSlice]:
    """Regroupe les lignes par nuit bio, tri chronologique → Nuit1, Nuit2…"""
    fi = _col_file_index(headers)
    buckets: dict[str, list[list]] = {}
    for row in rows:
        if not row:
            continue
        fn = str(row[fi]) if fi < len(row) and row[fi] is not None else ""
        key = biological_night_key(fn) or "_unknown"
        buckets.setdefault(key, []).append(list(row))

    known = sorted(
        ((k, v) for k, v in buckets.items() if k != "_unknown"),
        key=lambda kv: kv[0],
    )
    unknown = buckets.get("_unknown") or []

    slices: list[NightSlice] = []
    for i, (k, rws) in enumerate(known, start=1):
        try:
            y, m, d = map(int, k.split("-"))
            nd = date(y, m, d)
        except Exception:
            nd = date.today()
        slices.append(NightSlice(
            night_index=i, night_date=nd, headers=list(headers), rows=rws,
        ))
    if unknown:
        if slices:
            # Lignes sans horodatage : ne pas inventer une « Nuit 2 ».
            slices[-1].rows.extend(unknown)
            slices[-1].n_contacts = len(slices[-1].rows)
        else:
            slices.append(NightSlice(
                night_index=1,
                night_date=date.today(),
                headers=list(headers),
                rows=unknown,
            ))
    return slices


def origin_stem_from_xlsx_name(xlsx_path: Path | str) -> str:
    """Stem pour naming D11 à partir du xlsx/csv d'observations."""
    name = Path(xlsx_path).name
    low = name.lower()
    if low.endswith(".xlsx"):
        name = name[:-5]
    elif low.endswith(".csv"):
        name = name[:-4]
    name = re.sub(r"_[A-Za-z]{2,4}$", "", name)
    return name


def raw_csv_name(night_index: int, origin_stem: str) -> str:
    return f"Nuit{int(night_index)}_{origin_stem}.csv"


def vu_csv_name(night_index: int, origin_stem: str) -> str:
    return f"Nuit{int(night_index)}_{origin_stem}_Vu.csv"


def _strip_vu_suffix(rest: str) -> tuple[bool, str]:
    """``(is_vu, stem)`` — suffixe ``_Vu`` inséré par ChiroSurf avant ``.csv``."""
    if rest.lower().endswith("_vu"):
        stem = rest[:-3]
        if stem.endswith("_"):
            stem = stem[:-1]
        return True, stem
    return False, rest


def parse_chirosurf_csv_name(
    name: str,
) -> tuple[int | None, bool, str] | None:
    """Décode un nom de CSV nuit / ``_Vu``.

    Retourne ``(night_index | None, is_vu, stem)``. ``None`` si le fichier
    n'est pas un CSV ChiroSurf reconnaissable.

    Accepte D11 (``Nuit1_stem.csv``) et la convention Benjamin
    (``Nuit_1_stem.csv``, ``Nuit_1-observations_Vu.csv``). Un ``*_Vu.csv``
    sans préfixe Nuit est un orphelin (index ``None``) à rattacher par date.
    """
    name = Path(name).name
    if not name.lower().endswith(".csv"):
        return None
    m = _NUIT_FILE_RE.match(name)
    if m:
        is_vu, stem = _strip_vu_suffix(m.group("rest"))
        return int(m.group("n")), is_vu, stem or "observations"
    low = name.lower()
    if low.endswith("_vu.csv"):
        stem = name[: -len("_Vu.csv")]
        if stem.endswith("_"):
            stem = stem[:-1]
        return None, True, stem or "observations"
    return None


def is_chirosurf_vu_csv(path: Path | str) -> bool:
    """True si le chemin ressemble à un ``_Vu`` ChiroSurf (dossier attendu)."""
    p = Path(path)
    if p.suffix.lower() != ".csv" or not p.name.lower().endswith("_vu.csv"):
        return False
    return p.parent.name.lower() in {
        CHIROSURF_DIRNAME.lower(), "chirosurf_nuits", "data_k", "data",
    }


def count_audio_files(folder: Path | str) -> int:
    """Nombre de ``.wav`` / ``.mp3`` **directement** dans ``folder`` (pas récursif).

    ChiroSurf 4.x fait ``glob $dir/*.{wav,mp3}`` sans descendre les sous-dossiers.
    """
    d = Path(folder)
    if not d.is_dir():
        return 0
    n = 0
    try:
        for p in d.iterdir():
            if p.is_file() and p.suffix.lower() in _AUDIO_EXTS:
                n += 1
    except OSError:
        return 0
    return n


def find_session_audio_dir(session_path: Path | str) -> Path | None:
    """Dossier où ChiroSurf doit ouvrir le CSV : WAV présents au premier niveau.

    Priorité ``Data_k/`` puis ``Data/`` puis la racine de session.
    """
    session_path = Path(session_path)
    for name in _AUDIO_DIR_NAMES:
        d = session_path / name
        if count_audio_files(d) > 0:
            return d
    if count_audio_files(session_path) > 0:
        return session_path
    return None


class ChiroSurfLaunchError(Exception):
    """Pas de WAV à côté du CSV : ChiroSurf 4.x abort (glob Tcl, issue #7)."""


def stage_csv_beside_audio(src: Path | str, audio_dir: Path | str) -> Path:
    """Copie ``src`` dans ``audio_dir`` (même nom). Retourne le chemin à ouvrir."""
    src = Path(src)
    audio_dir = Path(audio_dir)
    dest = audio_dir / src.name
    try:
        if dest.resolve() == src.resolve():
            return dest
    except OSError:
        pass
    if dest.is_file():
        try:
            if (dest.stat().st_size == src.stat().st_size
                    and dest.stat().st_mtime >= src.stat().st_mtime):
                return dest
        except OSError:
            pass
    try:
        shutil.copy2(src, dest)
    except OSError:
        if dest.is_file():
            return dest
        raise
    return dest


def prepare_chirosurf_launch(
    session_path: Path | str,
    csv_path: Path | str,
) -> Path:
    """Prépare l'ouverture ChiroSurf : CSV **à côté des WAV**.

    ChiroSurf 4.x (``OpenFile``) fait ``glob $dossier_csv/*.{wav,mp3}`` sans
    ``-nocomplain`` : un CSV isolé dans ``chirosurf/`` plante le script de
    démarrage (issue #7).
    """
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise ChiroSurfLaunchError(f"CSV introuvable :\n{csv_path}")
    audio = find_session_audio_dir(session_path)
    if audio is None:
        raise ChiroSurfLaunchError(
            "Aucun fichier WAV/MP3 dans Data_k/, Data/ ni à la racine "
            "de la session.\n\n"
            "ChiroSurf exige que le tableur et les sons soient dans le "
            "même dossier. Si la nuit a déjà été nettoyée, les WAV ne "
            "sont plus là — impossible d'ouvrir cette nuit dans ChiroSurf."
        )
    return stage_csv_beside_audio(csv_path, audio)


def _prefer_newer(a: Path, b: Path) -> Path:
    try:
        if b.stat().st_mtime > a.stat().st_mtime:
            return b
    except OSError:
        pass
    return a


def _is_chirosurf_dir(folder: Path) -> bool:
    return folder.name.lower() in {CHIROSURF_DIRNAME.lower(), "chirosurf_nuits"}


def _iter_candidate_csvs(session_path: Path) -> list[Path]:
    """CSV dans chirosurf/ (d'abord) puis Data_k/ Data/ (copies / _Vu ChiroSurf)."""
    out: list[Path] = []
    for name in _CSV_SCAN_DIRNAMES:
        d = session_path / name
        if not d.is_dir():
            continue
        try:
            for p in sorted(d.iterdir()):
                if p.is_file() and p.suffix.lower() == ".csv":
                    out.append(p)
        except OSError:
            continue
    return out


def harvest_vu_sidecars(session_path: Path | str) -> list[Path]:
    """Ramène vers ``chirosurf/`` les ``_Vu`` écrits à côté des WAV.

    ChiroSurf écrit le ``_Vu`` **dans le dossier du CSV ouvert**. Après
    staging dans Data_k/, le sidecar y reste. On copie vers chirosurf/
    (nom conservé) si absent, ou si la source est plus récente.
    N'écrase jamais un ``_Vu`` chirosurf/ plus récent.
    """
    session_path = Path(session_path)
    dest_dir = ensure_chirosurf_dir(session_path)
    copied: list[Path] = []
    for folder_name in _AUDIO_DIR_NAMES:
        src_dir = session_path / folder_name
        if not src_dir.is_dir():
            continue
        try:
            entries = list(src_dir.iterdir())
        except OSError:
            continue
        for p in entries:
            if not p.is_file() or p.suffix.lower() != ".csv":
                continue
            parsed = parse_chirosurf_csv_name(p.name)
            if parsed is None or not parsed[1]:
                continue
            dest = dest_dir / p.name
            try:
                if dest.exists() and dest.resolve() == p.resolve():
                    continue
            except OSError:
                pass
            if dest.is_file():
                try:
                    if dest.stat().st_mtime >= p.stat().st_mtime:
                        continue
                except OSError:
                    continue
            try:
                shutil.copy2(p, dest)
            except OSError:
                continue
            copied.append(dest)
    return copied


def ensure_chirosurf_dir(session_path: Path | str) -> Path:
    d = Path(session_path) / CHIROSURF_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_csv(path: Path, headers: list[str], rows: list[list],
              *, delimiter: str = ";") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(headers)
        for r in rows:
            w.writerow([(c if c is not None else "") for c in r])
    return path


def read_csv(path: Path | str) -> tuple[list[str], list[list]]:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines:
        return [], []
    first = lines[0]
    delim = ";" if first.count(";") >= first.count(",") else ","
    reader = csv.reader(lines, delimiter=delim)
    headers = [h.strip().strip('"') for h in next(reader)]
    rows = []
    for r in reader:
        if not r or all(not str(c).strip() for c in r):
            continue
        rows.append([c.strip().strip('"') if isinstance(c, str) else c for c in r])
    return headers, rows


def rows_from_xlsx(xlsx_path: Path | str) -> tuple[list[str], list[list]]:
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.active
    data = list(ws.iter_rows(values_only=True))
    if not data:
        return [], []
    headers = [str(h) if h is not None else "" for h in data[0]]
    rows = [list(r) for r in data[1:] if any(c is not None for c in r)]
    return headers, rows


def _guess_date_from_csv_data(headers: list[str], rows: list[list]) -> date | None:
    fi = _col_file_index(headers)
    for r in rows[:80]:
        if fi < len(r) and r[fi]:
            key = biological_night_key(str(r[fi]))
            if key and key != "_unknown":
                try:
                    y, m, d = map(int, key.split("-"))
                    return date(y, m, d)
                except Exception:
                    pass
    return None


def prepare_chirosurf_nights(
    session_path: Path | str,
    xlsx_path: Path | str,
    *,
    force_raw: bool = False,
) -> list[ChiroSurfNightFile]:
    """Génère (si besoin) les CSV bruts nuit par nuit sous ``chirosurf/``.

    Régénère les bruts si absents ou si ``force_raw``. N'écrase jamais un ``_Vu``.
    """
    session_path = Path(session_path)
    xlsx_path = Path(xlsx_path)
    headers, rows = rows_from_xlsx(xlsx_path)
    if not headers:
        return []

    slices = split_rows_by_biological_night(headers, rows)
    origin = origin_stem_from_xlsx_name(xlsx_path)
    out_dir = ensure_chirosurf_dir(session_path)

    for sl in slices:
        raw_path = out_dir / raw_csv_name(sl.night_index, origin)
        if force_raw or not raw_path.is_file():
            write_csv(raw_path, sl.headers, sl.rows)

    harvest_vu_sidecars(session_path)
    discovered = {nf.night_index: nf for nf in list_chirosurf_nights(session_path)}

    result: list[ChiroSurfNightFile] = []
    for sl in slices:
        disc = discovered.get(sl.night_index)
        raw_path = out_dir / raw_csv_name(sl.night_index, origin)
        if disc is not None and disc.has_raw:
            raw_path = disc.raw_path
        vu_path = out_dir / vu_csv_name(sl.night_index, origin)
        has_vu = vu_path.is_file()
        if disc is not None and disc.has_vu and disc.vu_path.is_file():
            vu_path = disc.vu_path
            has_vu = True
        result.append(ChiroSurfNightFile(
            night_index=sl.night_index,
            night_date=sl.night_date,
            raw_path=raw_path,
            vu_path=vu_path,
            has_raw=raw_path.is_file(),
            has_vu=has_vu,
            n_contacts=sl.n_contacts,
        ))
    return result


def list_chirosurf_nights(session_path: Path | str) -> list[ChiroSurfNightFile]:
    """Liste les CSV nuit / ``_Vu`` (chirosurf/, Data_k/, Data/), sans générer."""
    session_path = Path(session_path)
    by_idx: dict[int, dict] = {}
    orphans: list[Path] = []

    for p in _iter_candidate_csvs(session_path):
        parsed = parse_chirosurf_csv_name(p.name)
        if parsed is None:
            continue
        idx, is_vu, stem = parsed
        if idx is None:
            if is_vu:
                orphans.append(p)
            continue
        info = by_idx.setdefault(idx, {"stem": stem, "raw": None, "vu": None})
        if is_vu:
            info["vu"] = p if info["vu"] is None else _prefer_newer(info["vu"], p)
            if info.get("raw") is None:
                info["stem"] = stem
        else:
            if info["raw"] is None or _is_chirosurf_dir(p.parent):
                info["raw"] = p
                info["stem"] = stem

    date_to_idx: dict[date, int] = {}
    for idx, info in by_idx.items():
        src = info.get("raw") or info.get("vu")
        if src and Path(src).is_file():
            try:
                headers, rows = read_csv(src)
                nd = _guess_date_from_csv_data(headers, rows)
            except Exception:
                nd = None
            if nd is not None:
                date_to_idx.setdefault(nd, idx)

    for p in orphans:
        parsed = parse_chirosurf_csv_name(p.name)
        stem = parsed[2] if parsed else "observations"
        try:
            headers, rows = read_csv(p)
            nd = _guess_date_from_csv_data(headers, rows)
        except Exception:
            nd = None
        idx: int | None = date_to_idx.get(nd) if nd is not None else None
        if idx is None and len(by_idx) == 1:
            idx = next(iter(by_idx))
        if idx is None and not by_idx:
            idx = 1
        if idx is None:
            continue
        info = by_idx.setdefault(idx, {"stem": stem, "raw": None, "vu": None})
        info["vu"] = p if info["vu"] is None else _prefer_newer(info["vu"], p)

    fallback_dir = session_path / CHIROSURF_DIRNAME
    result: list[ChiroSurfNightFile] = []
    for idx in sorted(by_idx):
        info = by_idx[idx]
        stem = info["stem"] or "observations"
        raw_path = info["raw"] or (fallback_dir / raw_csv_name(idx, stem))
        vu_path = info["vu"] or (fallback_dir / vu_csv_name(idx, stem))
        n_contacts = None
        night_date = None
        src = info["raw"] or info["vu"]
        if src and Path(src).is_file():
            try:
                headers, rows = read_csv(src)
                n_contacts = len(rows)
                night_date = _guess_date_from_csv_data(headers, rows)
            except Exception:
                pass
        result.append(ChiroSurfNightFile(
            night_index=idx,
            night_date=night_date,
            raw_path=Path(raw_path),
            vu_path=Path(vu_path),
            has_raw=bool(info["raw"] and Path(info["raw"]).is_file()),
            has_vu=bool(info["vu"] and Path(info["vu"]).is_file()),
            n_contacts=n_contacts,
        ))
    return result


def synthesis_night_menu(
    slices: list[NightSlice],
    vu_indexes: set[int] | None = None,
) -> list[tuple[int, str]]:
    """Choix du sélecteur Synthèse : ``(key, label)``.

    ``key == 0`` = toute la participation (uniquement s'il y a **plus d'une**
    nuit bio). Les clés ``1..N`` sont les nuits. Un ``_Vu`` existant est
    signalé dans le libellé — ChiroSurf n'est pas requis pour ouvrir Synthèse.
    """
    vu_indexes = vu_indexes or set()
    items: list[tuple[int, str]] = []
    if len(slices) > 1:
        total = sum(sl.n_contacts for sl in slices)
        items.append((0, f"Toute la participation · {total} contacts"))
    for sl in slices:
        d = sl.night_date.strftime("%d/%m") if sl.night_date else "?"
        extra = " · _Vu" if sl.night_index in vu_indexes else ""
        items.append((
            sl.night_index,
            f"Nuit {sl.night_index} · {d} · {sl.n_contacts} contacts{extra}",
        ))
    return items


def resolve_synthesis_table(
    headers: list[str],
    rows: list[list],
    *,
    night_index: int | None = None,
    vu_path: Path | str | None = None,
) -> tuple[list[str], list[list], str, bool]:
    """Table pour Synthèse : ``(headers, rows, source_label, mixed_nights)``.

    * ``night_index`` ``None`` ou ``0`` → toutes les lignes du tableur.
    * sinon une nuit biologique ; ``vu_path`` prioritaire s'il existe.
    ``mixed_nights`` True si le cumul mélange plusieurs nuits (classes
    d'activité contacts/nuit non applicables).
    """
    slices = split_rows_by_biological_night(headers, rows)
    mixed_all = len(slices) > 1
    if night_index is None or int(night_index) == 0:
        return list(headers), list(rows), "xlsx (toute la participation)", mixed_all
    idx = int(night_index)
    if vu_path is not None and Path(vu_path).is_file():
        h, r = read_csv(vu_path)
        return h, r, f"_Vu nuit {idx}", False
    for sl in slices:
        if sl.night_index == idx:
            d = sl.night_date.strftime("%d/%m") if sl.night_date else "?"
            return list(sl.headers), list(sl.rows), f"xlsx · Nuit {idx} · {d}", False
    return list(headers), list(rows), "xlsx", mixed_all


def load_table_for_synthesis(
    session_path: Path | str,
    xlsx_path: Path | str,
    *,
    prefer_vu_night: int | None = None,
    night_index: int | None = None,
) -> tuple[list[str], list[list], str]:
    """Charge headers/rows pour synthèse (priorité ``_Vu`` si demandé).

    Rétrocompatible (3-tuple). Préfère ``night_index`` s'il est fourni,
    sinon ``prefer_vu_night``.
    """
    session_path = Path(session_path)
    xlsx_path = Path(xlsx_path)
    target = night_index if night_index is not None else prefer_vu_night
    headers, rows = rows_from_xlsx(xlsx_path)
    vu_path = None
    if target:
        for nf in list_chirosurf_nights(session_path):
            if nf.night_index != int(target):
                continue
            if nf.has_vu and nf.vu_path.is_file():
                vu_path = nf.vu_path
            break
    h, r, src, _mixed = resolve_synthesis_table(
        headers, rows, night_index=target, vu_path=vu_path,
    )
    return h, r, src
