"""
activity_reference.py — interprétation en NIVEAUX D'ACTIVITÉ des contacts/nuit
par espèce, d'après le référentiel Vigie-Chiro Point Fixe.

Référentiel : Bas, Kerbiriou, Roemer & Julien (2020), *Bat reference scale of
activity levels* (Team-Chiro / MNHN), en **contacts/nuit**, sur Tadarida,
protocole Point Fixe. Valeurs distillées dans ``activity_ref_PF.csv``
(``code;referentiel;saison;q25;q75;q98;nbocc;confiance``), régénérable via
``build_activity_ref.py``. Déclinaisons : national (toutes-saisons + 3 saisons),
13 régions métropolitaines, habitats grossiers.

Méthode (Haquart 2013, reprise MNHN) : on situe le nombre de contacts d'une nuit
dans la distribution de référence de l'espèce, découpée en 4 classes ::

    Faible  < Q25  |  Moyenne  Q25–Q75  |  Forte  Q75–Q98  |  Très forte ≥ Q98

Le contexte (saison / région / habitat) est choisi avec une **chaîne de repli** :
déclinaison la plus spécifique FIABLE → national saisonnier → national toutes-saisons.
On ne descend jamais vers un seuil peu fiable si un seuil fiable plus général existe.

⚠️ GARDE-FOUS (à afficher, jamais omettre) :
  * détectabilité très variable entre espèces → on ne compare JAMAIS des contacts
    entre espèces ; on raisonne espèce par espèce ;
  * une classe d'activité **n'est pas** un niveau d'enjeu de conservation ;
  * valable **sous conditions de protocole** (matériel conforme, micro < 6 m,
    métropole, T°min > 6 °C, pluie 24 h < 9 mm, bonne saison) ;
  * seuils peu fiables pour les contextes sous-échantillonnés (colonne ``confiance``).

Logique PURE (aucune GUI) → testable.
"""

from __future__ import annotations

import csv
from pathlib import Path

CLASS_FAIBLE = "Faible"
CLASS_MOYENNE = "Moyenne"
CLASS_FORTE = "Forte"
CLASS_TRES_FORTE = "Très forte"
CLASSES_ORDER = (CLASS_FAIBLE, CLASS_MOYENNE, CLASS_FORTE, CLASS_TRES_FORTE)

CITATION = ("Bas, Kerbiriou, Roemer & Julien 2020 — référentiel Vigie-Chiro "
            "Point Fixe (contacts/nuit)")
UNITE = "contacts/nuit"

_DEFAULT_REF = Path(__file__).with_name("activity_ref_PF.csv")
_CONFIANCE_FIABLE = {"tres bonne", "bonne"}

# --- Régions métropolitaines : département (2 premiers chiffres du n° site
# Tadarida) → nom de région tel qu'il apparaît dans le référentiel. Pas de GPS.
_REGION_DEPTS = {
    "Auvergne-Rhone-Alpes": "01 03 07 15 26 38 42 43 63 69 73 74",
    "Bourgogne-Franche-Comte": "21 25 39 58 70 71 89 90",
    "Bretagne": "22 29 35 56",
    "Centre-Val de Loire": "18 28 36 37 41 45",
    "Corse": "2A 2B 20",
    "Grand-Est": "08 10 51 52 54 55 57 67 68 88",
    "Hauts-de-France": "02 59 60 62 80",
    "Ile-de-France": "75 77 78 91 92 93 94 95",
    "Normandie": "14 27 50 61 76",
    "Nouvelle Aquitaine": "16 17 19 23 24 33 40 47 64 79 86 87",
    "Occitanie": "09 11 12 30 31 32 34 46 48 65 66 81 82",
    "Pays de la Loire": "44 49 53 72 85",
    "Provence-Alpes-Cote dAzur": "04 05 06 13 83 84",
}
REGION_BY_DEPT = {d: reg for reg, ds in _REGION_DEPTS.items() for d in ds.split()}

# Habitats grossiers proposables à l'utilisateur (menu déroulant « milieu dominant »).
HABITATS = ("Foret", "Agricole", "Urbain", "Riviere",
            "Agricole-Foret", "Agricole-Urbain", "Foret-Urbain")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def region_for_dept(dept) -> str | None:
    """Nom de région à partir d'un n° de département (str/int). None si inconnu.
    Accepte '1', '01', 1, '2A'… (Corse : 2A/2B/20)."""
    if dept is None:
        return None
    s = str(dept).strip().upper()
    if s.isdigit():
        s = s.zfill(2)[:2]
    return REGION_BY_DEPT.get(s)


