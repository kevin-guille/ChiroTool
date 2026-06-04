"""
vigiechiro_api.py — client Python pour l'API Vigie-Chiro (lecture seule, v1a).

Base URL : https://vigiechiro.herokuapp.com
Source  : https://github.com/Scille/vigiechiro-api (backend Eve/Flask)

Authentification : HTTP Basic avec ``token`` comme username et mot de passe
vide. Le token (32 caractères alphanumériques majuscules) est obtenu après
login OAuth sur le portail, et accessible dans le localStorage du navigateur
sous la clé ``auth-session-token``.

Endpoints couverts (v1a read-only) :
  - ping / me        : valide le token
  - list_sites       : sites de l'utilisateur
  - get_site         : détail d'un site
  - list_protocoles  : protocoles disponibles
  - list_participations : participations de l'utilisateur
  - get_participation   : détail d'une participation (inclut l'état de traitement)
  - download_file    : download direct d'un fichier via /fichiers/<id>/acces
  - list_donnees     : observations (lignes tadarida) d'une participation

Non couvert (viendra en v1b/c) :
  - POST /sites/<id>/participations     (création)
  - POST /fichiers, upload multipart S3 (upload WAV)
  - POST /participations/<id>/compute   (déclencher Tadarida)

Robustesse :
  - retry léger sur erreurs réseau transitoires
  - exceptions claires : TokenExpiredError, NetworkError, ApiError
  - timeouts configurables
  - pagination Eve transparente (itérateur)
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# PyInstaller --windowed : sys.stdout peut être None (pas de console).
# On guard pour éviter AttributeError au démarrage du .exe.
if sys.stdout is not None and getattr(sys.stdout, "encoding", None):
    if sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            if sys.stderr is not None:
                sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    requests = None  # type: ignore
    HTTPBasicAuth = None  # type: ignore


DEFAULT_BASE_URL = "https://vigiechiro.herokuapp.com/api/v1"
USER_AGENT = "ChiroTool/0.1 (+https://github.com/local/chirotool)"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ApiError(Exception):
    """Erreur API générique (4xx / 5xx autres que 401)."""


class TokenExpiredError(ApiError):
    """Token invalide ou expiré (HTTP 401)."""


class NetworkError(ApiError):
    """Erreur réseau (timeout, DNS, connexion refusée, etc.)."""


# ---------------------------------------------------------------------------
# Helpers de sérialisation pour l'API Eve
# ---------------------------------------------------------------------------

# Noms anglais des jours/mois pour le format RFC 1123 (forcés indépendamment
# de la locale du système — sinon python-eve refuse les dates en français
# type "Lun, 19 mai 2026 ...").
_DAYS_RFC = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTHS_RFC = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _to_rfc1123(dt: datetime) -> str:
    """Sérialise un datetime au format RFC 1123 (attendu par Eve / Vigie-Chiro).

    Exemple : 'Tue, 19 May 2026 19:00:00 GMT'

    On utilise strftime EN ANGLAIS via une table manuelle, pour ne pas dépendre
    de ``locale.LC_TIME`` (qui peut être français côté Windows BE).
    """
    if dt is None:
        raise ValueError("datetime requis pour la sérialisation RFC 1123")
    return (
        f"{_DAYS_RFC[dt.weekday()]}, "
        f"{dt.day:02d} {_MONTHS_RFC[dt.month]} {dt.year:04d} "
        f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} GMT"
    )


class NotFoundError(ApiError):
    """Ressource introuvable (HTTP 404)."""


# ---------------------------------------------------------------------------
# Données
# ---------------------------------------------------------------------------

@dataclass
class Site:
    id: str
    numero: str | None = None
    protocole_id: str | None = None
    observateur_id: str | None = None
    commentaire: str | None = None
    localites: list[dict] = field(default_factory=list)  # points avec géom
    grille_stoc_id: str | None = None
    date_creation: datetime | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, d: dict) -> "Site":
        # Le n° site Tadarida (utilisé dans le nom CarXXXXXX) est suffixé au titre,
        # ex : "Vigiechiro - Point Fixe-250887"  →  numero = "250887"
        numero = d.get("numero") or d.get("numero_site")
        if not numero and d.get("titre"):
            import re
            m = re.search(r"-(\d{5,6})\s*$", str(d["titre"]))
            if m:
                numero = m.group(1).zfill(6)  # 045945 si département 04
        return cls(
            id=str(d.get("_id") or d.get("id") or ""),
            numero=str(numero).strip() if numero else None,
            protocole_id=_id_of(d.get("protocole")),
            observateur_id=_id_of(d.get("observateur")),
            commentaire=d.get("commentaire"),
            localites=d.get("localites") or [],
            grille_stoc_id=_id_of(d.get("grille_stoc")),
            date_creation=_parse_dt(d.get("_created") or d.get("date_creation")),
            raw=d,
        )

    def point_coordinates(self, point_name: str) -> tuple[float, float] | None:
        """Retourne (lat, lon) du point `point_name` (ex 'Z1') s'il existe."""
        for loc in self.localites:
            if loc.get("nom") == point_name:
                for g in (loc.get("geometries") or {}).get("geometries", []):
                    if g.get("type") == "Point" and len(g.get("coordinates", [])) >= 2:
                        return float(g["coordinates"][0]), float(g["coordinates"][1])
        return None


