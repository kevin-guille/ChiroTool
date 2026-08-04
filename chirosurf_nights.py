"""
chirosurf_nights.py — scission multi-nuits pour ChiroSurf (SPEC v0.6 / issue #3).

- 1 CSV par **nuit biologique** (coupure midi, aligné activity_graph)
- Naming D11 : ``Nuit{n}_{stem_origine}.csv`` / ``Nuit{n}_{stem_origine}_Vu.csv``
- Dossier ``chirosurf/`` créé **à la demande** (lazy)
- Ne jamais écraser un ``_Vu`` sans confirmation explicite

Logique pure + I/O fichier testable.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from activity_graph import _night_date_iso, parse_filename_time

CHIROSURF_DIRNAME = "chirosurf"  # sous-dossier session (SPEC D3)

_NUIT_FILE_RE = re.compile(
    r"^Nuit(?P<n>\d+)_(?P<rest>.+)\.csv$", re.IGNORECASE
)


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
    """Fichier présent (ou prévu) sous chirosurf/."""
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
    """Date ISO YYYY-MM-DD de la nuit bio pour un nom de fichier WAV/contact."""
    parsed = parse_filename_time(filename)
    if not parsed:
        m = re.search(r"(20\d{6})", filename or "")
        if not m:
            return None
        ds = m.group(1)
        return f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"
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
        slices.append(NightSlice(
            night_index=len(slices) + 1,
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
    result: list[ChiroSurfNightFile] = []

    for sl in slices:
        raw_path = out_dir / raw_csv_name(sl.night_index, origin)
        vu_path = out_dir / vu_csv_name(sl.night_index, origin)

        if force_raw or not raw_path.is_file():
            write_csv(raw_path, sl.headers, sl.rows)

        result.append(ChiroSurfNightFile(
            night_index=sl.night_index,
            night_date=sl.night_date,
            raw_path=raw_path,
            vu_path=vu_path,
            has_raw=raw_path.is_file(),
            has_vu=vu_path.is_file(),
            n_contacts=sl.n_contacts,
        ))
    return result


def list_chirosurf_nights(session_path: Path | str) -> list[ChiroSurfNightFile]:
    """Liste les fichiers chirosurf/ existants (sans générer)."""
    d = Path(session_path) / CHIROSURF_DIRNAME
    if not d.is_dir():
        return []

    by_idx: dict[int, dict] = {}
    for p in sorted(d.glob("Nuit*_*.csv")):
        m = _NUIT_FILE_RE.match(p.name)
        if not m:
            continue
        idx = int(m.group("n"))
        rest = m.group("rest")
        # « foo_Vu » / « foo_vu » → stem « foo » (suffixe _Vu de ChiroSurf)
        is_vu = rest.lower().endswith("_vu")
        stem = rest[: -len("_Vu")] if is_vu else rest
        if stem.endswith("_"):
            stem = stem[:-1]

        info = by_idx.setdefault(idx, {"stem": stem, "raw": None, "vu": None})
        if is_vu:
            info["vu"] = p
            # Le brut fixe le stem de référence s'il arrive après
            if info.get("raw") is None:
                info["stem"] = stem
        else:
            info["raw"] = p
            info["stem"] = stem

    result: list[ChiroSurfNightFile] = []
    for idx in sorted(by_idx):
        info = by_idx[idx]
        stem = info["stem"] or "observations"
        raw_path = info["raw"] or (d / raw_csv_name(idx, stem))
        vu_path = info["vu"] or (d / vu_csv_name(idx, stem))
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


def load_table_for_synthesis(
    session_path: Path | str,
    xlsx_path: Path | str,
    *,
    prefer_vu_night: int | None = None,
) -> tuple[list[str], list[list], str]:
    """Charge headers/rows pour synthèse (priorité ``_Vu`` si demandé)."""
    session_path = Path(session_path)
    if prefer_vu_night is not None:
        for nf in list_chirosurf_nights(session_path):
            if nf.night_index != prefer_vu_night:
                continue
            if nf.has_vu and nf.vu_path.is_file():
                h, r = read_csv(nf.vu_path)
                return h, r, f"_Vu nuit {prefer_vu_night}"
            if nf.has_raw and nf.raw_path.is_file():
                h, r = read_csv(nf.raw_path)
                return h, r, f"CSV nuit {prefer_vu_night}"
    h, r = rows_from_xlsx(xlsx_path)
    return h, r, Path(xlsx_path).name
