#!/usr/bin/env python3
"""
build_activity_ref.py — régénère le référentiel d'activité distillé embarqué
(``activity_ref_PF.csv``) à partir des fichiers sources Team-Chiro.

Le référentiel embarqué est un SNAPSHOT reproductible : on ne l'édite jamais à la
main, on relance ce script quand Team-Chiro publie une mise à jour.

Sources (à télécharger depuis
https://croemer3.wixsite.com/teamchiro/reference-scales-of-activity) :
  * le national toutes-saisons ``refPF_Total_<date>.csv`` (Bas et al. 2020) ;
  * l'archive ZIP des déclinaisons saison × (national / région / habitat).

On ne distille QUE : national (toutes-saisons + 3 saisons) + 13 régions
métropolitaines + habitats grossiers. On IGNORE volontairement altitude, domaines
biogéographiques et habitats fins CLC (nécessiteraient GPS/DEM/raster, faible
valeur ajoutée). Colonnes de sortie : ``code;referentiel;saison;q25;q75;q98;nbocc;confiance``.

Usage :
    python build_activity_ref.py <refPF_Total.csv> <declinaisons.zip> [sortie.csv]

Licence des données : Bas, Kerbiriou, Roemer & Julien (2020) — libre d'usage avec
citation obligatoire. On ne redistribue que les seuils chiffrés (des faits).
"""

from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from pathlib import Path

# Régions métropolitaines : noms EXACTEMENT tels qu'ils apparaissent dans les
# noms de fichiers du ZIP (sans accents/apostrophes) — servent de clé `region:`.
REGIONS = {
    "Auvergne-Rhone-Alpes", "Bourgogne-Franche-Comte", "Bretagne",
    "Centre-Val de Loire", "Corse", "Grand-Est", "Hauts-de-France",
    "Ile-de-France", "Normandie", "Nouvelle Aquitaine", "Occitanie",
    "Pays de la Loire", "Provence-Alpes-Cote dAzur",
}
# Habitats grossiers retenus (choix manuel réaliste dans un menu déroulant).
HABITATS = {
    "Foret", "Agricole", "Urbain", "Riviere",
    "Agricole-Foret", "Agricole-Urbain", "Foret-Urbain",
}
SAISON_MAP = {"Printemps": "printemps", "Ete": "ete", "Automne": "automne"}

_OUT_COLS = ["code", "referentiel", "saison", "q25", "q75", "q98", "nbocc", "confiance"]


def _distill_rows(reader) -> list[dict]:
    """Extrait (Espece, Q25, Q75, Q98, nbocc, Confiance) d'un CSV source ;-délimité."""
    out = []
    for r in reader:
        code = (r.get("Espece") or "").strip()
        if not code or not r.get("Q25"):
            continue
        out.append({
            "code": code, "q25": r["Q25"], "q75": r["Q75"], "q98": r["Q98"],
            "nbocc": r.get("nbocc") or "", "confiance": (r.get("Confiance") or "").strip(),
        })
    return out


def _emit(rows, referentiel, saison, sink):
    for r in rows:
        sink.append({**r, "referentiel": referentiel, "saison": saison})


def build(total_csv: Path, zip_path: Path) -> list[dict]:
    combined: list[dict] = []

    # 1. National toutes-saisons (Bas et al. 2020)
    with open(total_csv, encoding="utf-8", errors="replace") as fh:
        _emit(_distill_rows(csv.DictReader(fh, delimiter=";")),
              "national", "toutes", combined)

    # 2. Déclinaisons du ZIP : refPF_<Saison>_<Contexte>_<date>.csv
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            base = Path(name).name
            m = re.match(r"refPF_([^_]+)_(.+?)_(\d{4}-\d{2}-\d{2})\.csv$", base)
            if not m:
                continue
            saison_raw, contexte = m.group(1), m.group(2)
            saison = SAISON_MAP.get(saison_raw)
            if saison is None:
                continue
            if contexte == "Total":
                referentiel = "national"
            elif contexte in REGIONS:
                referentiel = f"region:{contexte}"
            elif contexte in HABITATS:
                referentiel = f"habitat:{contexte}"
            else:
                continue   # altitude / biogéo / CLC fin : ignorés
            text = z.read(name).decode("utf-8", "replace")
            _emit(_distill_rows(csv.DictReader(io.StringIO(text), delimiter=";")),
                  referentiel, saison, combined)
    return combined


def write_csv(rows, out_path: Path):
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write("# Referentiel d'activite Vigie-Chiro Point Fixe (contacts/nuit)\n")
        f.write("# Source : Bas Y, Kerbiriou C, Roemer C & Julien JF (2020) "
                "Bat reference scale of activity levels (Team-Chiro / MNHN)\n")
        f.write("# https://croemer3.wixsite.com/teamchiro/reference-scales-of-activity "
                "- libre d'usage avec citation obligatoire\n")
        f.write("# national toutes-saisons = 2020 ; saisons/regions/habitats = 2023 ; "
                "genere par build_activity_ref.py\n")
        f.write("# Classes : Faible <Q25 | Moyenne Q25-Q75 | Forte Q75-Q98 | "
                "Tres forte >=Q98\n")
        w = csv.DictWriter(f, fieldnames=_OUT_COLS, delimiter=";")
        w.writeheader()
        w.writerows(rows)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    total_csv, zip_path = Path(argv[1]), Path(argv[2])
    out_path = Path(argv[3]) if len(argv) > 3 else Path(__file__).with_name("activity_ref_PF.csv")
    rows = build(total_csv, zip_path)
    write_csv(rows, out_path)
    refs = sorted({r["referentiel"] for r in rows})
    print(f"[OK] {len(rows)} lignes, {len(refs)} referentiels -> {out_path}")
    print("     referentiels :", ", ".join(refs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
