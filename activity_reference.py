"""
activity_reference.py — interprétation en NIVEAUX D'ACTIVITÉ des contacts/nuit
par espèce, d'après le référentiel national Vigie-Chiro Point Fixe.

Référentiel : Bas, Kerbiriou, Roemer & Julien (2020), *Bat reference scale of
activity levels* (Team-Chiro / MNHN), en **contacts/nuit**, sur Tadarida,
protocole Point Fixe — exactement la chaîne de production de ChiroTool. Valeurs
distillées dans ``activity_ref_PF_national.csv`` (code;q25;q75;q98;…).

Méthode (Haquart 2013, reprise MNHN) : on situe le nombre de contacts d'une nuit
dans la distribution de référence de l'espèce, découpée en 4 classes ::

    Faible  < Q25   |   Moyenne  Q25–Q75   |   Forte  Q75–Q98   |   Très forte ≥ Q98

⚠️ GARDE-FOUS (à afficher dans l'UI, jamais omettre) :
  * la détectabilité varie énormément entre espèces → on ne compare JAMAIS des
    contacts entre espèces ; on raisonne espèce par espèce ;
  * une classe d'activité **n'est pas** un niveau d'enjeu de conservation
    (une activité faible ne signifie pas un enjeu faible) ;
  * valable **sous conditions de protocole** (matériel conforme Vigie-Chiro,
    micro < 6 m, métropole, T°min > 6 °C, pluie 24 h < 9 mm, bonne saison) ;
  * seuils peu fiables pour les espèces/contextes sous-échantillonnés (`confiance`).

Logique PURE (aucune GUI, aucune I/O sauf le chargement du CSV) → testable.
"""

from __future__ import annotations

import csv
from pathlib import Path

CLASS_FAIBLE = "Faible"
CLASS_MOYENNE = "Moyenne"
CLASS_FORTE = "Forte"
CLASS_TRES_FORTE = "Très forte"
CLASSES_ORDER = (CLASS_FAIBLE, CLASS_MOYENNE, CLASS_FORTE, CLASS_TRES_FORTE)

CITATION = ("Bas, Kerbiriou, Roemer & Julien 2020 — référentiel national "
            "Vigie-Chiro Point Fixe (contacts/nuit)")
UNITE = "contacts/nuit"

_DEFAULT_REF = Path(__file__).with_name("activity_ref_PF_national.csv")
# La colonne `confiance` du référentiel : au-dessous de ces valeurs, seuils fragiles.
_CONFIANCE_FIABLE = {"tres bonne", "bonne"}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_reference(path=None) -> dict:
    """Charge le référentiel : ``{code_lower: {q25,q75,q98,moy,nbocc,confiance}}``.

    Ignore les lignes de commentaire (``#``). Renvoie ``{}`` si le fichier est
    absent ou illisible (dégradation propre : l'outil marche sans référentiel,
    il n'affiche simplement pas de classe d'activité).
    """
    path = Path(path) if path else _DEFAULT_REF
    ref: dict[str, dict] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
    except OSError:
        return {}
    for row in csv.DictReader(lines, delimiter=";"):
        code = (row.get("code") or "").strip().lower()
        q25, q75, q98 = _f(row.get("q25")), _f(row.get("q75")), _f(row.get("q98"))
        if not code or None in (q25, q75, q98):
            continue
        ref[code] = {
            "q25": q25, "q75": q75, "q98": q98,
            "moy": _f(row.get("moy_si_present")),
            "nbocc": _f(row.get("nbocc")),
            "confiance": (row.get("confiance") or "").strip(),
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


def activity_for(code, n_contacts, reference) -> dict | None:
    """Interprétation complète pour une espèce, ou None si absente du référentiel.

    Retour : ``{classe, q25, q75, q98, moy, nbocc, confiance, fiable}``.
    ``fiable`` = seuil jugé robuste (confiance « bonne »/« très bonne »).
    """
    row = reference.get((code or "").strip().lower())
    if not row:
        return None
    conf = row.get("confiance") or ""
    return {
        "classe": classify(n_contacts, row),
        "q25": row["q25"], "q75": row["q75"], "q98": row["q98"],
        "moy": row["moy"], "nbocc": row["nbocc"],
        "confiance": conf,
        "fiable": conf.strip().lower() in _CONFIANCE_FIABLE,
    }


def annotate_synthesis(synthesis: dict, reference: dict) -> dict:
    """Ajoute à chaque espèce **chiro** de la synthèse un champ ``activite`` (ou
    None). N'ajoute rien aux groupes non-chiros (référentiel non pertinent) et
    aux espèces absentes du référentiel. Renvoie la même synthèse (mutée)."""
    for sp in synthesis.get("species", []):
        if sp.get("groupe") != "chiros":
            sp.setdefault("activite", None)
            continue
        sp["activite"] = activity_for(sp.get("taxon"), sp.get("n_contacts", 0), reference)
    return synthesis
