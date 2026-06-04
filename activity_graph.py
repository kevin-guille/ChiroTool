"""
activity_graph.py — agrégation et rendu d'un graphe d'activité horaire.

Source de données : xlsx d'observations Vigie-Chiro (téléchargé via
``download_observations_as_xlsx`` ou présent à la racine de la session).
On utilise en priorité le ``validateur_taxon`` (validation humaine via
ChiroSurf), avec fallback sur ``observateur_taxon`` puis ``tadarida_taxon``.

L'heure de chaque contact est extraite du **nom du fichier WAV**, pas du
champ ``temps_debut`` (qui est en secondes depuis le début de l'enregistrement
et nécessiterait de recouper avec l'heure de début du WAV).

Format attendu du nom de fichier :
``Car<SITE>-<YYYY>-Pass<N>-<POINT>-<SERIAL>_<YYYYMMDD>_<HHMMSS>[_…].wav``

Ce module est autonome (pas de dépendance Tk/CTk) → testable et réutilisable.
Le rendu visuel se fait dans ``gui_activity.py``.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Iterable


# Regex extraction de l'heure depuis le nom de fichier
_RE_FILENAME_TIMESTAMP = re.compile(
    r"_(\d{8})_(\d{2})(\d{2})(\d{2})(?:_\d+)?(?:\..+)?$"
)

# Regex contexte session : préfixe canonique Vigie-Chiro
#   Car<SITE>-<YYYY>-Pass<N>-<POINT>-<SERIAL>_<...>
_RE_FILENAME_CONTEXT = re.compile(
    r"^Car(?P<site>\d{5,6})-(?P<year>\d{4})-Pass(?P<passage>\d+)-"
    r"(?P<point>[A-Za-z]\d+)-(?P<serial>[^_]+)_"
)


def parse_filename_context(name: str) -> dict | None:
    """Extrait site / passage / point depuis un nom WAV canonique.

    Retourne None si le nom n'est pas au format Vigie-Chiro
    (WAV brut non renommé par exemple).
    """
    m = _RE_FILENAME_CONTEXT.match(name)
    if not m:
        return None
    d = m.groupdict()
    try:
        d["passage"] = int(d["passage"])
    except (TypeError, ValueError):
        return None
    d["site"] = str(d["site"]).zfill(6)
    d["point"] = d["point"].upper()
    return d


@dataclass
class HourlyBin:
    """Comptage de contacts validés sur une tranche horaire d'une nuit."""
    start_minutes_from_midnight: int  # 0..1440
    n_contacts: int = 0


@dataclass
class NightActivity:
    """Activité horaire pour 1 nuit, 1 espèce (ou groupe / "tous")."""
    label: str            # ex: "2025-07-12 · Pippip"
    night_date: str       # ISO YYYY-MM-DD
    taxon: str            # nom court ou "(tous)"
    bins: list[int]       # nb contacts par tranche, indexé sur _bin_index
    bin_minutes: int      # taille d'une tranche (5, 15, 30 minutes)


def _night_date_iso(date_s: str, minutes_from_midnight: int,
                     cutoff_hour: int = 12) -> str:
    """Retourne la date ISO de la NUIT à laquelle rattacher un contact.

    Un contact avant `cutoff_hour` (midi par défaut) est rattaché à la veille
    (nuit commencée la veille au soir). date_s au format YYYYMMDD.
    """
    from datetime import date, timedelta
    try:
        y, mo, d = int(date_s[:4]), int(date_s[4:6]), int(date_s[6:8])
        dd = date(y, mo, d)
    except (ValueError, IndexError):
        # Fallback : format brut sans rattachement
        return f"{date_s[:4]}-{date_s[4:6]}-{date_s[6:8]}"
    if minutes_from_midnight < cutoff_hour * 60:
        dd = dd - timedelta(days=1)
    return dd.isoformat()


