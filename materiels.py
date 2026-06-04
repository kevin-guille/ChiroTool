"""
materiels.py — parc matériel persistant du bureau d'études.

Stocke la liste des enregistreurs du BE (avec marque, modèle, n° de série
physique, modèle et série du micro, hauteur habituelle, etc.) dans un fichier
JSON à côté des préférences utilisateur (``%APPDATA%\\ChiroTool\\materiels.json``
ou ``ChiroTool_data/materiels.json`` en mode portable).

**Pourquoi** : avant cette brique, le wizard session utilisait la ``Feuil2`` du
Suivi Excel 2026 pour résoudre un numéro interne (1..27) vers une série
enregistreur / micro. Deux problèmes :

  1. Tous les BE ne maintiennent pas un Suivi Excel à jour — ou le Suivi peut
     être sur un partage non accessible au moment du traitement.
  2. Le numéro 1..27 est un identifiant **interne** au bureau (convention
     Acer Campestre). Il ne correspond pas à un identifiant Vigie-Chiro :
     seul ce qui finit dans ``configuration.micro0_modele`` côté API est
     "officiel". Il faut donc que le mapping numéro-interne → info-matérielle
     soit fiable et local à l'app.

Ce module est la source de vérité canonique. Le wizard l'interroge en
priorité ; fallback sur Feuil2 si absent, fallback sur saisie manuelle si
le matériel n'est pas répertorié (option « Autre » du dropdown).

Format de fichier (JSON, lisible à la main pour dépannage) :

.. code-block:: json

    {
        "schema_version": 1,
        "materiels": [
            {
                "id": 1,
                "marque": "Wildlife Acoustics",
                "modele": "SM4BAT FS",
                "serie_enr": "S4U04784",
                "micro_modele": "SMX-U1",
                "micro_serie": "U1-12345",
                "hauteur_m": 2.0,
                "stereo": false,
                "micro2_modele": null,
                "micro2_serie": null,
                "notes": "Boîtier rouge, coin atelier"
            }
        ]
    }
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


MATERIELS_FILENAME = "materiels.json"
SCHEMA_VERSION = 1


@dataclass
class Materiel:
    """Un enregistreur du parc du BE.

    ``id`` correspond au numéro interne que l'utilisateur a l'habitude d'écrire
    dans son Suivi. 1..27 est la plage historique Acer Campestre, mais rien
    n'empêche d'aller au-delà (99 max raisonnable).
    """

    id: int
    marque: str | None = None         # ex: "Wildlife Acoustics"
    modele: str | None = None         # ex: "SM4BAT FS"
    serie_enr: str | None = None      # ex: "S4U04784"
    micro_modele: str | None = None   # ex: "SMX-U1"
    micro_serie: str | None = None    # ex: "U1-12345"
    hauteur_m: float | None = 2.0
    stereo: bool = False
    micro2_modele: str | None = None
    micro2_serie: str | None = None
    notes: str | None = None

    def is_empty(self) -> bool:
        """True si aucun champ identifiant n'est renseigné (ligne vide)."""
        return not any([
            self.marque, self.modele, self.serie_enr,
            self.micro_modele, self.micro_serie,
        ])

    def label(self) -> str:
        """Ligne résumée pour affichage dans les dropdowns."""
        parts = [f"#{self.id}"]
        if self.modele:
            parts.append(self.modele)
        elif self.marque:
            parts.append(self.marque)
        if self.serie_enr:
            parts.append(f"({self.serie_enr})")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _materiels_path() -> Path:
    """Emplacement du fichier JSON (partagé avec gui_config)."""
    # Import tardif pour éviter la boucle gui_config ↔ credentials ↔ ...
    from gui_config import config_dir
    return config_dir() / MATERIELS_FILENAME


def load_materiels() -> list[Materiel]:
    """Charge la liste depuis le fichier JSON.

    Retourne [] si le fichier n'existe pas (premier lancement).
    En cas de JSON corrompu, log silencieusement et retourne [].
    """
    p = _materiels_path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict) or "materiels" not in data:
        return []
    known_fields = {f for f in Materiel.__dataclass_fields__}
    out: list[Materiel] = []
    for item in data.get("materiels") or []:
        if not isinstance(item, dict):
            continue
        # Filtre les clés inconnues (forward-compat)
        filtered = {k: v for k, v in item.items() if k in known_fields}
        # id obligatoire
        if "id" not in filtered:
            continue
        try:
            filtered["id"] = int(filtered["id"])
        except (TypeError, ValueError):
            continue
        try:
            m = Materiel(**filtered)
        except (TypeError, ValueError):
            continue
        out.append(m)
    # Tri stable par id pour présentation
    out.sort(key=lambda m: m.id)
    return out


def save_materiels(materiels: list[Materiel], *,
                     allow_clear: bool = False) -> None:
    """Sauvegarde atomique (.tmp + replace) avec garde-fou anti-effacement.

    Si ``materiels`` est vide ET qu'il existait une liste non-vide
    précédemment, on REFUSE l'écriture par défaut. C'est un garde-fou contre
    les écrasements accidentels (PreferencesDialog ouverte sans visiter
    l'onglet matériels, race condition à l'init, etc.). Pour vider
    intentionnellement, passer ``allow_clear=True``.

    Backup automatique avant remplacement : ``materiels.json.bak`` conserve
    l'état précédent, exploitable manuellement si erreur catastrophique.

    Log applicatif (chirotool.log) à chaque save pour traçabilité.
    """
    import logging as _log
    p = _materiels_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    # Lecture de l'existant pour le garde-fou + backup
    existing: list[Materiel] = []
    try:
        existing = load_materiels()
    except Exception:
        pass

    if not materiels and existing and not allow_clear:
        _log.warning(
            "save_materiels : refus d'écraser %d matériel(s) existant(s) "
            "par une liste vide (utiliser allow_clear=True si voulu)",
            len(existing),
        )
        return

    # Backup .bak (rotation simple : un seul fichier conservé)
    if p.is_file():
        try:
            bak = p.with_suffix(p.suffix + ".bak")
            bak.write_bytes(p.read_bytes())
        except Exception:
            pass

    payload = {
        "schema_version": SCHEMA_VERSION,
        "materiels": [asdict(m) for m in materiels],
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(p)
    _log.info("save_materiels : %d matériel(s) écrit(s) dans %s",
              len(materiels), p)


# ---------------------------------------------------------------------------
# Recherche / résolution
# ---------------------------------------------------------------------------

def find_by_id(materiels: list[Materiel], n: int) -> Materiel | None:
    for m in materiels:
        if m.id == n:
            return m
    return None


def find_by_serial(materiels: list[Materiel], serial: str) -> Materiel | None:
    """Cherche par série enregistreur (insensible à la casse + espaces)."""
    if not serial:
        return None
    s = serial.strip().lower()
    for m in materiels:
        if m.serie_enr and m.serie_enr.strip().lower() == s:
            return m
    return None


def next_free_id(materiels: list[Materiel], *, start: int = 1) -> int:
    """Retourne le plus petit id >= start non utilisé."""
    used = {m.id for m in materiels}
    i = start
    while i in used:
        i += 1
    return i


# ---------------------------------------------------------------------------
# CLI de test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ms = load_materiels()
    print(f"{len(ms)} matériels enregistrés dans {_materiels_path()}")
    for m in ms:
        print(f"  {m.label()}  micro={m.micro_modele}  serie_micro={m.micro_serie}")
