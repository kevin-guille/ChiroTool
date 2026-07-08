"""
sync_state.py — logique PURE de synchronisation des identifications observateur
avec le serveur Vigie-Chiro (aucune dépendance GUI → testable unitairement).

Une identification locale (``observateur_taxon`` + ``observateur_probabilite``)
peut être dans l'un de ces états vis-à-vis du serveur :

  * ``pending``    : validée localement, jamais envoyée
  * ``synced``     : envoyée, identique à la valeur mémorisée côté serveur
  * ``modified``   : modifiée depuis le dernier envoi → à ré-envoyer
  * ``to_retract`` : vidée localement après avoir été envoyée (l'identification
                     reste sur le serveur — une donnée ne se supprime pas côté
                     client ; on affiche juste un avertissement visible)
  * ``error``      : dernier envoi en échec (posé par le worker d'envoi)

Règle métier (imposée par le protocole/API) : une identification n'est
**envoyable que si elle porte À LA FOIS un taxon ET une confiance** (le backend
exige les deux champs ensemble).

La clé de synchro d'une observation est ``"<donnee_id>#<obs_index>"`` (l'index
NATIF 0-based côté serveur, cf. sidecar produit à l'export).
"""

from __future__ import annotations

SYNC_PENDING = "pending"
SYNC_SYNCED = "synced"
SYNC_MODIFIED = "modified"
SYNC_TO_RETRACT = "to_retract"
SYNC_ERROR = "error"


def is_sendable(taxon, conf) -> bool:
    """Une identification est envoyable ssi elle a un taxon ET une confiance."""
    return bool(taxon) and bool(conf)


def next_sync_state(local_taxon, local_conf, record) -> str | None:
    """Machine à états PURE de synchro d'une observation.

    ``record`` = dict persisté (``{state, pushed_taxon, pushed_conf, ...}``) ou
    ``None``/vide si l'observation n'a jamais été envoyée.

    Retourne le nouvel état, ou ``None`` si l'observation n'a **rien** à
    synchroniser (jamais validée de façon envoyable ET jamais envoyée) — dans ce
    cas l'appelant retire toute pastille.

    Déterministe et **bidirectionnel** : si l'utilisateur remet exactement la
    valeur déjà envoyée, l'état revient de ``modified`` à ``synced``.
    """
    rec = record or {}
    pushed_taxon = rec.get("pushed_taxon")
    pushed_conf = rec.get("pushed_conf")
    was_pushed = bool(pushed_taxon)
    has_local = is_sendable(local_taxon, local_conf)

    if not was_pushed:
        return SYNC_PENDING if has_local else None
    # Déjà envoyée au moins une fois côté serveur.
    if not has_local:
        # Vidée (ou rendue non-envoyable) après un envoi → reste sur le serveur.
        return SYNC_TO_RETRACT
    if (str(local_taxon), str(local_conf)) == (str(pushed_taxon), str(pushed_conf)):
        return SYNC_SYNCED
    return SYNC_MODIFIED


def _num(v):
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def _match_key(nom, temps_debut, temps_fin=None):
    """Clé d'appariement ligne↔entrée sidecar, tolérante aux types.

    Inclut ``temps_fin`` en plus de ``temps_debut`` : deux contacts d'un même WAV
    peuvent partager le même ``temps_debut`` (ou l'avoir absent) mais diffèrent
    sur leur ``temps_fin`` → les garde individuellement appariables.
    """
    nom_s = str(nom or "").strip().lower()
    if nom_s.endswith(".wav"):
        nom_s = nom_s[:-4]
    return (nom_s, _num(temps_debut), _num(temps_fin))


def build_row_key_map(rows, col_idx, entries):
    """Associe chaque ligne (par son index) à sa clé serveur
    ``"<donnee_id>#<obs_index>"`` via ``(nom_fichier, temps_debut, temps_fin)`` —
    jamais par numéro de ligne (robuste aux lignes vides/trous).

    **Sécurité anti-corruption** : si deux observations distinctes partagent la
    même clé (collision → index serveur ambigu), on les EXCLUT du mapping (elles
    deviennent non-envoyables) plutôt que d'écrire au mauvais index côté serveur.

    Retourne ``(row_keys, n_unmapped)`` où ``row_keys`` = ``{row_idx: key}``.
    Fonction PURE / testable.
    """
    ci = col_idx or {}
    fi = ci.get("nom du fichier")
    ti = ci.get("temps_debut")
    tf = ci.get("temps_fin")
    if fi is None or ti is None or not entries:
        return {}, len(rows)

    # 1re passe : construire le lookup ET compter les collisions de clé.
    lookup: dict = {}
    counts: dict = {}
    for e in entries:
        did = e.get("donnee_id")
        oidx = e.get("obs_index")
        if did is None or oidx is None:
            continue
        k = _match_key(e.get("nom_fichier"), e.get("temps_debut"), e.get("temps_fin"))
        counts[k] = counts.get(k, 0) + 1
        lookup[k] = f"{did}#{oidx}"
    # Retirer toute clé ambiguë (≥2 observations) : mieux vaut « non mappé » que
    # « mappé au mauvais index ».
    for k, n in counts.items():
        if n > 1:
            lookup.pop(k, None)

    row_keys: dict[int, str] = {}
    n_unmapped = 0
    for idx, r in enumerate(rows):
        nom = r[fi] if fi < len(r) else None
        td = r[ti] if ti < len(r) else None
        tfin = r[tf] if (tf is not None and tf < len(r)) else None
        key = lookup.get(_match_key(nom, td, tfin))
        if key is None:
            n_unmapped += 1
        else:
            row_keys[idx] = key
    return row_keys, n_unmapped
