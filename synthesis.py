"""
synthesis.py — récapitulatif par espèce d'une nuit d'observations.

Compte les contacts par **espèce retenue** (taxon observateur si la ligne a été
validée, sinon taxon Tadarida) et fournit les totaux, à partir des lignes d'un
tableur d'observations Vigie-Chiro (11 colonnes standard).

``compute_mnhn_synthesis`` relit un fichier ``_Vu`` produit dans le logiciel externe
(bandes de confiance Tadarida, seuil couvrant 75 % du pool, issue #7 / SPEC P8).
Cette relecture est distincte de la procédure de validation Vigie-Chiro et de
``validated_only`` (lignes écoutées seulement).

Logique pure : pas d'I/O, pas de GUI → testable unitairement (voir
tests/test_core.py :: TestSynthesis / TestMnhnSynthesis).
"""

from __future__ import annotations

from taxons import classify_taxon


def _col_index(headers: list) -> dict[str, int]:
    """Mappe les colonnes métier utiles vers leur indice (insensible à la casse)."""
    lower = [str(h).lower().strip() for h in headers]
    idx: dict[str, int] = {}
    for wanted in ("nom du fichier", "tadarida_taxon", "observateur_taxon",
                    "tadarida_probabilite", "observateur_probabilite"):
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


def _tadarida_proba(row: list, ci: dict[str, int]) -> float | None:
    """Probabilité Tadarida (0–1) si lisible, sinon None."""
    i = ci.get("tadarida_probabilite")
    if i is None or i >= len(row):
        return None
    v = row[i]
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_night_synthesis(headers: list, rows: list, *,
                            validated_only: bool = False,
                            min_tadarida_proba: float | None = None,
                            chiros_only: bool = False) -> dict:
    """Récapitulatif par espèce d'une nuit.

    ``validated_only`` : ne compter que les contacts **validés par l'observateur**
    (colonne ``observateur_taxon`` renseignée) et ignorer les identifications
    automatiques Tadarida non revues. Ce n'est **pas** l'interprétation
    d’un ``_Vu`` produit dans le logiciel externe (voir ``compute_mnhn_synthesis``).

    ``min_tadarida_proba`` : si défini (0–1), ignore les contacts non validés
    dont la proba Tadarida est absente ou strictement inférieure au seuil
    (issue #3 / synthèse non validée). Les lignes déjà validées observateur
    passent toujours.

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

    thr = None
    if min_tadarida_proba is not None:
        try:
            thr = float(min_tadarida_proba)
        except (TypeError, ValueError):
            thr = None

    per: dict[str, dict] = {}
    for row in rows:
        if not row:
            continue
        taxon, validated = retained_taxon(row, ci)
        if not taxon:
            continue
        if validated_only and not validated:
            continue                              # ignore les non-validés (Tadarida seul)
        if chiros_only and classify_taxon(taxon) != "chiros":
            continue
        if thr is not None and not validated:
            p = _tadarida_proba(row, ci)
            if p is None or p < thr:
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


# Relecture d’un _Vu produit dans le logiciel externe (issue #7)

_MNHN_N_BINS = 10


def _cell(row: list, ci: dict[str, int], key: str):
    i = ci.get(key)
    if i is None or i >= len(row):
        return None
    return row[i]


def _taxon_str(value) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def mnhn_proba_bin(value) -> int | None:
    """Bande exclusive 0..9 : ``[k/10, (k+1)/10)``, ``k=9`` pour ``p >= 0.9``.

    ``None`` si la proba est absente, illisible, négative ou non finie.
    ``p >= 1`` est ramené à la bande 0.9 (graphe du logiciel externe ``>= 0.90``).
    """
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if not value:
            return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if x != x or x < 0.0 or x == float("inf"):
        return None
    if x >= 1.0:
        return 9
    return min(9, int(x * 10.0 + 1e-12))


def mnhn_f75(bin_counts: list[int]) -> int | None:
    """Plus haut ``k`` tel que le cumul ``p >= k/10`` atteint 75 % du pool.

    Comparaison entière ``4 * cumul >= 3 * n`` (seuil inclus). ``None`` si
    le pool est vide. Le cumul part des bandes hautes (0.9 → 0.0).
    """
    if len(bin_counts) != _MNHN_N_BINS:
        raise ValueError("bin_counts must have 10 entries")
    n = sum(bin_counts)
    if n <= 0:
        return None
    cumul = 0
    for k in range(9, -1, -1):
        cumul += bin_counts[k]
        if 4 * cumul >= 3 * n:
            return k
    return 0


def _empty_species_acc() -> dict:
    return {
        "bins": [0] * _MNHN_N_BINS,
        "val_bins": set(),
        "n_val": 0,
        "n_forced": 0,
        "n_direct": 0,
        "files": set(),
        "files_pool": [set() for _ in range(_MNHN_N_BINS)],
        "files_direct": set(),
        "n_pool_invalid": 0,
    }


def _mnhn_accumulate(headers: list, rows: list
                      ) -> tuple[set[str], dict[str, dict], dict[str, int]]:
    """Premier passage de relecture du _Vu : espèces écoutées + accumulateurs par taxon."""
    ci = _col_index(headers)
    t_file = ci.get("nom du fichier")
    per: dict[str, dict] = {}

    def acc_for(taxon: str) -> dict:
        d = per.get(taxon)
        if d is None:
            d = _empty_species_acc()
            per[taxon] = d
        return d

    listened: set[str] = set()
    for row in rows:
        if not row:
            continue
        tad = _taxon_str(_cell(row, ci, "tadarida_taxon"))
        obs = _taxon_str(_cell(row, ci, "observateur_taxon"))
        fn = ""
        if t_file is not None and t_file < len(row) and row[t_file]:
            fn = str(row[t_file])
        pbin = mnhn_proba_bin(_cell(row, ci, "tadarida_probabilite"))

        if obs:
            listened.add(obs)
            d_obs = acc_for(obs)
            d_obs["n_val"] += 1
            if fn:
                d_obs["files_direct"].add(fn)

        if tad and obs and obs != tad:
            acc_for(obs)["n_forced"] += 1
            continue

        if tad:
            d = acc_for(tad)
            if pbin is None:
                d["n_pool_invalid"] += 1
                if obs == tad:
                    d["n_direct"] += 1
                continue
            d["bins"][pbin] += 1
            if fn:
                d["files_pool"][pbin].add(fn)
            if obs == tad:
                d["val_bins"].add(pbin)
            continue

        if obs:
            acc_for(obs)["n_direct"] += 1
    return listened, per, ci


def _mnhn_keep_rules(listened: set[str], per: dict[str, dict]) -> dict[str, dict]:
    """Pour chaque espèce écoutée : ``reached_75`` et bandes concordantes."""
    rules: dict[str, dict] = {}
    for taxon in listened:
        d = per[taxon]
        bins = d["bins"]
        n_pool = sum(bins)
        f75 = mnhn_f75(bins) if n_pool else None
        val_bins = d["val_bins"]
        rules[taxon] = {
            "reached_75": f75 is not None and f75 in val_bins,
            "val_bins": val_bins,
        }
    return rules


def iter_mnhn_contacts(headers: list, rows: list):
    """Yield ``(row, taxon)`` pour chaque contact retenu lors de la relecture du ``_Vu``.

    Même règle que ``compute_mnhn_synthesis`` : pool Tadarida filtré par
    bandes de confiance, corrections forcées, espèces absentes de Tadarida.
    Sert aux graphes Activité (horodatage du nom de fichier).
    """
    listened, per, ci = _mnhn_accumulate(headers, rows)
    rules = _mnhn_keep_rules(listened, per)
    for row in rows:
        if not row:
            continue
        tad = _taxon_str(_cell(row, ci, "tadarida_taxon"))
        obs = _taxon_str(_cell(row, ci, "observateur_taxon"))
        pbin = mnhn_proba_bin(_cell(row, ci, "tadarida_probabilite"))
        if tad and obs and obs != tad:
            if obs in rules:
                yield row, obs
            continue
        if tad:
            rule = rules.get(tad)
            if rule is None:
                continue
            if pbin is None:
                if obs == tad:
                    yield row, tad
                continue
            if rule["reached_75"] or pbin in rule["val_bins"]:
                yield row, tad
            continue
        if obs in rules:
            yield row, obs


def compute_mnhn_synthesis(headers: list, rows: list, *,
                           chiros_only: bool = False) -> dict:
    """Synthèse par relecture d’un ``_Vu`` produit dans le logiciel externe (SPEC P8).

    Calcul à partir d’un ``_Vu`` seul, distinct de la procédure de validation
    Vigie-Chiro réalisée dans le logiciel externe. Ne pas confondre avec
    ``validated_only`` (lignes écoutées uniquement).

    Pour chaque espèce avec au moins un ``observateur_taxon`` :

    * pool = propositions ``tadarida_taxon`` de ce code, hors corrections
      sortantes (observateur ≠ Tadarida) ;
    * bandes = 10 plages de ``tadarida_probabilite`` (pas le temps) ;
    * F75 = plus haut seuil dont le cumul ``p >= seuil`` couvre 75 % du pool ;
    * si une validation **concordante** (observateur = Tadarida) tombe dans
      la bande F75 : tous les contacts du pool ;
    * sinon : union des bandes exclusives qui contiennent une validation
      concordante (une bande sautée n'est pas comptée) ;
    * correction vers une espèce déjà proposée par Tadarida : +1 après
      extrapolation, sans transférer la proba source ;
    * espèce absente de Tadarida : lignes observateur seulement.

    ``n_valides`` reste le nombre de lignes réellement écoutées. Les
    champs ``reached_75``, ``f75``, ``n_pool``, ``n_forced`` sont des
    diagnostics par espèce. ``tadarida_taxon_autre`` est ignoré.
    """
    listened, per, _ci = _mnhn_accumulate(headers, rows)

    species: list[dict] = []
    by_group: dict[str, int] = {}
    total_contacts = 0
    validated_contacts = 0
    all_files: set[str] = set()

    for taxon in listened:
        d = per[taxon]
        grp = classify_taxon(taxon)
        if chiros_only and grp != "chiros":
            continue
        bins = d["bins"]
        n_pool = sum(bins)
        f75 = mnhn_f75(bins) if n_pool else None
        val_bins: set[int] = d["val_bins"]
        reached = f75 is not None and f75 in val_bins
        files: set[str] = set(d["files_direct"])
        if reached:
            n_extrap = n_pool
            for s in d["files_pool"]:
                files |= s
        else:
            n_extrap = 0
            for k in val_bins:
                n_extrap += bins[k]
                files |= d["files_pool"][k]
        n_contacts = n_extrap + d["n_forced"] + d["n_direct"]
        species.append({
            "taxon": taxon,
            "groupe": grp,
            "n_contacts": n_contacts,
            "n_valides": d["n_val"],
            "n_fichiers": len(files),
            "validated": True,
            "reached_75": reached,
            "f75": None if f75 is None else f75 / 10.0,
            "n_pool": n_pool,
            "n_forced": d["n_forced"],
        })
        by_group[grp] = by_group.get(grp, 0) + n_contacts
        total_contacts += n_contacts
        validated_contacts += d["n_val"]
        all_files |= files

    species.sort(key=lambda s: (-s["n_contacts"], s["taxon"].lower()))
    richesse_chiros = sum(1 for s in species if s["groupe"] == "chiros")
    richesse_totale = sum(1 for s in species if s["groupe"] not in ("noise", "unknown"))
    n_invalid = sum(per[t]["n_pool_invalid"] for t in listened)
    return {
        "species": species,
        "total_contacts": total_contacts,
        "validated_contacts": validated_contacts,
        "total_fichiers": len(all_files),
        "by_group": by_group,
        "richesse_chiros": richesse_chiros,
        "richesse_totale": richesse_totale,
        "method": "mnhn",
        "n_proba_invalides": n_invalid,
    }


def merge_night_syntheses(parts: list[dict]) -> dict:
    """Agrège des synthèses déjà calculées (une par nuit biologique).

    Somme les contacts. Pas de classe d'activité : le référentiel est en
    contacts/nuit. ``reached_75`` du cumul n'a pas de sens (False).
    """
    acc: dict[str, dict] = {}
    validated_contacts = 0
    total_fichiers = 0
    n_invalid = 0
    method = None
    for part in parts:
        if not part:
            continue
        method = part.get("method") or method
        validated_contacts += int(part.get("validated_contacts") or 0)
        total_fichiers += int(part.get("total_fichiers") or 0)
        n_invalid += int(part.get("n_proba_invalides") or 0)
        for s in part.get("species") or []:
            taxon = s.get("taxon") or ""
            if not taxon:
                continue
            d = acc.setdefault(taxon, {
                "taxon": taxon,
                "groupe": s.get("groupe") or classify_taxon(taxon),
                "n_contacts": 0,
                "n_valides": 0,
                "n_fichiers": 0,
                "validated": False,
                "n_pool": 0,
                "n_forced": 0,
            })
            d["n_contacts"] += int(s.get("n_contacts") or 0)
            d["n_valides"] += int(s.get("n_valides") or 0)
            d["n_fichiers"] += int(s.get("n_fichiers") or 0)
            d["validated"] = d["validated"] or bool(s.get("validated"))
            d["n_pool"] += int(s.get("n_pool") or 0)
            d["n_forced"] += int(s.get("n_forced") or 0)

    species = []
    by_group: dict[str, int] = {}
    total_contacts = 0
    for d in acc.values():
        d["reached_75"] = False
        d["f75"] = None
        species.append(d)
        by_group[d["groupe"]] = by_group.get(d["groupe"], 0) + d["n_contacts"]
        total_contacts += d["n_contacts"]
    species.sort(key=lambda s: (-s["n_contacts"], s["taxon"].lower()))
    out = {
        "species": species,
        "total_contacts": total_contacts,
        "validated_contacts": validated_contacts,
        "total_fichiers": total_fichiers,
        "by_group": by_group,
        "richesse_chiros": sum(1 for s in species if s["groupe"] == "chiros"),
        "richesse_totale": sum(
            1 for s in species if s["groupe"] not in ("noise", "unknown")),
        "n_proba_invalides": n_invalid,
    }
    if method:
        out["method"] = method
    return out