@dataclass
class Participation:
    id: str
    site_id: str | None = None
    observateur_id: str | None = None
    protocole_id: str | None = None
    date_debut: datetime | None = None
    date_fin: datetime | None = None
    point: str | None = None
    commentaire: str | None = None
    traitement_etat: str | None = None   # 'PLANIFIE' / 'EN_COURS' / 'TERMINE' / ...
    traitement_date: datetime | None = None
    bilan: dict | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, d: dict) -> "Participation":
        traitement = d.get("traitement") or {}
        return cls(
            id=str(d.get("_id") or d.get("id") or ""),
            site_id=_id_of(d.get("site")),
            observateur_id=_id_of(d.get("observateur")),
            protocole_id=_id_of(d.get("protocole")),
            date_debut=_parse_dt(d.get("date_debut")),
            date_fin=_parse_dt(d.get("date_fin")),
            point=d.get("point"),
            commentaire=d.get("commentaire"),
            traitement_etat=traitement.get("etat"),
            traitement_date=_parse_dt(traitement.get("date_planification")
                                       or traitement.get("date_debut")),
            bilan=d.get("bilan"),
            raw=d,
        )


def _id_of(x: Any) -> str | None:
    if x is None:
        return None
    if isinstance(x, dict):
        return str(x.get("_id") or x.get("id") or "") or None
    return str(x) or None


