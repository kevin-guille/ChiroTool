"""
resources.py — localisation des fichiers de données embarqués (CSV référentiels),
en développement comme dans l'exe PyInstaller.

Dans un build onefile, les ``datas`` déclarées dans la spec sont extraites sous
``sys._MEIPASS`` ; en développement, elles sont à côté des modules. On centralise
la résolution ici pour ne plus dépendre de l'emplacement exact du module appelant
(robuste à une éventuelle réorganisation future).
"""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(name: str) -> Path:
    """Chemin d'un fichier de données embarqué (``name`` = nom de fichier simple).

    - Exe PyInstaller : ``sys._MEIPASS / name`` (racine d'extraction).
    - Développement : à côté de ce module (racine du projet ``_tool``).
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / name
    return Path(__file__).with_name(name)