def region_for_site(n_site_tadarida) -> str | None:
    """Région depuis le n° de site Tadarida (6 chiffres, 2 premiers = département)."""
    s = str(n_site_tadarida or "").strip()
    return region_for_dept(s[:2]) if len(s) >= 2 else None


def season_for_date(dt) -> str:
    """Sous-période phénologique Vigie-Chiro d'une date (datetime/date), ou
    'toutes' hors des trois fenêtres (nuit hivernale, hors protocole)."""
    if dt is None:
        return "toutes"
    md = (dt.month, dt.day)
    if (4, 1) <= md <= (6, 15):
        return "printemps"
    if (6, 16) <= md <= (8, 31):
        return "ete"
    if (9, 1) <= md <= (11, 15):
        return "automne"
    return "toutes"


def load_reference(path=None) -> dict:
    """Charge le référentiel : ``{(referentiel, saison, code_lower): row}``.

    ``row`` = ``{q25, q75, q98, nbocc, confiance}``. Ignore les commentaires (#).
    Renvoie ``{}`` si absent/illisible (dégradation propre)."""
    path = Path(path) if path else _DEFAULT_REF
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
    except OSError:
        return {}
    ref: dict[tuple, dict] = {}
    for r in csv.DictReader(lines, delimiter=";"):
        code = (r.get("code") or "").strip().lower()
        refl = (r.get("referentiel") or "").strip()
        sais = (r.get("saison") or "").strip()
        q25, q75, q98 = _f(r.get("q25")), _f(r.get("q75")), _f(r.get("q98"))
        if not code or not refl or None in (q25, q75, q98):
            continue
        ref[(refl, sais, code)] = {
            "q25": q25, "q75": q75, "q98": q98,
            "nbocc": _f(r.get("nbocc")),
            "confiance": (r.get("confiance") or "").strip(),
        }
    return ref


def classify(n_contacts, row) -> str | None:
    """Classe d'activité de ``n_contacts`` selon une ligne de référence (ou None)."""
    if not row:
        return None
    n = n_contacts
    if n < row["q25"]:
        return CLASS_FAIBLE
    if n < row["q75"]:
        return CLASS_MOYENNE
    if n < row["q98"]:
        return CLASS_FORTE
    return CLASS_TRES_FORTE


def _reliable(row) -> bool:
    return (row.get("confiance") or "").strip().lower() in _CONFIANCE_FIABLE


def _fallback_chain(saison, region, habitat):
    """Ordre d'essai des (referentiel, saison), du plus spécifique au national."""
    chain = []
    if habitat:
        chain.append((f"habitat:{habitat}", saison))
    if region:
        chain.append((f"region:{region}", saison))
    chain.append(("national", saison))
    if saison != "toutes":
        chain.append(("national", "toutes"))
    return chain


def activity_for(code, n_contacts, reference, *, saison="toutes",
                 region=None, habitat=None) -> dict | None:
    """Interprète les contacts d'une espèce via la chaîne de repli.

    Retourne ``{classe, q25, q75, q98, nbocc, confiance, fiable, referentiel,
    saison}`` (le référentiel/saison RÉELLEMENT utilisés, pour la traçabilité),
    ou ``None`` si l'espèce est absente de tout référentiel candidat.

    On retient la 1re déclinaison **fiable** ; à défaut, la 1re qui existe (avec
    ``fiable=False``) — jamais un seuil peu fiable si un fiable plus général existe.
    """
    code_l = (code or "").strip().lower()
    chain = _fallback_chain(saison, region, habitat)

    def _pack(row, refl, sais):
        return {
            "classe": classify(n_contacts, row),
            "q25": row["q25"], "q75": row["q75"], "q98": row["q98"],
            "nbocc": row["nbocc"], "confiance": row["confiance"],
            "fiable": _reliable(row), "referentiel": refl, "saison": sais,
        }

    first_existing = None
    for refl, sais in chain:
        row = reference.get((refl, sais, code_l))
        if not row:
            continue
        if first_existing is None:
            first_existing = _pack(row, refl, sais)
        if _reliable(row):
            return _pack(row, refl, sais)
    return first_existing


def annotate_synthesis(synthesis: dict, reference: dict, *, saison="toutes",
                       region=None, habitat=None) -> dict:
    """Ajoute à chaque espèce **chiro** de la synthèse un champ ``activite`` (ou
    None). N'ajoute rien aux groupes non-chiros. Renvoie la synthèse (mutée)."""
    for sp in synthesis.get("species", []):
        if sp.get("groupe") != "chiros":
            sp.setdefault("activite", None)
            continue
        sp["activite"] = activity_for(
            sp.get("taxon"), sp.get("n_contacts", 0), reference,
            saison=saison, region=region, habitat=habitat)
    return synthesis
