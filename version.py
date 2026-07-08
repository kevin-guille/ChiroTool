"""
version.py — métadonnées de version centralisées.

Un seul point de vérité pour la version, exploitée par :
  - la page « À propos »
  - la barre de titre éventuellement
  - la future logique d'auto-update (compare avec GitHub Releases)
  - le manifest des actions enregistrées dans chaque session (tool_version)

Convention SemVer après le 1er release public.
Pendant la phase de tests internes : suffixe `-dev` ou `-rc.N`.

⚠️ Convention de release (pour que « Rechercher une mise à jour » soit exact) :
le **tag GitHub doit correspondre à `v{__version__}`**. Donc avant de publier :
  1. fixe `__version__` à la version cible (ex. `0.2` pour une stable, ou
     `0.2-dev` si tu publies un build de test),
  2. (re)build l'exe depuis ce code,
  3. crée la release avec le tag identique (`v0.2` ou `v0.2-dev`) — la case
     « pre-release » de GitHub reste indépendante du numéro de version.
Ainsi un exe qui affiche `0.2-dev` comparé au tag `v0.2-dev` → « à jour ».
"""

from __future__ import annotations

__version__ = "0.5.0-rc.2"
__build_date__ = "2026-07-08"

# URLs utilisées dans la page À propos et la vérification de mises à jour.
GITHUB_REPO_URL = "https://github.com/kevin-guille/ChiroTool"
# Endpoint LISTE (et non /latest) : /latest exclut les pre-releases. On veut
# pouvoir détecter aussi les pre-releases (v0.x) pendant la phase de test.
GITHUB_RELEASES_API = "https://api.github.com/repos/kevin-guille/ChiroTool/releases"
GITHUB_RELEASES_PAGE = "https://github.com/kevin-guille/ChiroTool/releases"
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


# --- Comparaison de versions (pour la recherche de mise à jour) -------------
import re as _re


def parse_version(s: str) -> tuple[tuple[int, int, int], tuple]:
    """Parse 'v0.2', '0.2-dev', '1.0.3-rc.2'… en clé de tri comparable.

    Retourne ``(core, pre)`` où ``core`` = (major, minor, patch) et ``pre``
    ordonne stable > rc > beta > alpha > dev. Une version STABLE (sans suffixe)
    est supérieure à toute pré-version du même ``core`` (sémantique SemVer).
    """
    s = (s or "").strip().lstrip("vV")
    s = s.split("+", 1)[0]                      # retire le build metadata
    core_str, _, suffix = s.partition("-")
    nums: list[int] = []
    for part in core_str.split("."):
        m = _re.match(r"\d+", part)
        nums.append(int(m.group()) if m else 0)
    while len(nums) < 3:
        nums.append(0)
    core = (nums[0], nums[1], nums[2])
    suffix = suffix.lower()
    if not suffix:
        pre: tuple = (1,)                       # stable : rang le plus haut
    else:
        rank = {"dev": 0, "alpha": 1, "beta": 2, "rc": 3}
        m = _re.match(r"([a-z]+)\.?(\d*)", suffix)
        typ = m.group(1) if m else suffix
        num = int(m.group(2)) if (m and m.group(2)) else 0
        pre = (0, rank.get(typ, 0), num)
    return core, pre


def is_newer(remote: str, local: str) -> bool:
    """True si la version ``remote`` est strictement plus récente que ``local``."""
    rc, rp = parse_version(remote)
    lc, lp = parse_version(local)
    return (rc, rp) > (lc, lp)


def fetch_latest_release(timeout: float = 6.0, per_page: int = 20) -> dict | None:
    """Renvoie la release publiée au tag de version le plus élevé, sous la forme
    ``{"tag", "prerelease", "url"}``.

    Combine DEUX sources et garde la plus récente :
    - la LISTE ``/releases`` (inclut les pre-releases pendant la phase de test) ;
    - ``/releases/latest`` (release stable canonique).
    Raison : l'endpoint LISTE est parfois servi en **cache obsolète** par GitHub
    (une release toute neuve n'y apparaît pas immédiatement) alors que
    ``/latest`` est à jour — les combiner rend la détection fiable et immédiate.

    Ignore les brouillons. **Ne lève jamais** : renvoie ``None`` sur toute erreur.
    """
    try:
        import requests
        headers = {"Accept": "application/vnd.github+json"}
        candidates: list[dict] = []

        r = requests.get(GITHUB_RELEASES_API, timeout=timeout,
                         params={"per_page": per_page}, headers=headers)
        if r.status_code == 200:
            candidates += [rel for rel in (r.json() or []) if not rel.get("draft")]

        # /releases/latest : à jour même quand la liste est en cache obsolète.
        try:
            rl = requests.get(GITHUB_RELEASES_API + "/latest",
                              timeout=timeout, headers=headers)
            if rl.status_code == 200:
                candidates.append(rl.json())
        except Exception:
            pass

        return _best_release(candidates)
    except Exception:
        return None


def _best_release(candidates: list) -> dict | None:
    """Sélectionne la release publiée au tag le plus élevé parmi ``candidates``
    (dicts API GitHub, éventuellement en double). Ignore les brouillons.
    Fonction PURE → testable. Renvoie ``{"tag","prerelease","url"}`` ou None."""
    published = [c for c in candidates if c and not c.get("draft")]
    if not published:
        return None
    latest = max(published,
                 key=lambda rel: parse_version(rel.get("tag_name") or ""))
    return {
        "tag": latest.get("tag_name") or "",
        "prerelease": bool(latest.get("prerelease")),
        "url": latest.get("html_url") or GITHUB_RELEASES_PAGE,
    }
