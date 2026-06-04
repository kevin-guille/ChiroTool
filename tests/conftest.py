"""Configuration pytest : ajoute le dossier parent au path."""

import sys
from pathlib import Path

# Permet à `tests/` d'importer les modules du dossier `_tool/`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
