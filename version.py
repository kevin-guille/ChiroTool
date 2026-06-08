"""
version.py — métadonnées de version centralisées.

Un seul point de vérité pour la version, exploitée par :
  - la page « À propos »
  - la barre de titre éventuellement
  - la future logique d'auto-update (compare avec GitHub Releases)
  - le manifest des actions enregistrées dans chaque session (tool_version)

Convention SemVer après le 1er release public.
Pendant la phase de tests internes : suffixe `-dev` ou `-rc.N`.
"""

from __future__ import annotations

__version__ = "0.2-dev"
__build_date__ = "2026-06-04"

# URLs utilisées dans la page À propos et la vérification de mises à jour.
GITHUB_REPO_URL = "https://github.com/kevin-guille/ChiroTool"
GITHUB_RELEASES_API = "https://api.github.com/repos/kevin-guille/ChiroTool/releases/latest"
GITHUB_ISSUES_URL = "https://github.com/kevin-guille/ChiroTool/issues"

# Liens contributeurs / soutien
AUTHOR_NAME = "GUILLE Kevin"
AUTHOR_LINKEDIN = "https://fr.linkedin.com/in/kevin-guille-764b6a150"
EMPLOYER_NAME = "Acer Campestre"
EMPLOYER_URL = "https://www.acer-campestre.fr/"
EMPLOYER_LINKEDIN = "https://fr.linkedin.com/company/acer-campestre"

# Protocole et écosystème
PROTOCOL_NAME = "Vigie-Chiro Point Fixe — MNHN"
PROTOCOL_URL = "https://www.vigienature.fr/fr/chauves-souris"
PORTAL_URL = "https://vigiechiro.herokuapp.com/"

# Licence
LICENSE_NAME = "MIT"
LICENSE_URL = f"{GITHUB_REPO_URL}/blob/main/LICENSE"
