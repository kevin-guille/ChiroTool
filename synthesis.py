"""
synthesis.py — récapitulatif par espèce d'une nuit d'observations.

Compte les contacts par **espèce retenue** (taxon observateur si la ligne a été
validée, sinon taxon Tadarida) et fournit les totaux, à partir des lignes d'un
tableur d'observations Vigie-Chiro (11 colonnes standard).

Logique pure : pas d'I/O, pas de GUI → testable unitairement (voir
tests/test_core.py :: TestSynthesis).
"""

from __future__ import annotations

from taxons import classify_taxon


def _col_index(headers: list) -> dict[str, int]:
    """Mappe les colonnes métier utiles vers leur indice (insensible à la casse)."""
    lower = [str(h).lower().strip() for h in headers]
    idx: dict[str, int] = {}
    for wanted in ("nom du fichier", "tadarida_taxon", "observateur_taxon"):
        if wanted in lower:
            idx[wanted] = lower.index(wanted)
    return idx


def retained_taxon(row: list, ci: dict[str, int]) -> tuple[str, bool]:
    """Espèce retenue pour une ligne : ``(taxon, validated)``.

    Priorité au taxon observateur (validation humaine) ; sinon Tadarida.
    ``validated`` = True si l'espèce vient d'une validation observateur.
    Retourne ``("", False)`` si aucune espèce exploitable.
    """
    t_obs = ci.get("observateur_taxon")
    t_tad = ci.get("tadarida_taxon")
    obs = row[t_obs] if (t_obs is not None and t_obs < len(row)) else None
    if obs not in (None, ""):
        return str(obs).strip(), True
    tad = row[t_tad] if (t_tad is not None and t_tad < len(row)) else None
    if tad not in (None, ""):
        return str(tad).strip(), False
    return "", False


def compute_night_synthesis(headers: list, rows: list) -> dict:
    """Récapitulatif par espèce d'une nuit.

    Retour ::

        {
          "species": [                       # trié par n_contacts décroissant
            {"taxon", "groupe", "n_contacts", "n_valides", "n_fichiers", "validated"}, ...
          ],
          "total_contacts": int,             # contacts avec une espèce retenue
          "validated_contacts": int,         # contacts issus d'une validation observateur
          "total_fichiers": int,             # fichiers distincts concernés
          "by_group": {groupe: n_contacts},  # ex. {"chiros": 42, "noise": 7}
          "richesse_chiros": int,            # nb d'espèces chiro distinctes
          "richesse_totale": int,            # nb de taxons distincts (hors noise/unknown)
        }

    « validated_contacts / total_contacts » = « X identifiés (validés) sur Y
    détectés ». Les contacts supprimés au nettoyage ne sont pas dans ``rows``
    (l'xlsx nettoyé ne les contient plus) → naturellement exclus.
    """
    ci = _col_index(headers)
    t_file = ci.get("nom du fichier")

    per: dict[str, dict] = {}
    for row in rows:
        if not row:
            continue
        taxon, validated = retained_taxon(row, ci)
        if not taxon:
            continue
        d = per.setdefault(taxon, {"n": 0, "n_val": 0, "files": set(), "validated": False})
        d["n"] += 1
        if validated:
            d["validated"] = True
            d["n_val"] += 1
        if t_file is not None and t_file < len(row):
            fn = row[t_file]
            if fn:
                d["files"].add(str(fn))

    species: list[dict] = []
    by_group: dict[str, int] = {}
    total_contacts = 0
    validated_contacts = 0
    all_files: set[str] = set()
    for taxon, d in per.items():
        grp = classify_taxon(taxon)
        species.append({
            "taxon": taxon,
            "groupe": grp,
            "n_contacts": d["n"],
            "n_valides": d["n_val"],
            "n_fichiers": len(d["files"]),
            "validated": d["validated"],
        })
        by_group[grp] = by_group.get(grp, 0) + d["n"]
        total_contacts += d["n"]
        validated_contacts += d["n_val"]
        all_files |= d["files"]

    species.sort(key=lambda s: (-s["n_contacts"], s["taxon"].lower()))
    richesse_chiros = sum(1 for s in species if s["groupe"] == "chiros")
    richesse_totale = sum(1 for s in species if s["groupe"] not in ("noise", "unknown"))
    return {
        "species": species,
        "total_contacts": total_contacts,
        "validated_contacts": validated_contacts,
        "total_fichiers": len(all_files),
        "by_group": by_group,
        "richesse_chiros": richesse_chiros,
        "richesse_totale": richesse_totale,
    }
