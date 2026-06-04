"""
vigiechiro_enums.py — listes de valeurs officielles / observées pour l'API.

Deux catégories :

1. **Strictes backend** : enums validés par le schéma Cerberus côté serveur.
   Toute autre valeur sera refusée. Source : Scille/vigiechiro-api/resources.

2. **Observées frontend** : listes proposées dans le formulaire web. Le backend
   accepte n'importe quelle string (champ `configuration` est libre), mais
   pour rester cohérent avec le reste des données on suit ces listes.
   Source : Feuil2 du Suivi + PPTX officiels + observations terrain.
"""

from __future__ import annotations


# ============================================================================
# STRICT (backend schema) — ne pas envoyer d'autre valeur
# ============================================================================

# meteo.vent
VENT_VALUES = [
    ("NUL", "Nul"),
    ("FAIBLE", "Faible"),
    ("MOYEN", "Moyen"),
    ("FORT", "Fort"),
]

# meteo.couverture (nuageuse, en %)
COUVERTURE_VALUES = [
    ("0-25", "0 – 25 %"),
    ("25-50", "25 – 50 %"),
    ("50-75", "50 – 75 %"),
    ("75-100", "75 – 100 %"),
]

# meteo.temperature_debut / fin : INTEGER (pas de décimales)

# observateur_probabilite (valeurs attendues dans les xlsx d'obs)
OBSERVATEUR_CONFIDENCE = [
    ("POSSIBLE", "Possible"),
    ("PROBABLE", "Probable"),
    ("SUR", "Sûr"),
]


# ============================================================================
# OBSERVÉ (frontend + terrain) — liste recommandée, pas imposée par le serveur
# ============================================================================

# configuration.detecteur_enregistreur_type
DETECTEUR_ENREGISTREUR_TYPES = [
    "SM2 +",
    "SM3BAT",
    "SM4BAT FS",
    "SM Mini",
    "SM Mini 2",
    "SMminiBAT",
    "Audiomoth",
    "Passive Recorder",
    "Batlogger A",
    "Batlogger A+",
    "Batlogger M",
    "Batlogger C",
    "Anabat Swift",
    "Anabat Scout",
    "Peersonic RPA3",
    "Autre",
]

# configuration.micro0_modele (et micro1_modele en stéréo)
MICRO_MODELES = [
    "SMX-U1",
    "SMX-U2",
    "SMX-US",
    "SM4 BAT FS",          # micro intégré SM4
    "MU (Audiomoth)",      # Audiomoth intégré
    "Batlogger micro",
    "Dodotronic Ultramic",
    "Ultramic UM250K",
    "Ultramic UM384K",
    "Avisoft Knowles",
    "Autre",
]

# configuration.micro0_hauteur : en mètres
# Convention observée : valeur négative si détecteur en gîte (grotte, combles...)
# Exemples : 1.5, 2, 4, 10, -2 (gîte 2m sous plafond)

# --- Points fixes ---
# Code point = lettre + chiffre (A1-A4, B1-B4, C1-C4, D1-D4 = 16 pastilles STOC)
# Autres codes courants observés : Z1, Z2, ... (points "opportunistes" hors grille)
POINT_CODE_HINT = "lettre A→Z + chiffre 1→9 (ex A1, C2, Z4)"


# ============================================================================
# Helpers
# ============================================================================

def vent_options() -> list[str]:
    """Retourne les valeurs à envoyer au backend (clés)."""
    return [v for v, _label in VENT_VALUES]


def vent_labels() -> list[str]:
    """Retourne les labels utilisateur (pour l'UI)."""
    return [label for _v, label in VENT_VALUES]


def vent_from_label(label: str) -> str | None:
    for v, lab in VENT_VALUES:
        if lab == label:
            return v
    return None


def couverture_options() -> list[str]:
    return [v for v, _ in COUVERTURE_VALUES]


def couverture_labels() -> list[str]:
    return [label for _v, label in COUVERTURE_VALUES]


def couverture_from_label(label: str) -> str | None:
    for v, lab in COUVERTURE_VALUES:
        if lab == label:
            return v
    return None


def confidence_options() -> list[str]:
    return [v for v, _ in OBSERVATEUR_CONFIDENCE]


def confidence_labels() -> list[str]:
    return [label for _v, label in OBSERVATEUR_CONFIDENCE]