def parse_filename_time(name: str) -> tuple[str, int] | None:
    """Extrait (date_yyyymmdd, minutes_from_midnight) depuis un nom de fichier.

    Retourne None si format non reconnu.
    """
    m = _RE_FILENAME_TIMESTAMP.search(name)
    if not m:
        return None
    date_s = m.group(1)
    h, mn, s = int(m.group(2)), int(m.group(3)), int(m.group(4))
    if not (0 <= h <= 23 and 0 <= mn <= 59 and 0 <= s <= 59):
        return None
    return date_s, h * 60 + mn


def best_taxon(row_lookup: dict, idx_validateur: int | None,
                idx_observateur: int | None,
                idx_tadarida: int | None) -> str | None:
    """Retourne le taxon le plus "trustworthy" disponible pour un contact.

    Priorité : validateur (humain) > observateur (humain) > tadarida (auto).
    Retourne None si la valeur est vide ou ne peut être lue.
    """
    for idx in (idx_validateur, idx_observateur, idx_tadarida):
        if idx is None:
            continue
        v = row_lookup.get(idx)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _bin_index(minutes_from_midnight: int, bin_size: int) -> int:
    """Index de la tranche horaire (toutes alignées sur minuit, en cycles 24h)."""
    minutes_from_midnight %= 1440
    return minutes_from_midnight // bin_size


def _bin_count(bin_size: int) -> int:
    return 1440 // bin_size


def aggregate_xlsx(xlsx_path: Path, *,
                    bin_minutes: int = 30,
                    taxon_filter: str | None = None,
                    use_only_validated: bool = False
                    ) -> dict[tuple[str, str, int | None, str, str], list[int]]:
    """Agrège un xlsx d'observations en
    ``{(site, point, passage, night_date, taxon): bins}``.

    - ``site`` : numéro à 6 chiffres (carré STOC). "?" si non extractible
    - ``point`` : "Z3", "A1", … "?" si non extractible
    - ``passage`` : entier (1, 2, …) ou None si non extractible
    - ``night_date`` : "YYYY-MM-DD"
    - ``taxon`` : nom du taxon (validateur > observateur > tadarida)

    Le contexte (site, point, passage) est extrait du **nom de fichier** de
    chaque contact (format canonique Vigie-Chiro Car<SITE>-<YYYY>-Pass<N>-
    <POINT>-...). Les contacts dont le nom n'est pas au format canonique
    sont quand même comptés sous la clé spéciale ("?", "?", None, …) pour
    ne pas les perdre, mais ils ne seront pas filtrables par site/point.

    - ``bin_minutes`` : taille d'une tranche (5, 15, 30, 60)
    - ``taxon_filter`` : si fourni, ne garde que les contacts de ce taxon
    - ``use_only_validated`` : si True, ignore les contacts sans validateur_taxon
    """
    import openpyxl
    if bin_minutes <= 0 or 1440 % bin_minutes != 0:
        raise ValueError("bin_minutes doit diviser 1440 (1, 5, 15, 30, 60…)")
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        try:
            header = next(rows)
        except StopIteration:
            return {}
        idx = {h: i for i, h in enumerate(header) if h}
        idx_filename = idx.get("nom du fichier")
        idx_validateur = idx.get("validateur_taxon")
        idx_observateur = idx.get("observateur_taxon")
        idx_tadarida = idx.get("tadarida_taxon")
        if idx_filename is None:
            return {}

        nbins = _bin_count(bin_minutes)
        result: dict[tuple[str, str, int | None, str, str], list[int]] = {}

        for r in rows:
            if not r or len(r) <= idx_filename:
                continue
            fname = r[idx_filename]
            if not fname:
                continue
            fname_s = str(fname)
            parsed_time = parse_filename_time(fname_s)
            if not parsed_time:
                continue
            date_s, mins = parsed_time
            # Notion de NUIT biologique : un contact après minuit (avant ~12h)
            # appartient à la nuit commencée la veille au soir. Sans ce
            # rattachement, les contacts de 22h le 3 sept et 02h le 4 sept
            # (même nuit) seraient comptés sur deux dates différentes.
            night_date = _night_date_iso(date_s, mins)

            # Extrait le contexte site/point/passage. Pour un fichier non
            # canonique on tombe sur ("?", "?", None) — ces lignes restent
            # comptées mais hors filtres site/point.
            ctx = parse_filename_context(fname_s)
            if ctx is not None:
                site = ctx["site"]
                point = ctx["point"]
                passage = ctx["passage"]
            else:
                site, point, passage = "?", "?", None

            row_lookup = {i: r[i] if i < len(r) else None for i in idx.values()}
            if use_only_validated:
                v = row_lookup.get(idx_validateur)
                if not v or not str(v).strip():
                    continue

            taxon = best_taxon(row_lookup, idx_validateur,
                                idx_observateur, idx_tadarida) or "(?)"

            if taxon_filter and taxon != taxon_filter:
                continue

            key = (site, point, passage, night_date, taxon)
            if key not in result:
                result[key] = [0] * nbins
            result[key][_bin_index(mins, bin_minutes)] += 1

        return result
    finally:
        try:
            wb.close()
        except Exception:
            pass


