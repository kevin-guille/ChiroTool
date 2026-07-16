"""
taxons.py — classification des codes taxons Tadarida/Vigie-Chiro en groupes.

Utilise la liste officielle ``SpeciesListComplete.csv`` récupérée depuis le
dépôt officiel du Muséum (YvesBas/Tadarida-C, dossier Sonotypes).

  https://github.com/YvesBas/Tadarida-C/blob/master/Sonotypes/SpeciesListComplete.csv

754 taxons avec leur groupe fin (16 catégories). On regroupe ici en 5 groupes
métier pour le nettoyage :

  noise     : bruit, suppression systématique
  chiros    : chauves-souris (priorité absolue dans la règle OR)
  orthos    : tous les insectes (bush-cricket, grasshopper, cicada, cricket,
              beetle, moth, bee, fly, buzz, social, insect divers)
  micromam  : autres mammifères (other-mammal, rongeurs, musaraignes, ...)
  oiseaux   : oiseaux nocturnes
  unknown   : non classé (amphibiens, codes inconnus, ...)

Lookup :
  1. match exact dans le CSV (insensible à la casse) → groupe fin → groupe métier
  2. fallback : mapping hardcodé par préfixe de genre (robustesse si CSV absent)
  3. dernier recours : ``unknown``

Le CSV peut être absent sans casser le code : on retombe sur la table
hardcodée de secours (couvre les genres les plus courants observés).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Final

from resources import resource_path


GROUPS: Final = ("noise", "chiros", "orthos", "micromam", "oiseaux", "unknown")

# Mapping des groupes fins (CSV officiel) vers nos 5 groupes métier
FINE_TO_BUSINESS: dict[str, str] = {
    "noise": "noise",
    "bat": "chiros",
    "bird": "oiseaux",
    "other-mammal": "micromam",
    "bush-cricket": "orthos",
    "ground-cricket": "orthos",
    "grasshopper": "orthos",
    "cicada": "orthos",
    "insect": "orthos",
    "moth": "orthos",
    "beetle": "orthos",
    "bee": "orthos",
    "fly": "orthos",
    "buzz": "orthos",
    "social": "orthos",
    # Amphibiens : pas de cible métier claire → unknown
    "frog": "unknown",
}

# Fallback par préfixe de genre (3 premières lettres du code) — si CSV absent
FALLBACK_PREFIX: dict[str, str] = {
    # Chiroptères
    "bar": "chiros", "ept": "chiros", "hyp": "chiros", "min": "chiros",
    "myo": "chiros", "nyc": "chiros", "pip": "chiros", "ple": "chiros",
    "rhi": "chiros", "tad": "chiros", "ves": "chiros",
    # Orthoptères & insectes
    "tet": "orthos", "gry": "orthos", "cic": "orthos", "oec": "orthos",
    "pho": "orthos", "rus": "orthos", "mec": "orthos", "con": "orthos",
    "lep": "orthos", "ypo": "orthos", "pla": "orthos", "dec": "orthos",
    "ana": "orthos", "oed": "orthos", "isp": "orthos",
    # Micromammifères
    "mus": "micromam", "apo": "micromam", "sor": "micromam", "cro": "micromam",
    "eli": "micromam", "glis": "micromam",
    # Oiseaux
    "luc": "oiseaux", "tur": "oiseaux", "ery": "oiseaux", "tyt": "oiseaux",
    "str": "oiseaux", "ath": "oiseaux", "cap": "oiseaux", "cot": "oiseaux",
}

# Codes spéciaux (non conformes au format 6 lettres)
SPECIAL: dict[str, str] = {
    "noise": "noise",
    "bruit": "noise",
    "chirosp": "chiros", "chiro_sp": "chiros", "chirop": "chiros",
    "pipsp": "chiros", "myosp": "chiros", "plesp": "chiros",
    "rhisp": "chiros", "nycsp": "chiros",
    "bird": "oiseaux", "aviaria": "oiseaux",
    "rodentia": "micromam", "rodsp": "micromam", "micromam": "micromam",
    "orthopt": "orthos", "orthop": "orthos",
}


# ---------------------------------------------------------------------------
# Chargement CSV officiel
# ---------------------------------------------------------------------------

_DEFAULT_CSV = resource_path("SpeciesListComplete.csv")

# Cache : {code_lower: (fine_group, scientific_name, common_name_fr)}
_OFFICIAL_TABLE: dict[str, tuple[str, str, str]] = {}
_TABLE_LOADED = False


def _load_official_table(path: Path = _DEFAULT_CSV) -> None:
    """Charge la table officielle MNHN (754 taxons).

    Robuste à l'encodage et au délimiteur : les CSV MNHN circulent en
    UTF-8, UTF-8-BOM ou cp1252, séparés par ';' ou ','. On essaye plusieurs
    combinaisons et on logue une ALERTE si la table reste vide (sinon la
    classification dégrade silencieusement de 754 taxons à ~40 préfixes).
    """
    global _TABLE_LOADED, _OFFICIAL_TABLE
    if _TABLE_LOADED:
        return
    _TABLE_LOADED = True
    if not path.is_file():
        import logging as _log
        _log.warning("taxons : CSV officiel introuvable (%s) — "
                      "classification en mode fallback préfixe uniquement.", path)
        return

    import logging as _log

    # Sniff du délimiteur sur la 1re ligne, fallback ';' puis ','
    def _try_load(encoding: str) -> int:
        n = 0
        with path.open("r", encoding=encoding, newline="") as f:
            sample = f.readline()
            f.seek(0)
            delim = ";" if sample.count(";") >= sample.count(",") else ","
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                code = (row.get("Esp") or "").strip()
                if not code:
                    continue
                _OFFICIAL_TABLE[code.lower()] = (
                    (row.get("Group") or "").strip().lower(),
                    (row.get("Scientific name") or "").strip(),
                    (row.get("NomFR") or "").strip(),
                )
                n += 1
        return n

    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            _OFFICIAL_TABLE.clear()
            n = _try_load(enc)
            if n > 0:
                return  # succès
        except (UnicodeDecodeError, csv.Error):
            continue
        except OSError:
            break

    if not _OFFICIAL_TABLE:
        _log.warning("taxons : CSV officiel illisible ou colonnes inattendues "
                      "(%s) — classification en mode fallback préfixe.", path)


def reload_official_table(path: Path | None = None) -> int:
    """Force le rechargement du CSV. Retourne le nb de taxons chargés."""
    global _TABLE_LOADED, _OFFICIAL_TABLE
    _TABLE_LOADED = False
    _OFFICIAL_TABLE = {}
    _load_official_table(path or _DEFAULT_CSV)
    return len(_OFFICIAL_TABLE)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def classify_taxon(taxon: str | None) -> str:
    """Retourne le groupe métier (chiros/orthos/micromam/oiseaux/noise/unknown)."""
    if taxon is None:
        return "unknown"
    s = str(taxon).strip().lower()
    if not s:
        return "unknown"

    _load_official_table()

    if s in _OFFICIAL_TABLE:
        fine = _OFFICIAL_TABLE[s][0]
        return FINE_TO_BUSINESS.get(fine, "unknown")

    if s in SPECIAL:
        return SPECIAL[s]

    if len(s) >= 3 and s[:3] in FALLBACK_PREFIX:
        return FALLBACK_PREFIX[s[:3]]

    return "unknown"


def lookup_taxon(taxon: str | None) -> dict:
    """Retourne un dict enrichi pour diagnostic / UI :
    {code, group, fine_group, scientific_name, common_name_fr, source}."""
    out = {
        "code": taxon,
        "group": "unknown",
        "fine_group": None,
        "scientific_name": None,
        "common_name_fr": None,
        "source": "none",
    }
    if taxon is None:
        return out
    s = str(taxon).strip().lower()
    if not s:
        return out

    _load_official_table()

    if s in _OFFICIAL_TABLE:
        fine, sci, fr = _OFFICIAL_TABLE[s]
        out["fine_group"] = fine
        out["scientific_name"] = sci
        out["common_name_fr"] = fr
        out["group"] = FINE_TO_BUSINESS.get(fine, "unknown")
        out["source"] = "official"
        return out

    if s in SPECIAL:
        out["group"] = SPECIAL[s]
        out["source"] = "special"
        return out

    if len(s) >= 3 and s[:3] in FALLBACK_PREFIX:
        out["group"] = FALLBACK_PREFIX[s[:3]]
        out["source"] = f"prefix:{s[:3]}"
        return out

    return out


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

    ap = argparse.ArgumentParser(description="Classification des taxons Tadarida.")
    ap.add_argument("taxons", nargs="*", help="codes à classer (défaut : stats globales)")
    ap.add_argument("--csv", type=Path, default=None, help="chemin CSV alternatif")
    args = ap.parse_args()

    if args.csv:
        reload_official_table(args.csv)
    else:
        _load_official_table()

    print(f"Taxons officiels chargés : {len(_OFFICIAL_TABLE)}")
    if args.taxons:
        print()
        for t in args.taxons:
            info = lookup_taxon(t)
            print(f"  {t:10s} → {info['group']:10s}  ({info['source']})  "
                  f"{info['scientific_name'] or ''}  {info['common_name_fr'] or ''}")
        return 0

    # Stats par groupe métier
    from collections import Counter
    c = Counter(FINE_TO_BUSINESS.get(fine, "unknown")
                for fine, _, _ in _OFFICIAL_TABLE.values())
    print("\nRépartition par groupe métier :")
    for g, n in c.most_common():
        print(f"  {g:10s} {n:4d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