def _parse_dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        # ISO 8601 avec offset (+00:00, -05:00) : fromisoformat gère
        s = v.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            pass
        # Formats plus exotiques (RFC 1123 notamment)
        for fmt in (
            "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S", "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(v, fmt)
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class VigieChiroClient:
    """Client Vigie-Chiro. Lève les exceptions typées ci-dessus en cas d'erreur.

    Pattern "Retry source-gated" : les requêtes
    ``foreground`` (upload humain qui attend, get_participation direct)
    retry agressivement ; les requêtes ``background`` (polling status,
    fetch régulier) renoncent vite pour ne pas saturer en cas de cascade
    API down.

    Le champ ``source`` est un défaut par instance ; chaque appel peut
    l'override via ``_request(..., source="background")``.
    """

    # Politique de retry par source
    _RETRY_POLICY = {
        "foreground": {"max_retries": 5, "base_backoff": 0.5, "cap": 32.0},
        "background": {"max_retries": 1, "base_backoff": 0.5, "cap": 4.0},
    }

    def __init__(
        self,
        token: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 30,
        source: str = "foreground",
    ):
        if requests is None:
            raise ImportError("le module 'requests' est requis (pip install requests)")
        if not token or len(token) < 16:
            raise ValueError("token invalide (attendu ~32 caractères)")
        if source not in self._RETRY_POLICY:
            raise ValueError(f"source invalide : {source!r} "
                               f"(attendu : {list(self._RETRY_POLICY)})")

        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.source = source

        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(token, "")
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })

    @property
    def max_retries(self) -> int:
        return self._RETRY_POLICY[self.source]["max_retries"]

    @property
    def retry_backoff(self) -> float:
        return self._RETRY_POLICY[self.source]["base_backoff"]

    # -- bas niveau ---------------------------------------------------------

    def _request(self, method: str, path: str, *,
                  source: str | None = None, **kwargs) -> Any:
        """
        Appel HTTP avec retry source-gated.

        - ``foreground`` : retry 5× sur erreur réseau + 5xx + 429, backoff
          exponentiel 0.5 → 32 s + jitter 25 %. Respecte ``Retry-After``.
        - ``background`` : retry 1× seulement, pour ne pas amplifier les
          cascades API.
        """
        import random

        effective_source = source or self.source
        policy = self._RETRY_POLICY.get(effective_source, self._RETRY_POLICY["foreground"])
        max_retries = policy["max_retries"]
        base = policy["base_backoff"]
        cap = policy["cap"]

        url = path if path.startswith("http") else f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)

        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            # Erreurs réseau
            try:
                resp = self.session.request(method, url, **kwargs)
            except requests.RequestException as e:
                last_exc = NetworkError(f"{method} {path} : {e}")
                if attempt < max_retries:
                    delay = min(cap, base * (2 ** attempt))
                    delay *= 1.0 + random.uniform(-0.25, 0.25)   # jitter ±25 %
                    time.sleep(delay)
                    continue
                raise last_exc

            # Codes non-retryables immédiats
            if resp.status_code == 401:
                raise TokenExpiredError("token Vigie-Chiro invalide ou expiré (HTTP 401)")
            if resp.status_code == 404:
                raise NotFoundError(f"ressource introuvable : {method} {path}")

            # 429 / 5xx : retry avec éventuel Retry-After
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                if attempt < max_retries:
                    ra = resp.headers.get("Retry-After")
                    if ra:
                        try:
                            delay = min(cap, float(ra))
                        except ValueError:
                            delay = base * (2 ** attempt)
                    else:
                        delay = base * (2 ** attempt)
                    delay = min(cap, delay)
                    delay *= 1.0 + random.uniform(-0.25, 0.25)
                    time.sleep(max(0.1, delay))
                    continue
                # Plus de retries → lève
                body = resp.text[:500] if resp.text else ""
                raise ApiError(f"HTTP {resp.status_code} sur {method} {path} : {body}")

            # Autres 4xx : fatal
            if resp.status_code >= 400:
                body = resp.text[:500] if resp.text else ""
                raise ApiError(f"HTTP {resp.status_code} sur {method} {path} : {body}")

            # Succès
            if resp.status_code == 204 or not resp.content:
                return {}
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" in ctype:
                try:
                    return resp.json()
                except ValueError:
                    return {"_raw": resp.text}
            return resp

        # Normalement inatteignable
        raise last_exc or ApiError("échec requête sans exception (bug ?)")

    # -- ping / me ----------------------------------------------------------

    def me(self) -> dict:
        """
        Retourne les informations de l'utilisateur courant.
        Tente plusieurs chemins possibles (l'API n'expose pas toujours /moi).
        """
        errs: list[str] = []
        for path in ("/moi", "/utilisateurs/moi", "/me", "/utilisateurs"):
            try:
                data = self._request("GET", path)
            except NotFoundError as e:
                errs.append(str(e))
                continue
            # Si /utilisateurs renvoie une liste, on prend le 1er (cas fallback)
            if isinstance(data, dict) and data.get("_items"):
                items = data["_items"]
                if items:
                    return items[0]
            if isinstance(data, dict) and "email" in data:
                return data
        raise ApiError(
            "aucune route 'moi' connue n'a répondu.\n"
            "Routes essayées : " + ", ".join(errs)
        )

    def ping(self) -> bool:
        """Test rapide : True si token valide, False sinon (lève seulement sur erreur réseau)."""
        try:
            self.me()
            return True
        except TokenExpiredError:
            return False
        except ApiError:
            # Le token passe mais la route /moi n'existe pas → on teste /sites minimal
            try:
                self._request("GET", "/sites", params={"max_results": 1})
                return True
            except TokenExpiredError:
                return False
            except ApiError:
                return False

    # -- sites --------------------------------------------------------------

    def iter_sites(
        self,
        page_size: int = 50,
        params: dict | None = None,
        mine_only: bool = False,
    ) -> Iterator[dict]:
        """Itère sur tous les sites accessibles (pagination Eve transparente).

        Si ``mine_only`` : appelle ``/sites/mes-sites`` au lieu de ``/sites``
        (uniquement les sites dont l'utilisateur est observateur).
        """
        path = "/moi/sites" if mine_only else "/sites"
        page = 1
        while True:
            p = {"max_results": page_size, "page": page}
            if params:
                p.update(params)
            data = self._request("GET", path, params=p)
            items = (data.get("_items") or []) if isinstance(data, dict) else []
            if not items:
                break
            for it in items:
                yield it
            meta = data.get("_meta", {}) if isinstance(data, dict) else {}
            total = meta.get("total") or 0
            seen = page * page_size
            if seen >= total:
                break
            page += 1

    def list_sites(self, page_size: int = 50, mine_only: bool = False) -> list[Site]:
        return [Site.from_api(d) for d in self.iter_sites(page_size=page_size, mine_only=mine_only)]

    def list_my_sites(self) -> list[Site]:
        return self.list_sites(mine_only=True)

    def get_site(self, site_id: str) -> Site:
        d = self._request("GET", f"/sites/{site_id}")
        return Site.from_api(d)

    # -- protocoles ---------------------------------------------------------

    def list_protocoles(self, mine_only: bool = False) -> list[dict]:
        path = "/moi/protocoles" if mine_only else "/protocoles"
        data = self._request("GET", path, params={"max_results": 50})
        if isinstance(data, dict):
            return data.get("_items") or []
        return []

    # -- participations -----------------------------------------------------

    def iter_participations(
        self,
        page_size: int = 50,
        params: dict | None = None,
        mine_only: bool = False,
    ) -> Iterator[dict]:
        path = "/moi/participations" if mine_only else "/participations"
        page = 1
        while True:
            p = {"max_results": page_size, "page": page}
            if params:
                p.update(params)
            data = self._request("GET", path, params=p)
            items = (data.get("_items") or []) if isinstance(data, dict) else []
            if not items:
                break
            for it in items:
                yield it
            meta = data.get("_meta", {}) if isinstance(data, dict) else {}
            if page * page_size >= (meta.get("total") or 0):
                break
            page += 1

    def list_participations(self, page_size: int = 50, mine_only: bool = False) -> list[Participation]:
        return [Participation.from_api(d) for d in self.iter_participations(page_size=page_size, mine_only=mine_only)]

    def list_my_participations(self) -> list[Participation]:
        return self.list_participations(mine_only=True)

    def get_participation(self, participation_id: str) -> Participation:
        d = self._request("GET", f"/participations/{participation_id}")
        return Participation.from_api(d)

    def participation_status(self, participation_id: str) -> dict:
        """Raccourci : renvoie juste l'état du traitement Tadarida."""
        p = self.get_participation(participation_id)
        return {
            "id": p.id,
            "etat": p.traitement_etat,
            "date": p.traitement_date.isoformat() if p.traitement_date else None,
            "has_bilan": p.bilan is not None,
        }

    # -- données / observations --------------------------------------------

    def iter_donnees(
        self,
        participation_id: str,
        page_size: int = 99,  # le backend refuse max_results >= 100
        on_progress=None,
    ) -> Iterator[dict]:
        """
        Itère sur les 'données' d'une participation. Une 'donnée' = un fichier
        WAV avec ses observations (contacts Tadarida).

        Route : /participations/<id>/donnees (la route /donnees seule n'expose
        pas de filtrage par participation côté public).
        """
        page = 1
        seen = 0
        total = None
        while True:
            data = self._request(
                "GET", f"/participations/{participation_id}/donnees",
                params={"max_results": page_size, "page": page},
            )
            items = (data.get("_items") or []) if isinstance(data, dict) else []
            meta = data.get("_meta", {}) if isinstance(data, dict) else {}
            if total is None:
                total = meta.get("total") or 0
            for it in items:
                yield it
                seen += 1
                if on_progress is not None:
                    on_progress(seen, total)
            if not items or seen >= total:
                break
            page += 1

    def download_observations_as_xlsx(
        self,
        participation_id: str,
        dst: Path,
        on_progress=None,
    ) -> dict:
        """
        Produit un fichier .xlsx au format 'participation-<id>-observations.xlsx'
        identique à celui reçu par mail depuis le portail. Utilisable
        directement par ``cleanup.py``.

        Colonnes produites :
          nom du fichier · temps_debut · temps_fin · frequence_mediane ·
          tadarida_taxon · tadarida_probabilite · tadarida_taxon_autre ·
          observateur_taxon · observateur_probabilite ·
          validateur_taxon · validateur_probabilite

        Retourne un dict avec les stats (nb fichiers, nb contacts, path).
        """
        import openpyxl

        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Mode write_only : les lignes sont streamées sur disque plutôt que
        # gardées en RAM. Pour 10k contacts, RAM pic passe de ~220 MB à <20 MB.
        # L'API est légèrement différente : pas d'accès aléatoire aux cellules
        # mais on ne fait que ws.append() ici → OK.
        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet(title=f"participation-{participation_id[:22]}")
        headers = [
            "nom du fichier", "temps_debut", "temps_fin", "frequence_mediane",
            "tadarida_taxon", "tadarida_probabilite", "tadarida_taxon_autre",
            "observateur_taxon", "observateur_probabilite",
            "validateur_taxon", "validateur_probabilite",
        ]
        ws.append(headers)

        n_files = 0
        n_contacts = 0
        n_silent = 0

        def _short(tx: Any) -> str | None:
            """Extrait libelle_court d'un taxon (objet ou string)."""
            if tx is None:
                return None
            if isinstance(tx, dict):
                return tx.get("libelle_court") or tx.get("_id")
            return str(tx)

        for donnee in self.iter_donnees(participation_id, on_progress=on_progress):
            n_files += 1
            titre = donnee.get("titre") or ""
            obs_list = donnee.get("observations") or []
            if not obs_list:
                n_silent += 1
                continue
            for obs in obs_list:
                n_contacts += 1
                # tadarida_taxon_autre → "Code1:0.03, Code2:0.02, ..."
                autres_s = ""
                if obs.get("tadarida_taxon_autre"):
                    parts = []
                    for a in obs["tadarida_taxon_autre"]:
                        tx = _short(a.get("taxon"))
                        p = a.get("probabilite")
                        if tx is not None:
                            parts.append(f"{tx}:{p}" if p is not None else tx)
                    autres_s = ", ".join(parts)

                ws.append([
                    titre,
                    obs.get("temps_debut"),
                    obs.get("temps_fin"),
                    obs.get("frequence_mediane"),
                    _short(obs.get("tadarida_taxon")),
                    obs.get("tadarida_probabilite"),
                    autres_s,
                    _short(obs.get("observateur_taxon")),
                    obs.get("observateur_probabilite"),
                    _short(obs.get("validateur_taxon")),
                    obs.get("validateur_probabilite"),
                ])

        tmp = dst.with_suffix(dst.suffix + ".tmp")
        wb.save(str(tmp))
        tmp.replace(dst)

        return {
            "path": str(dst),
            "n_files": n_files,
            "n_contacts": n_contacts,
            "n_silent_files": n_silent,
        }

    # -- fichiers (download) -----------------------------------------------

    def get_file_url(self, file_id: str) -> str:
        """Retourne l'URL S3 signée pour télécharger le fichier."""
        d = self._request("GET", f"/fichiers/{file_id}/acces",
                          params={"redirection": "false"})
        if isinstance(d, dict) and "s3_signed_url" in d:
            return d["s3_signed_url"]
        raise ApiError(f"réponse inattendue pour /fichiers/{file_id}/acces : {d!r}")

    def list_participation_files(self, participation_id: str) -> list[str]:
        """Retourne la liste des **noms** (``titre``) des fichiers WAV déjà
        uploadés pour une participation donnée.

        Permet la reprise d'upload : si un batch a été interrompu (PC éteint,
        crash, fermeture forcée), un nouvel "Upload + Tadarida" relancé sur la
        même session détecte ces fichiers et ne renvoie que les manquants.

        Stratégie :
          1. ``GET /fichiers?where={"lien_participation":"<id>"}`` — endpoint
             Eve standard. Retourne paginé.
          2. Si ce champ n'est pas le bon (schema Vigie-Chiro a évolué), on
             essaye ``participation`` puis ``lien_donnee``.
          3. Si rien ne marche → retourne [] (l'upload se fera intégralement,
             côté serveur ça créera potentiellement des doublons mais c'est
             un comportement dégradé acceptable).

        Retourne la liste des noms de fichiers (avec extension), ou [] si
        aucun fichier ou impossible de lister.
        """
        import json
        for field in ("lien_participation", "participation"):
            try:
                page = 1
                names: list[str] = []
                while True:
                    params = {
                        "where": json.dumps({field: participation_id}),
                        "max_results": 99, "page": page,
                    }
                    resp = self._request("GET", "/fichiers", params=params,
                                          source="background")
                    items = (resp or {}).get("_items") or []
                    for it in items:
                        # Le champ "titre" contient le nom de fichier original
                        # ("Car260155-...wav"). Selon le schéma, ce peut aussi
                        # être "nom" ou "filename" — on essaye plusieurs.
                        name = it.get("titre") or it.get("nom") \
                            or it.get("filename")
                        if name:
                            names.append(str(name))
                    # Détection fin de pagination
                    meta = (resp or {}).get("_meta") or {}
                    total = meta.get("total", 0)
                    if not items or len(names) >= total:
                        break
                    page += 1
                if names:
                    return names
                # Champ valide mais 0 résultat → on garde [] et on ne tente
                # pas d'autres noms de champs
                return []
            except ApiError:
                # Champ invalide pour ce schéma → essaye le suivant
                continue
            except Exception:
                # Erreur réseau ou autre : fallback graceful
                return []
        return []

    # -- WRITE : modification de sites -------------------------------------

    def update_site_localites(
        self,
        site_id: str,
        localites: list[dict],
        etag: str | None = None,
    ) -> dict:
        """
        PUT /sites/<id>/localites — remplace la liste des localités du site.

        ``localites`` : liste de dicts de la forme ::

            {"nom": "Z1",
             "geometries": {
                 "type": "GeometryCollection",
                 "geometries": [
                     {"type": "Point",
                      "coordinates": [lat, lon]}
                 ]
             },
             "representatif": false,
             "habitat_maille": ...,     # optionnel
             "habitats": [...]}         # optionnel

        Si ``etag`` est fourni, envoyé en ``If-Match`` (évite les conflits).
        """
        headers = {}
        if etag:
            headers["If-Match"] = etag
        return self._request(
            "PUT", f"/sites/{site_id}/localites",
            json={"localites": localites},
            headers=headers or None,
        )

    def add_localite(
        self,
        site_id: str,
        nom: str,
        lat: float,
        lon: float,
        *,
        representatif: bool = False,
    ) -> dict:
        """
        Ajoute une nouvelle localité au site.

        Récupère les localités existantes, ajoute la nouvelle, et fait
        un PUT avec la liste complète (contrat de l'endpoint).

        Lève ``ValueError`` si ``nom`` existe déjà dans le site.
        """
        site = self._request("GET", f"/sites/{site_id}")
        existing = list(site.get("localites") or [])
        for loc in existing:
            if (loc.get("nom") or "").strip().upper() == nom.strip().upper():
                raise ValueError(
                    f"le point '{nom}' existe déjà dans ce site")

        new_loc = {
            "nom": nom,
            "geometries": {
                "type": "GeometryCollection",
                "geometries": [{
                    "type": "Point",
                    # Vigie-Chiro stocke [lat, lon] (ordre observé en lecture)
                    "coordinates": [lat, lon],
                }],
            },
            "representatif": bool(representatif),
        }
        existing.append(new_loc)
        etag = site.get("_etag")
        return self.update_site_localites(site_id, existing, etag=etag)

    # -- WRITE : création / upload (v1c) -----------------------------------

    def create_participation(
        self,
        site_id: str,
        *,
        date_debut: datetime,
        date_fin: datetime,
        point: str,
        meteo: dict | None = None,
        configuration: dict | None = None,
        commentaire: str | None = None,
    ) -> dict:
        """
        POST /sites/<site_id>/participations — crée une participation vide
        (sans fichiers). Le traitement Tadarida n'est PAS lancé à ce stade.

        Args:
          site_id          : ObjectId du site Vigie-Chiro (ex '66ab2f58e4f...')
          date_debut       : datetime de pose du boîtier
          date_fin         : datetime de relève
          point            : code du point dans le site (ex 'Z1')
          meteo            : {temperature_debut, temperature_fin, vent, couverture}
                             vent ∈ {'NUL','FAIBLE','MOYEN','FORT'}
                             couverture ∈ {'0-25','25-50','50-75','75-100'}
          configuration    : {detecteur_enregistreur_type, micro0_hauteur, ...}
          commentaire      : note libre

        Returns: dict (réponse API avec _id de la nouvelle participation)
        """
        # IMPORTANT : l'API Eve de Vigie-Chiro attend les dates au format
        # RFC 1123 ("Wed, 19 May 2026 19:00:00 GMT"), pas en ISO 8601.
        # Avec de l'ISO, le serveur renvoie HTTP 422 :
        #   "date_debut: must be of datetime type"
        # Voir Eve docs : app.config['DATE_FORMAT'] = '%a, %d %b %Y %H:%M:%S GMT'
        # On considère le datetime saisi comme exprimé en heure locale et on
        # l'envoie tel quel avec le marqueur GMT (le serveur stocke en UTC
        # mais retransmet en RFC 1123 — cohérent avec ce que fait le
        # frontend JS officiel).
        payload: dict[str, Any] = {
            "date_debut": _to_rfc1123(date_debut),
            "date_fin": _to_rfc1123(date_fin),
            "point": point,
        }
        if meteo:
            # Validation côté client des enums stricts (évite 422 obscurs
            # de l'API Eve si le wizard GUI envoie une valeur minuscule, etc.)
            try:
                from vigiechiro_enums import vent_options, couverture_options
                vent_ok = set(vent_options())
                cov_ok = set(couverture_options())
            except Exception:
                vent_ok, cov_ok = set(), set()
            if "vent" in meteo and vent_ok and meteo["vent"] not in vent_ok:
                raise ValueError(
                    f"meteo.vent invalide : {meteo['vent']!r}. "
                    f"Attendu : {sorted(vent_ok)}")
            if "couverture" in meteo and cov_ok and meteo["couverture"] not in cov_ok:
                raise ValueError(
                    f"meteo.couverture invalide : {meteo['couverture']!r}. "
                    f"Attendu : {sorted(cov_ok)}")
            for k in ("temperature_debut", "temperature_fin"):
                if k in meteo and meteo[k] is not None:
                    if not isinstance(meteo[k], int):
                        raise TypeError(
                            f"meteo.{k} doit être un entier (reçu "
                            f"{type(meteo[k]).__name__} : {meteo[k]!r})")
            payload["meteo"] = meteo
        if configuration:
            payload["configuration"] = configuration
        if commentaire:
            payload["commentaire"] = commentaire
        return self._request("POST", f"/sites/{site_id}/participations", json=payload)

    def upload_wav(
        self,
        participation_id: str,
        path: Path,
        on_progress=None,
        multipart_threshold: int = 5 * 1024 * 1024,
    ) -> dict:
        """
        Upload d'un WAV vers Vigie-Chiro.

        Workflow (d'après issue #34 + fichiers.py) :
          1. POST /fichiers        → crée l'entrée + URL S3 signée
          2. PUT vers S3 (signée)  → upload binaire (single part ou multipart)
          3. POST /fichiers/<id>   → finalise

        Pour les fichiers <= ``multipart_threshold`` (5 MB par défaut) on fait
        un upload single-part (plus simple, plus rapide). Au-delà on bascule
        en multipart.

        Retourne le dict fichier final (avec _id, _etag, titre).
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        size = path.stat().st_size
        use_multipart = size > multipart_threshold

        # 1. création de l'entrée
        body = {
            "titre": path.name,
            "multipart": use_multipart,
            "lien_participation": participation_id,
        }
        meta = self._request("POST", "/fichiers", json=body)
        file_id = meta.get("_id") or meta.get("id")
        if not file_id:
            raise ApiError(f"réponse POST /fichiers sans _id : {meta}")

        if not use_multipart:
            # 2. upload single-part
            url = meta.get("s3_signed_url")
            if not url:
                raise ApiError(f"s3_signed_url manquante dans réponse : {meta}")
            self._put_single_s3(url, path, on_progress=on_progress)
            # 3. finalisation
            self._request("POST", f"/fichiers/{file_id}", json={})
        else:
            # Multipart : on découpe en chunks de multipart_threshold
            self._upload_multipart(file_id, path, chunk_size=multipart_threshold,
                                   on_progress=on_progress)

        return {"_id": file_id, "titre": path.name, "size": size,
                "multipart": use_multipart}

    def _put_single_s3(self, signed_url: str, path: Path, on_progress=None,
                        max_retries: int = 3) -> None:
        """PUT binaire vers URL S3 signée, avec retry sur erreur réseau/5xx.

        Le body est relu DEPUIS LE DÉBUT à chaque tentative (un reader streamé
        consommé ne peut pas être rejoué — on ré-ouvre le fichier).
        """
        import time as _time
        size = path.stat().st_size
        last_err = None
        for attempt in range(max_retries):
            uploaded = 0

            class _Reader:
                def __init__(self, p):
                    self._f = p.open("rb")
                def read(self, n=-1):
                    chunk = self._f.read(n if n > 0 else 65536)
                    nonlocal uploaded
                    uploaded += len(chunk)
                    if on_progress is not None:
                        on_progress(uploaded, size)
                    return chunk
                def __len__(self):
                    return size
                def close(self):
                    self._f.close()

            reader = _Reader(path)
            try:
                resp = requests.put(
                    signed_url, data=reader, timeout=self.timeout * 10,
                    headers={"Content-Length": str(size),
                             "Content-Type": "audio/wav"})
                if resp.status_code in (200, 201):
                    return  # succès
                # 4xx (URL expirée/refusée) : inutile de retry
                if 400 <= resp.status_code < 500:
                    raise ApiError(
                        f"upload S3 refusé (HTTP {resp.status_code}): "
                        f"{resp.text[:200]}")
                last_err = ApiError(f"upload S3 HTTP {resp.status_code}")
            except (requests.RequestException,) as e:
                last_err = e
            finally:
                reader.close()
            # Backoff avant retry
            if attempt < max_retries - 1:
                _time.sleep(1.5 * (attempt + 1))
        raise ApiError(f"upload S3 échoué après {max_retries} tentatives : {last_err}")

    def _upload_multipart(self, file_id: str, path: Path, chunk_size: int,
                          on_progress=None) -> None:
        """Upload multipart S3 : un PUT par part, puis POST finalize avec etags.

        En cas d'échec d'une part, on tente d'abandonner proprement l'upload
        multipart côté serveur (DELETE) pour ne pas laisser de parts orphelines,
        puis on propage l'erreur. La part elle-même est retryée 3× avant
        d'abandonner.
        """
        import time as _time
        size = path.stat().st_size
        parts: list[dict] = []
        uploaded = 0
        try:
            with path.open("rb") as f:
                part_number = 1
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    resp = self._request("PUT", f"/fichiers/{file_id}/multipart",
                                         json={"part_number": part_number})
                    url = resp.get("s3_signed_url")
                    if not url:
                        raise ApiError(
                            f"s3_signed_url manquante pour part {part_number}")
                    # Upload de la part avec retry
                    etag = None
                    last_err = None
                    for attempt in range(3):
                        try:
                            r = requests.put(
                                url, data=chunk, timeout=self.timeout * 5,
                                headers={"Content-Length": str(len(chunk))})
                            if r.status_code in (200, 201):
                                etag = r.headers.get("ETag", "").strip('"')
                                break
                            if 400 <= r.status_code < 500:
                                raise ApiError(
                                    f"part {part_number} refusée HTTP {r.status_code}")
                            last_err = ApiError(
                                f"part {part_number} HTTP {r.status_code}")
                        except requests.RequestException as e:
                            last_err = e
                        if attempt < 2:
                            _time.sleep(1.5 * (attempt + 1))
                    if etag is None:
                        raise ApiError(
                            f"upload part {part_number} échoué après 3 tentatives : "
                            f"{last_err}")
                    parts.append({"part_number": part_number, "etag": etag})
                    uploaded += len(chunk)
                    if on_progress is not None:
                        on_progress(uploaded, size)
                    part_number += 1
            # Finalisation
            self._request("POST", f"/fichiers/{file_id}", json={"parts": parts})
        except Exception:
            # Abandon de l'upload multipart pour ne pas laisser de parts
            # orphelines côté serveur (best-effort, ne masque pas l'erreur).
            try:
                self._request("DELETE", f"/fichiers/{file_id}")
            except Exception:
                pass
            raise

    def trigger_compute(self, participation_id: str) -> dict:
        """Lance le traitement Tadarida côté serveur.
        POST /participations/<id>/compute."""
        return self._request("POST", f"/participations/{participation_id}/compute")

    def wait_for_completion(
        self,
        participation_id: str,
        poll_interval: int = 60,
        max_wait: int = 3 * 3600,
        on_poll=None,
    ) -> str:
        """
        Bloque jusqu'à ce que l'état du traitement soit 'TERMINE' (ou 'FINI'),
        ou jusqu'à ``max_wait`` secondes.

        Chaque poll utilise source=background → pas de retry agressif.
        Si l'API tousse temporairement, on attend juste le prochain poll
        plutôt que d'amplifier la cascade.

        Retourne l'état final. Lève TimeoutError si dépasse max_wait.
        """
        elapsed = 0
        etat = ""
        while elapsed < max_wait:
            try:
                d = self._request("GET", f"/participations/{participation_id}",
                                    source="background")
                traitement = (d.get("traitement") or {}) if isinstance(d, dict) else {}
                etat = traitement.get("etat") or ""
            except TokenExpiredError:
                # Token expiré : propager immédiatement, ne pas boucler 3h.
                # L'utilisateur doit re-saisir son token avant de reprendre.
                raise
            except NetworkError:
                etat = "(poll network error)"
            except ApiError:
                etat = "(poll api error)"
            if on_poll is not None:
                on_poll(etat, elapsed)
            if etat in ("TERMINE", "FINI", "ERROR", "ERREUR"):
                return etat
            time.sleep(poll_interval)
            elapsed += poll_interval
        raise TimeoutError(
            f"traitement toujours pas terminé après {max_wait}s "
            f"(dernier état : {etat!r})"
        )

    def download_file(self, file_id: str, dst: Path, chunk_size: int = 1 << 16) -> Path:
        """Télécharge un fichier via l'URL signée, streaming sur disque."""
        url = self.get_file_url(file_id)
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(dst.suffix + ".part")
        try:
            with requests.get(url, stream=True, timeout=self.timeout) as r:
                r.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in r.iter_content(chunk_size):
                        if chunk:
                            f.write(chunk)
            tmp.replace(dst)
        except requests.RequestException as e:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise NetworkError(f"échec téléchargement {file_id} : {e}")
        return dst


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_token_from_args_or_storage(arg_token: str | None) -> str:
    if arg_token:
        return arg_token
    from credentials import load_token
    tok = load_token()
    if not tok:
        raise SystemExit(
            "❌ aucun token. Utilise --token XXXX, ou enregistre-le d'abord avec :\n"
            "   python vigiechiro_api.py save-token XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        )
    return tok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--token", help="token Vigie-Chiro (sinon chargé depuis le stockage)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)

    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping", help="valide le token")
    sub.add_parser("me", help="infos utilisateur")
    p_sites = sub.add_parser("sites", help="liste des sites")
    p_sites.add_argument("--mine", action="store_true", help="uniquement mes sites")

    p_site = sub.add_parser("site", help="détail d'un site")
    p_site.add_argument("id")

    p_proto = sub.add_parser("protocoles", help="liste des protocoles")
    p_proto.add_argument("--mine", action="store_true")

    p_parts = sub.add_parser("participations", help="liste des participations")
    p_parts.add_argument("--mine", action="store_true")

    p_part = sub.add_parser("participation", help="détail d'une participation")
    p_part.add_argument("id")

    p_obs = sub.add_parser("observations", help="télécharge les observations d'une participation en xlsx")
    p_obs.add_argument("id")
    p_obs.add_argument("--out", type=Path, default=None,
                       help="chemin de sortie (défaut : participation-<id>-observations.xlsx dans le dossier courant)")

    p_save = sub.add_parser("save-token", help="enregistre un token dans le stockage sécurisé")
    p_save.add_argument("token")

    sub.add_parser("delete-token", help="efface le token du stockage sécurisé")
    sub.add_parser("storage", help="affiche le backend de stockage utilisé")

    args = ap.parse_args()

    # Commandes qui ne nécessitent pas de client
    if args.cmd == "save-token":
        from credentials import save_token
        backend = save_token(args.token)
        print(f"✓ token enregistré ({backend})")
        return 0
    if args.cmd == "delete-token":
        from credentials import delete_token
        ok = delete_token()
        print("✓ token effacé" if ok else "(aucun token trouvé)")
        return 0
    if args.cmd == "storage":
        from credentials import storage_backend
        print(f"Backend : {storage_backend()}")
        return 0

    token = _load_token_from_args_or_storage(args.token)
    try:
        client = VigieChiroClient(token, base_url=args.base_url)
    except (ValueError, ImportError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    try:
        if args.cmd == "ping":
            ok = client.ping()
            print("✓ token valide" if ok else "✗ token invalide / expiré")
            return 0 if ok else 1

        if args.cmd == "me":
            import json as _json
            print(_json.dumps(client.me(), indent=2, ensure_ascii=False, default=str))
            return 0

        if args.cmd == "sites":
            n = 0
            for s in client.list_sites(mine_only=getattr(args, "mine", False)):
                n += 1
                pts = len(s.localites)
                print(f"  {s.id}  num={s.numero or '?':<8}  {pts} point(s)  "
                      f"proto={s.protocole_id}")
            print(f"\nTotal : {n} site(s)")
            return 0

        if args.cmd == "site":
            s = client.get_site(args.id)
            import json as _json
            print(_json.dumps(s.raw, indent=2, ensure_ascii=False, default=str))
            return 0

        if args.cmd == "protocoles":
            for p in client.list_protocoles(mine_only=getattr(args, "mine", False)):
                print(f"  {p.get('_id')}  {p.get('titre') or p.get('nom')}")
            return 0

        if args.cmd == "participations":
            n = 0
            for p in client.list_participations(mine_only=getattr(args, "mine", False)):
                n += 1
                dd = p.date_debut.strftime("%Y-%m-%d") if p.date_debut else "?"
                print(f"  {p.id}  {dd}  site={p.site_id}  "
                      f"point={p.point}  état={p.traitement_etat}")
            print(f"\nTotal : {n} participation(s)")
            return 0

        if args.cmd == "participation":
            p = client.get_participation(args.id)
            import json as _json
            print(_json.dumps(p.raw, indent=2, ensure_ascii=False, default=str))
            return 0

        if args.cmd == "observations":
            out = args.out or Path.cwd() / f"participation-{args.id}-observations.xlsx"

            last_print = [0]
            def _progress(seen, total):
                import time as _t
                now = _t.monotonic()
                if now - last_print[0] > 0.5 or seen == total:
                    last_print[0] = now
                    pct = (seen / total * 100) if total else 0
                    print(f"\r  progress : {seen}/{total} fichiers ({pct:.1f}%)", end="", flush=True)

            print(f"Téléchargement → {out}")
            res = client.download_observations_as_xlsx(args.id, out, on_progress=_progress)
            print(f"\n✓ {res['n_files']} fichiers parsés  ·  {res['n_contacts']} contacts écrits  "
                  f"·  {res['n_silent_files']} silencieux")
            print(f"✓ {res['path']}")
            return 0
    except TokenExpiredError as e:
        print(f"❌ {e}\nRelance : se reconnecter au portail et refaire 'save-token'.", file=sys.stderr)
        return 2
    except NetworkError as e:
        print(f"❌ réseau : {e}", file=sys.stderr)
        return 3
    except ApiError as e:
        print(f"❌ API : {e}", file=sys.stderr)
        return 4

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