def aggregate_multi_xlsx(paths: Iterable[Path], **kwargs
                          ) -> dict[tuple[str, str], list[int]]:
    """Agrège plusieurs xlsx (multi-nuits) en un seul dict cumulé."""
    out: dict[tuple[str, str], list[int]] = {}
    for p in paths:
        try:
            partial = aggregate_xlsx(Path(p), **kwargs)
        except Exception:
            continue
        for k, bins in partial.items():
            if k not in out:
                out[k] = list(bins)
            else:
                # Cumul (additionne par bin)
                cur = out[k]
                for i, n in enumerate(bins):
                    if i < len(cur):
                        cur[i] += n
                    else:
                        cur.append(n)
    return out


def list_taxons(aggregated: dict, *, min_total: int = 1
                  ) -> list[tuple[str, int]]:
    """Liste des taxons avec nb total de contacts, triée décroissant."""
    totals: dict[str, int] = defaultdict(int)
    for key, bins in aggregated.items():
        # Support les anciennes clés (night, taxon) et les nouvelles
        # (site, point, passage, night, taxon)
        taxon = key[-1]
        totals[taxon] += sum(bins)
    return sorted(
        ((t, n) for t, n in totals.items() if n >= min_total),
        key=lambda x: x[1], reverse=True,
    )


def list_nights(aggregated: dict) -> list[str]:
    """Liste des nuits présentes (dates ISO uniques), triée."""
    # La nuit est en avant-dernière position (avant le taxon)
    nights = set()
    for key in aggregated.keys():
        nights.add(key[-2])
    return sorted(nights)


def list_sites(aggregated: dict) -> list[str]:
    """Liste des sites (carrés STOC) présents, triée.

    Inclut "?" si des fichiers non-canoniques sont présents → l'utilisateur
    voit qu'il y a des contacts non rattachés à un site précis et peut les
    cocher s'il veut quand même les inclure.
    """
    sites = set()
    for key in aggregated.keys():
        if len(key) >= 5:
            site = key[0]
            if site:
                sites.add(site)
    # "?" en dernier pour ne pas polluer le haut de la liste
    real = sorted(s for s in sites if s != "?")
    if "?" in sites:
        real.append("?")
    return real


def list_points(aggregated: dict, site_filter: str | None = None
                  ) -> list[str]:
    """Liste des points présents (filtrable par site)."""
    points = set()
    for key in aggregated.keys():
        if len(key) < 5:
            continue
        site, point = key[0], key[1]
        if site_filter and site != site_filter:
            continue
        if point:
            points.add(point)
    real = sorted(p for p in points if p != "?")
    if "?" in points:
        real.append("?")
    return real


def list_passages(aggregated: dict) -> list[int | None]:
    """Liste des passages (1, 2, …) présents. Inclut None si des contacts
    n'ont pas de passage extractible (fichiers non canoniques)."""
    passages = set()
    for key in aggregated.keys():
        if len(key) < 5:
            continue
        passages.add(key[2])
    real = sorted(p for p in passages if p is not None)
    if None in passages:
        real.append(None)  # type: ignore[arg-type]
    return real
