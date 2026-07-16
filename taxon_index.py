"""
taxon_index.py — index des taxons ACCEPTÉS par l'API Vigie-Chiro (GET /taxons),
pour valider et autocompléter la saisie d'identification observateur.

Distinct de ``taxons.py`` (qui classe les 754 sonotypes Tadarida) : le serveur
n'accepte qu'un **sous-ensemble** (~199 taxons). Un code valide côté Tadarida
peut être refusé à l'envoi → on valide contre CE référentiel-ci.

Snapshot embarqué : ``taxons_vigiechiro.csv`` (``code;libelle``), régénérable
depuis le live. ``resolve_taxon_id`` (client API) reste l'autorité finale au
moment de l'envoi ; cet index sert à guider la saisie **hors-ligne**.

Gère aussi les codes « genre / groupe » (``Plesp`` = Oreillard sp., ``Myosp`` =
Murin sp., ``Pipsp`` = Pipistrelle sp.) : la bonne réponse pour un son incertain
entre deux espèces d'un même genre (cas classique Pleaur/Pleaus).

Logique PURE (aucune GUI) → testable.
"""

from __future__ import annotations

import csv
from pathlib import Path

from resources import resource_path

_DEFAULT = resource_path("taxons_vigiechiro.csv")


def load_taxon_index(path=None) -> dict:
    """Charge ``{code_lower: (code, libelle)}`` depuis le snapshot. ``{}`` si absent."""
    path = Path(path) if path else _DEFAULT
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
    except OSError:
        return {}
    index: dict[str, tuple[str, str]] = {}
    for r in csv.DictReader(lines, delimiter=";"):
        code = (r.get("code") or "").strip()
        if code:
            index[code.lower()] = (code, (r.get("libelle") or "").strip())
    return index


def is_known(code, index) -> bool:
    """Le code est-il accepté par le serveur (présent dans l'index) ?"""
    return (code or "").strip().lower() in index


def canonical_code(code, index) -> str | None:
    """Retourne le code dans sa casse canonique (ou None si inconnu)."""
    row = index.get((code or "").strip().lower())
    return row[0] if row else None


def suggest(query, index, limit: int = 12) -> list[tuple[str, str]]:
    """Suggestions ``(code, libelle)`` pour une saisie partielle.

    Cherche dans le code ET le libellé (nom FR / latin). Priorité : préfixe de
    code > préfixe de libellé > sous-chaîne. Trié, tronqué à ``limit``.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    pref_code, pref_lbl, sub = [], [], []
    for code_l, (code, label) in index.items():
        ll = label.lower()
        if code_l.startswith(q):
            pref_code.append((code, label))
        elif ll.startswith(q):
            pref_lbl.append((code, label))
        elif q in code_l or q in ll:
            sub.append((code, label))
    for bucket in (pref_code, pref_lbl, sub):
        bucket.sort(key=lambda x: x[0].lower())
    return (pref_code + pref_lbl + sub)[:limit]


def genus_code_for(code, index) -> str | None:
    """Code « genre sp. » correspondant à une espèce, s'il existe côté serveur.

    Heuristique : 3 premières lettres du code + ``sp`` (Pleaur → Plesp,
    Pippip → Pipsp, Myodau → Myosp), **validée contre l'index** — on ne renvoie
    un code que s'il existe réellement. Renvoie None si l'espèce n'a pas de code
    genre (genre monospécifique en France, ou déjà un code genre/groupe).
    """
    c = (code or "").strip()
    if len(c) < 4 or c.lower().endswith("sp"):
        return None
    return canonical_code(c[:3] + "sp", index)
