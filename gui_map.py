"""
gui_map.py — panneau cartographique pour ChiroTool.

Utilise ``tkintermapview`` (widget carte basé sur OpenStreetMap).

Fonctionnalités v1 (lecture seule) :
  - Affiche tous les sites de l'utilisateur (obtenus via l'API ou depuis les
    manifests de session si pas de token)
  - Markers cliquables avec popup : nom du site, n° Tadarida, liste des points
  - Focus automatique quand une session est sélectionnée dans la sidebar
  - Sélecteur de fond de carte (OSM / satellite / hybride)
  - Cache des tuiles sous config/map_cache/ (utilisable offline après premier
    chargement)

Fonctionnalités v2 (hors scope) :
  - Création de site par clic (grille STOC)
  - Dessin des carrés 2×2 km
  - Édition de points existants
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import messagebox
from typing import Any

# `threading` utilisé par search/load_sites

import customtkinter as ctk

try:
    import tkintermapview
except ImportError:
    tkintermapview = None  # type: ignore

from credentials import load_token
from gui_config import config_dir


# Fonds de carte disponibles (server_url, max_zoom)
# IGN Géoportail : fonds de référence pour tout naturaliste français.
# Usage public libre sur data.geopf.fr (WMTS essentiels). Couches :
#   - ORTHOIMAGERY.ORTHOPHOTOS : photos aériennes haute résolution
#   - GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2 : carte topographique IGN (Scan25 équivalent)
TILE_SERVERS = {
    "OSM (OpenStreetMap)": (
        "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", 19),
    "IGN — Photos aériennes": (
        "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg"
        "&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}", 19),
    "IGN — Plan topo": (
        "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        "&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&FORMAT=image/png"
        "&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}", 18),
    "Satellite (Esri)": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        19),
    "OpenTopoMap (topo)": (
        "https://a.tile.opentopomap.org/{z}/{x}/{y}.png", 17),
}

# Défaut : OSM standard. Mieux caché, rendu plus rapide, tuiles plus légères
# que l'IGN (qui reste dispo dans le menu pour qui en a besoin ponctuellement).
# Retour utilisateur terrain : IGN Plan topo sature la bande passante pendant
# les zoom/dezoom, incompatible avec un usage "navigation fluide".
DEFAULT_TILE = "OSM (OpenStreetMap)"

# Zoom en dessous duquel on agrège les points en clusters
CLUSTER_ZOOM_THRESHOLD = 12
# Taille d'une cellule de grille en pixels écran (plus grand = clusters plus agressifs)
CLUSTER_GRID_PIXELS = 70

# -- Client Nominatim centralisé -------------------------------------------
# Politique Nominatim : 1 req/s max, User-Agent identifiant l'app avec contact.
# Sans ça, IP potentiellement bannie (app distribuée à plusieurs BE = risque).
# Cf. https://operations.osmfoundation.org/policies/nominatim/
try:
    from version import __version__ as _APP_VERSION, GITHUB_REPO_URL as _REPO_URL
    NOMINATIM_UA = f"ChiroTool/{_APP_VERSION} (+{_REPO_URL})"
except Exception:
    NOMINATIM_UA = "ChiroTool (+https://github.com/kevin-guille/ChiroTool)"
NOMINATIM_MIN_INTERVAL_S = 1.05  # petit buffer de sécurité au-dessus de 1 s


def _points_from_raw(raw: dict) -> list[dict]:
    """Extrait les points [{nom, lat, lon}] d'un site brut de l'API.

    ATTENTION : Vigie-Chiro stocke [lat, lon] (ordre NON-STANDARD GeoJSON qui
    attendrait [lon, lat]). Validé par recoupement avec le portail. Ne pas
    « corriger » (cf vigiechiro_api.py côté écriture).
    """
    pts: list[dict] = []
    for loc in raw.get("localites") or []:
        for g in (loc.get("geometries") or {}).get("geometries", []):
            if g.get("type") != "Point":
                continue
            coords = g.get("coordinates") or []
            if len(coords) >= 2:
                pts.append({
                    "nom": loc.get("nom", "?"),
                    "lat": float(coords[0]),
                    "lon": float(coords[1]),
                })
    return pts


def _external_sites_path():
    """Fichier mémorisant les carrés d'AUTRES observateurs où l'utilisateur a
    ajouté un point (l'API /moi/sites ne les liste pas → il faut les re-fetch
    par id pour qu'ils restent visibles sur la carte)."""
    from gui_config import config_dir
    return config_dir() / "external_sites.json"


def _load_external_site_ids() -> list[str]:
    try:
        import json
        p = _external_sites_path()
        if p.is_file():
            return [str(x) for x in json.loads(p.read_text(encoding="utf-8")) if x]
    except Exception:
        pass
    return []


def _remember_external_site_id(site_id: str) -> None:
    try:
        import json
        ids = _load_external_site_ids()
        if site_id and site_id not in ids:
            ids.append(site_id)
            _external_sites_path().write_text(json.dumps(ids), encoding="utf-8")
    except Exception:
        pass
_nominatim_lock = threading.Lock()
_nominatim_last_call = [0.0]  # [ts] — mutable closure-friendly
_nominatim_cache: dict[tuple, list[dict]] = {}  # (query_normalized, limit) → results
_nominatim_cache_max = 128


def nominatim_search(query: str, *, limit: int = 7, timeout: float = 8.0) -> list[dict]:
    """Recherche Nominatim respectant les règles d'usage (1 req/s, UA, cache).

    - Cache mémoire LRU-like (simple dict borné) pour éviter les allers-retours
      quand l'utilisateur efface et retape la même chaîne.
    - Verrou global pour sérialiser les requêtes à 1 req/s, évite la bannière.
    - Exceptions réseau propagées au caller (qui décide d'afficher/ignorer).
    """
    import time
    import requests
    key = (query.strip().lower(), limit)
    if key in _nominatim_cache:
        return _nominatim_cache[key]
    with _nominatim_lock:
        # Attente minimale entre deux appels
        elapsed = time.monotonic() - _nominatim_last_call[0]
        if elapsed < NOMINATIM_MIN_INTERVAL_S:
            time.sleep(NOMINATIM_MIN_INTERVAL_S - elapsed)
        try:
            r = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": limit,
                         "countrycodes": "fr", "addressdetails": 0,
                         "accept-language": "fr"},
                headers={"User-Agent": NOMINATIM_UA},
                timeout=timeout,
            )
            _nominatim_last_call[0] = time.monotonic()
            r.raise_for_status()
            data = r.json()
        except Exception:
            # On garde la fenêtre de rate-limit à jour même en cas d'erreur
            _nominatim_last_call[0] = time.monotonic()
            raise
    # Cache (borné). Éviction FIFO naïve quand plein.
    if len(_nominatim_cache) >= _nominatim_cache_max:
        try:
            _nominatim_cache.pop(next(iter(_nominatim_cache)))
        except StopIteration:
            pass
    _nominatim_cache[key] = data
    return data


_reverse_cache: dict[tuple, str] = {}


def reverse_commune(lat: float, lon: float, *, timeout: float = 8.0) -> str | None:
    """Commune (ville/village) depuis des coordonnées via Nominatim reverse.

    Mêmes règles d'usage (1 req/s, User-Agent, cache). Retourne None si
    introuvable ou en cas d'erreur réseau (jamais d'exception propagée).
    """
    import time
    import requests
    key = (round(float(lat), 4), round(float(lon), 4))
    if key in _reverse_cache:
        return _reverse_cache[key]
    with _nominatim_lock:
        elapsed = time.monotonic() - _nominatim_last_call[0]
        if elapsed < NOMINATIM_MIN_INTERVAL_S:
            time.sleep(NOMINATIM_MIN_INTERVAL_S - elapsed)
        try:
            r = requests.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lon, "format": "jsonv2",
                         "zoom": 10, "addressdetails": 1, "accept-language": "fr"},
                headers={"User-Agent": NOMINATIM_UA},
                timeout=timeout,
            )
            _nominatim_last_call[0] = time.monotonic()
            r.raise_for_status()
            data = r.json()
        except Exception:
            _nominatim_last_call[0] = time.monotonic()
            return None
    addr = (data or {}).get("address") or {}
    commune = (addr.get("city") or addr.get("town") or addr.get("village")
               or addr.get("municipality") or addr.get("hamlet"))
    if commune:
        if len(_reverse_cache) >= _nominatim_cache_max:
            try:
                _reverse_cache.pop(next(iter(_reverse_cache)))
            except StopIteration:
                pass
        _reverse_cache[key] = commune
    return commune


class MapPanel(ctk.CTkFrame):
    """Panneau carte intégrable dans la GUI."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        if tkintermapview is None:
            self._build_missing_widget()
            return

        self._sites_loaded = False
        self._sites_cache: list[dict] = []
        self._markers: list = []
        self._polygons: list = []
        self._current_focus: str | None = None
        self._add_point_mode = False
        self._add_point_marker = None
        self._carre_preview_markers: list = []   # points du carré résolu (aperçu)
        # Registre optionnel pour colorer les markers selon l'état des sites.
        # Alimenté via set_registry() par gui_app au changement de workspace.
        self._registry = None
        self._site_states_cache: dict[str, str] = {}
        # Fiche récap overlay ouverte au clic sur un marker
        self._point_popup: ctk.CTkFrame | None = None
        self._point_popup_bind_id: str | None = None
        # Cache des participations API (indexé par site_id), peuplé au 1er
        # chargement des sites. Permet à la fiche récap d'afficher l'historique
        # même sans avoir lancé « Sync API » explicitement dans le Registre.
        self._api_participations_by_site: dict[str, list[dict]] = {}

        self._build_ui()

    def set_registry(self, registry) -> None:
        """Injecte une Registry pour enrichir le rendu (couleur markers).

        Appelé par gui_app.ChiroToolApp au changement de workspace. None = pas
        d'enrichissement (markers bleu par défaut).
        """
        self._registry = registry
        self._site_states_cache.clear()
        # Re-render si des markers sont déjà posés
        if self._sites_cache:
            try:
                self._render_markers()
            except Exception:
                pass

    def _state_for_site(self, site: dict) -> str:
        """Retourne l'état agrégé du site : 'done' / 'in_progress' / 'idle'.

        - 'done'        : au moins 1 participation TERMINE cette année
        - 'in_progress' : participation EN_COURS ou PLANIFIE
        - 'idle'        : aucune participation connue → site "à travailler"
        """
        numero = site.get("numero") or ""
        if not numero or self._registry is None:
            return "idle"
        if numero in self._site_states_cache:
            return self._site_states_cache[numero]
        state = "idle"
        try:
            from datetime import datetime
            year = datetime.now().year
            conn = self._registry._get_conn()
            rows = conn.execute(
                "SELECT api_etat, date_debut FROM sessions "
                "WHERE n_site_tadarida=? AND api_etat IS NOT NULL",
                (numero,),
            ).fetchall()
            etats_this_year = []
            for r in rows:
                d = r["date_debut"] or ""
                # On tolère les dates ISO ou "YYYY-MM-DD..."
                if d[:4] == str(year):
                    etats_this_year.append(r["api_etat"])
            if any(e in ("TERMINE", "FINI") for e in etats_this_year):
                state = "done"
            elif any(e in ("EN_COURS", "PLANIFIE") for e in etats_this_year):
                state = "in_progress"
        except Exception:
            state = "idle"
        self._site_states_cache[numero] = state
        return state

    # -- UI -----------------------------------------------------------------

    def _build_missing_widget(self):
        """Affiche un message d'erreur si tkintermapview manque."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        msg = ctk.CTkLabel(
            self,
            text=("La carte nécessite le module tkintermapview.\n"
                  "Installe-le avec :\n\n"
                  "    pip install tkintermapview"),
            font=ctk.CTkFont(size=13),
            justify="center",
        )
        msg.grid(row=0, column=0)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Barre de contrôle
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ctrl.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(ctrl, text="Fond :",
                      font=ctk.CTkFont(size=11)).grid(row=0, column=0, padx=(0, 4))

        self.tile_var = ctk.StringVar(value=DEFAULT_TILE)
        tile_menu = ctk.CTkOptionMenu(
            ctrl, variable=self.tile_var, width=220, height=28,
            values=list(TILE_SERVERS.keys()),
            command=self._on_tile_change,
        )
        tile_menu.grid(row=0, column=1, padx=(0, 8))

        self.reload_btn = ctk.CTkButton(
            ctrl, text="⟳ Recharger sites", height=28, width=140,
            command=self._on_reload_sites,
        )
        self.reload_btn.grid(row=0, column=2, padx=(0, 8))

        self.add_point_btn = ctk.CTkButton(
            ctrl, text="➕ Ajouter un point", height=28, width=160,
            command=self._toggle_add_point_mode,
        )
        self.add_point_btn.grid(row=0, column=3, padx=(0, 8))

        # Boutons de navigation rapide : recentrer sur la France / tous mes sites.
        # Utiles quand l'utilisateur s'est perdu en zoomant très loin.
        self.home_btn = ctk.CTkButton(
            ctrl, text="🏠", height=28, width=36,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._view_france,
        )
        self.home_btn.grid(row=0, column=5, padx=(0, 4))

        self.fit_sites_btn = ctk.CTkButton(
            ctrl, text="📍 Mes sites", height=28, width=100,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._view_all_sites,
        )
        self.fit_sites_btn.grid(row=0, column=6, padx=(0, 0))

        # Seconde ligne : recherche d'adresse/commune avec autocomplétion
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            ctrl, textvariable=self.search_var, height=28,
            placeholder_text="🔍  Rechercher une commune, une adresse… "
                               "(autocomplétion après 3 lettres)",
        )
        self.search_entry.grid(row=1, column=0, columnspan=4,
                                 sticky="ew", padx=(0, 8), pady=(4, 0))
        self.search_entry.bind("<Return>", lambda e: self._on_search())
        # Autocomplétion : déclenche après saisie (debounce 400 ms)
        self.search_var.trace_add("write", self._on_search_type)
        self._autocomplete_after = None
        self._last_query = ""

        self.search_btn = ctk.CTkButton(
            ctrl, text="Rechercher", height=28, width=110,
            command=self._on_search,
        )
        self.search_btn.grid(row=1, column=4, sticky="w", pady=(4, 0))

        # Dropdown d'autocomplétion (créé à la demande, positionné sur la carte)
        self.suggestions_box: ctk.CTkFrame | None = None

        self.status_lbl = ctk.CTkLabel(
            ctrl, text="(pas de sites chargés)",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
            anchor="e",
        )
        self.status_lbl.grid(row=0, column=4, sticky="e", padx=(8, 0))

        # Carte (pas de corner_radius : bug avec fg transparent du parent)
        cache_path = config_dir() / "map_cache.db"
        self.map = tkintermapview.TkinterMapView(
            self, corner_radius=0,
            database_path=str(cache_path),
        )
        self.map.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # Position par défaut : centre de la France métropolitaine
        self.map.set_position(46.8, 2.4)
        self.map.set_zoom(6)
        # Appliquer le tile server par défaut
        self._on_tile_change(DEFAULT_TILE)

    # -- Tiles --------------------------------------------------------------

    def _on_tile_change(self, choice: str):
        url, max_zoom = TILE_SERVERS.get(choice, TILE_SERVERS[DEFAULT_TILE])
        try:
            self.map.set_tile_server(url, max_zoom=max_zoom)
        except Exception:
            pass

    # -- Chargement des sites ----------------------------------------------

    def load_sites_async(self):
        """Charge les sites en arrière-plan (API si token, sinon manifests)."""
        if self._sites_loaded:
            return
        self._sites_loaded = True
        self.status_lbl.configure(text="chargement…")

        def _worker():
            try:
                sites = self._fetch_sites()
            except Exception as e:
                self.after(0, lambda: self.status_lbl.configure(
                    text=f"erreur : {e}",
                    text_color=("#cf222e", "#f85149")))
                return
            self.after(0, lambda: self._on_sites_loaded(sites))

        threading.Thread(target=_worker, daemon=True).start()

    def _fetch_sites(self) -> list[dict]:
        """
        Retourne une liste de dicts avec :
            {id, numero, titre, protocole, points: [{nom, lat, lon}, ...]}
        """
        token = load_token()
        if not token:
            # Fallback : à partir des manifests connus dans le workspace courant
            return self._fetch_from_manifests()

        try:
            from vigiechiro_api import VigieChiroClient
            client = VigieChiroClient(token)
            out = []
            import re
            for raw in client.iter_sites(mine_only=True):
                titre = raw.get("titre") or ""
                m = re.search(r"-(\d{5,6})\s*$", titre)   # n° Tadarida depuis le titre
                out.append({
                    "id": raw.get("_id") or "",
                    "numero": m.group(1).zfill(6) if m else None,
                    "titre": titre,
                    "points": _points_from_raw(raw),
                    "is_mine": True,
                })

            # Récupère aussi les participations de l'utilisateur pour nourrir
            # les fiches récap au clic sur un marker. Mis en cache indexé
            # par site_id pour retrouver vite. Sans ça, la fiche dirait
            # "aucune nuit enregistrée" alors que le site a bien un
            # historique côté serveur (mais pas encore dans le registre local).
            self._api_participations_by_site: dict[str, list[dict]] = {}
            try:
                for p in client.iter_participations(mine_only=True):
                    site_ref = p.get("site")
                    # "site" peut être soit un string (ObjectId) soit un dict
                    # embedded selon l'état de la réponse Eve
                    if isinstance(site_ref, dict):
                        sid = site_ref.get("_id") or ""
                    else:
                        sid = str(site_ref) if site_ref else ""
                    if not sid:
                        continue
                    self._api_participations_by_site.setdefault(sid, []).append(p)
            except Exception:
                # Fetch participations non critique : la carte marche
                # sans (on tombera sur le fallback registre local).
                pass

            # Carrés EXTERNES : appartenant à d'autres observateurs, sur lesquels
            # l'utilisateur a ajouté un point. /moi/sites ne les liste pas, on
            # les re-fetch par id pour qu'ils restent visibles (marqués is_mine=False).
            own_ids = {s["id"] for s in out}
            for ext_id in _load_external_site_ids():
                if not ext_id or ext_id in own_ids:
                    continue
                try:
                    raw = client.get_site_raw(ext_id)
                except Exception:
                    continue
                titre = raw.get("titre") or ""
                m = re.search(r"-(\d{5,6})\s*$", titre)
                out.append({
                    "id": raw.get("_id") or ext_id,
                    "numero": m.group(1).zfill(6) if m else None,
                    "titre": titre,
                    "points": _points_from_raw(raw),
                    "is_mine": False,
                })
            return out
        except Exception as e:
            # Fallback silencieux si l'API échoue
            return self._fetch_from_manifests()

    def _fetch_from_manifests(self) -> list[dict]:
        """Tente de récupérer les sites depuis les manifests + API sans points GPS."""
        # Sans token ni accès local fiable, on retourne vide
        # (dans une vraie v2, on pourrait extraire depuis raw des manifests qui
        # ont vigiechiro_site_id mémorisé et refaire un get_site avec token)
        return []

    # -- Markers ------------------------------------------------------------

    def _clear_markers(self):
        # Ferme le popup ouvert : il pointait potentiellement vers un marker
        # qui va être détruit, l'overlay resterait orphelin sinon.
        try:
            self._close_point_popup()
        except Exception:
            pass
        for m in self._markers:
            try:
                m.delete()
            except Exception:
                pass
        self._markers.clear()
        for p in self._polygons:
            try:
                p.delete()
            except Exception:
                pass
        self._polygons.clear()

    # -- Clustering --------------------------------------------------------

    def _flat_points(self) -> list[tuple[float, float, dict, dict]]:
        """Aplatit self._sites_cache en liste (lat, lon, site, point)."""
        out = []
        for site in self._sites_cache:
            for pt in site["points"]:
                out.append((pt["lat"], pt["lon"], site, pt))
        return out

    def _compute_clusters(self, zoom: int) -> tuple[list, list]:
        """Retourne (clusters, singletons).

        - clusters  : [(lat_cent, lon_cent, n, [points_in_cluster])]
        - singletons: [(lat, lon, site, point)] — quand n=1 ou zoom ≥ seuil
        """
        points = self._flat_points()
        if zoom >= CLUSTER_ZOOM_THRESHOLD or len(points) < 20:
            # Pas de clustering : tous les points en singletons
            return [], points

        # Grid en degrés selon le zoom (taille de cellule ∝ 2^(-zoom))
        # À zoom 6 : ~1.4° par cellule ; à zoom 10 : ~0.09° ; à zoom 11 : ~0.04°
        # Formule simplifiée : cellule_deg = CLUSTER_GRID_PIXELS × 360 / (256 × 2^zoom)
        cell_deg = CLUSTER_GRID_PIXELS * 360.0 / (256.0 * (2 ** zoom))

        buckets: dict[tuple[int, int], list] = {}
        for lat, lon, site, pt in points:
            key = (int(lat / cell_deg), int(lon / cell_deg))
            buckets.setdefault(key, []).append((lat, lon, site, pt))

        clusters: list = []
        singletons: list = []
        for _key, items in buckets.items():
            if len(items) == 1:
                singletons.append(items[0])
            else:
                avg_lat = sum(i[0] for i in items) / len(items)
                avg_lon = sum(i[1] for i in items) / len(items)
                clusters.append((avg_lat, avg_lon, len(items), items))
        return clusters, singletons

    def _render_markers(self, *, precomputed: tuple | None = None):
        """Dessine les markers selon le zoom courant (singletons + clusters).

        ``precomputed`` : si fourni, évite de recalculer les clusters (gain
        sur gros volumes). Passé par _check_zoom après vérification signature.
        """
        self._clear_markers()
        if precomputed is not None:
            clusters, singletons = precomputed
        else:
            try:
                zoom = int(self.map.zoom)
            except Exception:
                zoom = 10
            clusters, singletons = self._compute_clusters(zoom)

        # Gestion des labels :
        # - Zoom "fort" (>= 11) : labels toujours visibles (utilisateur est en
        #   vue locale, peu de points à l'écran, label lisible)
        # - Zoom "moyen" (8-10) : labels visibles si pas trop denses (< 40
        #   singletons retournés par le clustering)
        # - Zoom "faible" (< 8) : labels cachés pour ne pas surcharger la vue
        #   France/région (les pastilles colorées suffisent, infos dispos au clic)
        try:
            zoom_now = int(self.map.zoom)
        except Exception:
            zoom_now = 10
        if zoom_now >= 11:
            hide_labels = False
        elif zoom_now >= 8:
            hide_labels = len(singletons) > 40
        else:
            hide_labels = True

        # Markers singletons — coloration selon l'état du site cette année :
        #   done        → vert (participation TERMINE)
        #   in_progress → orange (EN_COURS ou PLANIFIE)
        #   idle        → bleu (site disponible, pas encore travaillé cette année)
        state_colors = {
            "done":        ("#2ea043", "#1a6e2b", "#0f4419"),   # vert
            "in_progress": ("#f2a93b", "#a0651c", "#6a400c"),   # orange
            "idle":        ("#1f6feb", "#0d419d", "#0d419d"),   # bleu (défaut)
        }
        # Carré appartenant à un AUTRE observateur (point ajouté par l'utilisateur) :
        # violet, pour le distinguer de ses propres carrés.
        external_c = ("#8957e5", "#5a2ca0", "#3d1e6d")
        for lat, lon, site, pt in singletons:
            is_mine = site.get("is_mine", True)
            if hide_labels:
                title = ""  # pas de texte : rendu beaucoup plus rapide
            else:
                title = f"{pt['nom']}"
                if site.get("numero"):
                    title = f"#{site['numero']} · {pt['nom']}"
                if not is_mine:
                    title += "  (autre obs.)"
            if not is_mine:
                circle_c, outside_c, text_c = external_c
            else:
                state = self._state_for_site(site)
                circle_c, outside_c, text_c = state_colors.get(
                    state, state_colors["idle"])
            marker = self.map.set_marker(
                lat, lon,
                text=title,
                marker_color_circle=circle_c,
                marker_color_outside=outside_c,
                text_color=text_c,
                # Callback clic : ouvre la fiche récap du point.
                # tkintermapview passe le marker en 1er argument, on capture
                # site+pt via défaut de lambda pour éviter la late-binding.
                command=lambda _m, s=site, p=pt: self._show_point_popup(s, p),
            )
            self._markers.append(marker)

        # Markers clusters (orange, avec nombre)
        for lat, lon, n, items in clusters:
            cluster_marker = self.map.set_marker(
                lat, lon,
                text=f"● {n} points",
                marker_color_circle="#e67e22",
                marker_color_outside="#a35014",
                text_color="#7a3c0e",
                command=lambda m, la=lat, lo=lon: self._on_cluster_click(la, lo),
            )
            self._markers.append(cluster_marker)

    def _on_sites_loaded(self, sites: list[dict]):
        self._sites_cache = sites

        total_points = sum(len(s["points"]) for s in sites)
        lats = [pt["lat"] for s in sites for pt in s["points"]]
        lons = [pt["lon"] for s in sites for pt in s["points"]]

        # Auto-centrer sur l'ensemble AVANT de dessiner (pour que le clustering
        # utilise le bon zoom)
        if lats and lons:
            avg_lat = sum(lats) / len(lats)
            avg_lon = sum(lons) / len(lons)
            self.map.set_position(avg_lat, avg_lon)
            if len(lats) == 1:
                self.map.set_zoom(14)
            else:
                span = max(max(lats) - min(lats), max(lons) - min(lons))
                if span < 0.01:    self.map.set_zoom(14)
                elif span < 0.1:   self.map.set_zoom(12)
                elif span < 1:     self.map.set_zoom(9)
                elif span < 5:     self.map.set_zoom(7)
                else:              self.map.set_zoom(6)

        self._render_markers()
        self._schedule_zoom_watch()

        if sites:
            self.status_lbl.configure(
                text=f"{len(sites)} site(s) · {total_points} point(s)",
                text_color=("gray40", "gray60"),
            )
        else:
            self.status_lbl.configure(
                text="aucun site chargé (token API absent ou pas de sites)",
                text_color=("gray40", "gray60"),
            )

    # -- Watcher du zoom : re-clusterise quand le zoom change --------------
    #
    # Stratégie anti-lag (pour les comptes avec 250+ sites) :
    # 1. Poll à 400ms pour détecter un zoom "en cours" (intervalle moins
    #    gourmand qu'un 250ms serré)
    # 2. Re-render UNIQUEMENT quand le zoom se stabilise (pas de changement
    #    pendant 3 ticks consécutifs ≈ 1.2s stable). Retour utilisateur :
    #    le zoom/dezoom rapide saturait la bande passante avec des requêtes
    #    de tuiles + re-render markers — on attend maintenant franchement
    #    l'arrêt avant de bouger.
    # 3. Skip si la signature de clustering reste identique entre 2 niveaux
    #    de zoom voisins.
    # Résultat : pendant que l'utilisateur dézoome activement, zéro re-render.
    # Le re-render se fait une seule fois après relâchement prolongé.

    def _schedule_zoom_watch(self):
        """Démarre (ou relance) la boucle de surveillance du zoom."""
        if not hasattr(self, "_last_rendered_zoom"):
            self._last_rendered_zoom = None
            self._last_observed_zoom = None
            self._zoom_stable_ticks = 0
            self._last_cluster_signature: tuple | None = None
        self.after(400, self._check_zoom)

    def _check_zoom(self):
        """Appelé périodiquement : re-rend quand le zoom se stabilise."""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if not self._sites_cache:
            self.after(250, self._check_zoom)
            return
        try:
            zoom = int(self.map.zoom)
        except Exception:
            zoom = 0

        # Détection de stabilité : le zoom doit rester identique 3 ticks de suite
        if zoom == self._last_observed_zoom:
            self._zoom_stable_ticks += 1
        else:
            self._zoom_stable_ticks = 0
            self._last_observed_zoom = zoom

        # Déclenche le re-render uniquement si :
        #  - zoom stabilisé (≥ 3 ticks au même niveau, ~1.2s)
        #  - ET différent du dernier niveau effectivement rendu
        if (self._zoom_stable_ticks >= 3
                and zoom != self._last_rendered_zoom):
            # Avant le render lourd, vérifie si la signature de clustering a
            # réellement changé. Deux zooms voisins peuvent donner les mêmes
            # buckets → inutile de détruire/recréer tous les markers.
            try:
                clusters, singletons = self._compute_clusters(zoom)
                sig = (
                    zoom < CLUSTER_ZOOM_THRESHOLD,
                    len(singletons),
                    len(clusters),
                    tuple(round(la, 2) for la, _lo, _n, _i in clusters[:20]),
                )
            except Exception:
                sig = (zoom,)

            if sig != self._last_cluster_signature:
                self._last_cluster_signature = sig
                try:
                    self._render_markers(precomputed=(clusters, singletons))
                except TypeError:
                    # Fallback si on n'accepte pas le kwarg
                    self._render_markers()
                except Exception:
                    pass
            self._last_rendered_zoom = zoom

        try:
            self.after(400, self._check_zoom)
        except Exception:
            pass

    def _on_cluster_click(self, lat: float, lon: float):
        """Clic sur un cluster → zoom in à la position."""
        try:
            current_zoom = int(self.map.zoom)
        except Exception:
            current_zoom = 10
        # Zoom d'1 cran à la fois pour animation douce
        new_zoom = min(19, current_zoom + 2)
        self.map.set_position(lat, lon)
        self.map.set_zoom(new_zoom)

    # -- Fiche récap au clic sur un marker ---------------------------------

    def _show_point_popup(self, site: dict, pt: dict):
        """Affiche une fiche overlay avec l'historique du point.

        Implémentation : CTkToplevel sans bordure (overrideredirect). C'est
        une *vraie* fenêtre OS, garantie au-dessus du canvas de la carte
        sans bataille de z-order. Essayé précédemment avec place() dans un
        CTkFrame : non-visible sous tkintermapview qui dessine par-dessus.
        """
        # Ferme l'éventuel popup précédent
        self._close_point_popup()

        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)   # pas de barre de titre système
        popup.attributes("-topmost", True)  # reste au-dessus

        # Positionnement : collé en haut-gauche de la zone carte
        try:
            mx = self.map.winfo_rootx()
            my = self.map.winfo_rooty()
        except Exception:
            mx, my = self.winfo_rootx(), self.winfo_rooty()
        popup.geometry(f"380x420+{mx + 14}+{my + 14}")

        # Cadre interne pour avoir l'apparence CTk (bordure, radius)
        frame = ctk.CTkFrame(
            popup, corner_radius=8,
            fg_color=("white", "gray18"),
            border_width=1,
            border_color=("gray70", "gray35"),
        )
        frame.pack(fill="both", expand=True, padx=0, pady=0)
        frame.grid_columnconfigure(0, weight=1)
        self._point_popup = popup
        self._point_popup_frame = frame

        # --- Header (tous les enfants sont ajoutés dans `frame` pour qu'ils
        #     bénéficient du style CTk et du fill; popup = Toplevel nue)
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        header.grid_columnconfigure(0, weight=1)

        # Nom du contrat : priorité au nom_contrat du registre local (le plus
        # parlant pour un BE, ex: "Contrat Isle d'Abeau ZAC"), fallback sur le
        # commentaire de la 1ère participation API, fallback sur le titre
        # Vigiechiro nettoyé ("Point Fixe" générique).
        contrat_label = self._resolve_contract_label(site, pt)

        ctk.CTkLabel(
            header,
            text=f"📍 {pt['nom']}",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header, text="✕", width=28, height=24,
            fg_color="transparent",
            text_color=("gray40", "gray60"),
            hover_color=("gray90", "gray28"),
            command=self._close_point_popup,
        ).grid(row=0, column=1, sticky="e", padx=(6, 0))

        # Sous-titre : contrat + n° site
        # Sous-titre : contrat + n° site. La ligne des coordonnées est à part
        # pour supporter le clic-copier (hint au hover).
        sub = []
        if contrat_label and contrat_label != "(site)":
            sub.append(contrat_label)
        if site.get("numero"):
            sub.append(f"site #{site['numero']}")
        ctk.CTkLabel(
            frame,
            text="  ·  ".join(sub) if sub else "(site)",
            font=ctk.CTkFont(size=11),
            text_color=("gray35", "gray65"),
            anchor="w", justify="left", wraplength=330,
        ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 2))

        # Coordonnées cliquables (copie dans le presse-papier)
        try:
            coords_text = f"📋 {float(pt['lat']):.5f}, {float(pt['lon']):.5f}"
            coords_raw = f"{float(pt['lat']):.5f}, {float(pt['lon']):.5f}"
        except Exception:
            coords_text = ""
            coords_raw = ""
        if coords_text:
            coords_lbl = ctk.CTkLabel(
                frame, text=coords_text,
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color=("gray50", "gray55"),
                anchor="w", cursor="hand2",
            )
            coords_lbl.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))

            def _copy_coords(_e=None, text=coords_raw, lbl=coords_lbl):
                try:
                    self.clipboard_clear()
                    self.clipboard_append(text)
                    self.update_idletasks()  # flush clipboard sans re-entrer l'event loop
                    lbl.configure(text=f"✓  copié : {text}")
                    lbl.after(1500, lambda: lbl.configure(
                        text=f"📋 {text}"))
                except Exception:
                    pass

            coords_lbl.bind("<Button-1>", _copy_coords)

        # --- Historique (sessions du registre + cache API)
        sessions = self._get_point_history(site, pt)

        sep = ctk.CTkFrame(frame, height=1, fg_color=("gray80", "gray30"))
        sep.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))

        # Ligne de stats globales (total nuits + dernière date)
        stats_lbl = ctk.CTkLabel(
            frame,
            text=self._format_history_summary(sessions),
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
        )
        stats_lbl.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 2))

        # Bilan "saison en cours" : quels passages sont faits, lesquels manquent.
        # Ex: "Saison 2026 : Pass1 ✓ · Pass2 à faire"
        season_info = self._format_current_season(sessions)
        if season_info:
            ctk.CTkLabel(
                frame, text=season_info,
                font=ctk.CTkFont(size=11),
                text_color=("gray35", "gray70"),
                anchor="w", wraplength=330, justify="left",
            ).grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 6))

        if sessions:
            # Hauteur adaptée : ~48 px/ligne + ~28 px par header d'année
            years = {str(s.get("date_debut") or "????")[:4] for s in sessions}
            approx_h = 48 * len(sessions) + 28 * len(years)
            body_container = ctk.CTkScrollableFrame(
                frame, fg_color="transparent",
                height=min(280, max(80, approx_h)),
            )
            body_container.grid(row=6, column=0, sticky="ew", padx=6, pady=(0, 8))
            body_container.grid_columnconfigure(0, weight=1)

            # Grouping par année : header "══ 2025 ══" entre chaque bloc
            current_year: str | None = None
            row_idx = 0
            for s in sessions:
                year = str(s.get("date_debut") or "????")[:4]
                if year != current_year:
                    current_year = year
                    self._build_year_header(body_container, row_idx, year)
                    row_idx += 1
                self._build_session_row(body_container, row_idx, s)
                row_idx += 1
        else:
            ctk.CTkLabel(
                frame,
                text="(aucune session enregistrée localement pour ce point)",
                font=ctk.CTkFont(size=11, slant="italic"),
                text_color=("gray50", "gray60"),
                anchor="w", wraplength=330,
            ).grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 12))

        # Rendu robuste sur Windows : withdraw + configure + deiconify évite
        # les fenêtres fantômes à (0,0) en mode overrideredirect.
        try:
            popup.update_idletasks()
            popup.deiconify()
            popup.lift()
            popup.focus_force()
        except Exception:
            pass

        # --- Fermeture par clic ailleurs sur la carte + Échap
        #
        # IMPORTANT : on retarde l'attachement des binds de 300 ms, car le
        # clic qui vient d'ouvrir le popup se propage ENCORE pendant qu'on
        # construit la fenêtre. S'il atterrit sur `<Button-1>` du canvas
        # maintenant, le handler de fermeture se déclenche juste après la
        # création → popup invisible parce que fermé immédiatement.
        def _attach_close_handlers():
            if self._point_popup is None:
                return
            try:
                self._point_popup_bind_id = self.map.canvas.bind(
                    "<Button-1>", self._on_map_click_outside_popup, add="+")
            except Exception:
                self._point_popup_bind_id = None
            try:
                self._point_popup_esc_id = self.winfo_toplevel().bind(
                    "<Escape>", lambda _e: self._close_point_popup(), add="+")
            except Exception:
                self._point_popup_esc_id = None

        self.after(300, _attach_close_handlers)

    def _resolve_contract_label(self, site: dict, pt: dict) -> str:
        """Retourne le libellé humain du site pour le header de la fiche."""
        numero = site.get("numero") or ""
        point_name = (pt.get("nom") or "").upper()

        # 1. Registre local : le nom_contrat est le vrai nom "business" saisi
        # par le BE dans son Suivi ou dans le wizard (ex: "Contrat X - ZAC Y").
        if self._registry is not None and numero:
            try:
                conn = self._registry._get_conn()
                row = conn.execute(
                    "SELECT nom_contrat FROM sessions "
                    "WHERE n_site_tadarida=? AND UPPER(n_point_fixe)=? "
                    "AND nom_contrat IS NOT NULL AND nom_contrat<>'' "
                    "ORDER BY date_debut DESC LIMIT 1",
                    (numero, point_name),
                ).fetchone()
                if row and row["nom_contrat"]:
                    return row["nom_contrat"]
            except Exception:
                pass

        # 2. Commentaire d'une participation API (souvent renseigné)
        site_id = site.get("id") or ""
        for p in self._api_participations_by_site.get(site_id, []):
            c = (p.get("commentaire") or "").strip()
            if c and len(c) <= 80:  # on skip les commentaires trop longs
                return c

        # 3. Fallback : titre Vigiechiro nettoyé
        titre = site.get("titre") or ""
        try:
            import re
            cleaned = re.sub(r"\s*-\s*\d{5,6}\s*$", "", titre).strip()
            cleaned = re.sub(r"^\s*Vigiechiro\s*-\s*", "", cleaned).strip()
            if cleaned:
                return cleaned
        except Exception:
            pass
        return "(site)"

    def _get_point_history(self, site: dict, pt: dict) -> list[dict]:
        """Retourne l'historique d'un (site, point) en fusionnant :

        1. le registre SQLite local (sessions avec fichiers WAV traités)
        2. le cache API `_api_participations_by_site` (peuplé au chargement
           de la carte, inclut les participations que l'utilisateur n'a pas
           encore synchronisées explicitement dans le Registre)

        Les doublons sont fusionnés par `vigiechiro_participation_id`. La liste
        est triée par date décroissante.
        """
        numero = site.get("numero") or ""
        point_name = (pt.get("nom") or "").upper()

        # 1. Registre local (priorité : il a les infos enr, série, état local)
        local_sessions: list[dict] = []
        seen_pids: set[str] = set()
        if self._registry is not None and numero:
            try:
                conn = self._registry._get_conn()
                rows = conn.execute(
                    "SELECT date_debut, n_passage, n_enregistreur, n_serie, "
                    "api_etat, nom_contrat, canonical_name, n_site_tadarida, "
                    "vigiechiro_participation_id, source "
                    "FROM sessions "
                    "WHERE n_site_tadarida=? AND UPPER(n_point_fixe)=? "
                    "ORDER BY date_debut DESC",
                    (numero, point_name),
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    local_sessions.append(d)
                    pid = d.get("vigiechiro_participation_id")
                    if pid:
                        seen_pids.add(pid)
            except Exception:
                pass

        # 2. Cache API pour ce site (via site_id : valeur 'id' dans notre dict)
        site_id = site.get("id") or ""
        api_extras: list[dict] = []
        for p in self._api_participations_by_site.get(site_id, []):
            pid = p.get("_id") or ""
            if pid in seen_pids:
                continue  # déjà dans le registre local
            api_point = (p.get("point") or "").upper()
            if api_point != point_name:
                continue
            # Normalise le format pour partager le même affichage
            traitement = p.get("traitement") or {}
            config = p.get("configuration") or {}
            api_extras.append({
                "date_debut": p.get("date_debut") or "",
                "date_fin": p.get("date_fin") or "",
                "n_passage": p.get("numero_passage")
                             or p.get("n_passage"),
                "n_enregistreur": None,  # inconnu côté API (libre)
                "n_serie": config.get("detecteur_enregistreur_serie"),
                "api_etat": traitement.get("etat"),
                "nom_contrat": None,
                "canonical_name": f"[API] {p.get('date_debut', '?')[:10]}",
                "n_site_tadarida": numero,
                "vigiechiro_participation_id": pid,
                "source": "server",
                # Champs supplémentaires que la fiche peut afficher
                "_api_detecteur": config.get("detecteur_enregistreur_type"),
                "_api_micro0": config.get("micro0_modele"),
                "_api_meteo": p.get("meteo") or {},
                "_api_commentaire": p.get("commentaire"),
            })

        # Fusion + tri décroissant par date_debut
        all_sessions = local_sessions + api_extras
        all_sessions.sort(key=lambda s: str(s.get("date_debut") or ""),
                           reverse=True)
        return all_sessions

    def _format_history_summary(self, sessions: list[dict]) -> str:
        """Une ligne : '3 nuits · dernière : 2025-07-12'."""
        n = len(sessions)
        if n == 0:
            return "Aucune nuit enregistrée"
        last = sessions[0].get("date_debut") or ""
        last_short = str(last)[:10] if last else "?"
        word = "nuit" if n == 1 else "nuits"
        return f"🌙  {n} {word}  ·  dernière : {last_short}"

    def _format_current_season(self, sessions: list[dict]) -> str:
        """Bilan de la saison en cours : Pass1 / Pass2 faits ou manquants.

        Protocole Vigie-Chiro Point Fixe = 2 passages par an (juin + juillet
        typiquement). On regarde uniquement l'année courante. Si rien cette
        année, on indique "Saison YYYY : aucune nuit". Sinon : pour chaque
        passage observé, ✓ ; pour les passages 1 et 2 manquants, "à faire".
        """
        from datetime import datetime
        year_now = datetime.now().year
        this_year = [s for s in sessions
                       if str(s.get("date_debut") or "")[:4] == str(year_now)]
        if not this_year:
            return f"Saison {year_now} : aucune nuit"

        # Passages faits cette année (set de n_passage ; on ignore les None)
        passes_done: set[int] = set()
        for s in this_year:
            p = s.get("n_passage")
            if p is not None:
                try:
                    passes_done.add(int(p))
                except (TypeError, ValueError):
                    pass

        parts = [f"Saison {year_now} :"]
        if not passes_done:
            # Nuits cette année mais passages inconnus (API qui ne renvoie
            # pas numero_passage par ex) → on affiche juste le nombre.
            n = len(this_year)
            parts.append(f"{n} nuit(s)")
            return "  ".join(parts)
        # Affichage Pass1/Pass2 (les plus courants). On affiche aussi les autres
        # passages observés (Pass3+ sont rares mais possibles).
        for p in (1, 2):
            if p in passes_done:
                parts.append(f"Pass{p} ✓")
            else:
                parts.append(f"Pass{p} à faire")
        extras = sorted(passes_done - {1, 2})
        for p in extras:
            parts.append(f"Pass{p} ✓")
        return "  ·  ".join(parts)

    def _build_year_header(self, parent, row_idx: int, year: str):
        """Séparateur visuel entre les blocs d'années dans l'historique."""
        hdr = ctk.CTkLabel(
            parent,
            text=f"─── {year} ───",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=("gray45", "gray55"),
            anchor="w",
        )
        hdr.grid(row=row_idx, column=0, sticky="ew",
                   padx=6, pady=(8 if row_idx > 0 else 2, 2))

    def _build_session_row(self, parent, idx: int, s: dict):
        """Une ligne de l'historique (date + passage + enr + état).

        Interactions :
        - clic sur la ligne → ouvre la session dans le Registre (si callback
          défini via set_on_open_in_registry)
        - bouton ⌄ → déplie/replie les conditions météo de la nuit
        """
        card = ctk.CTkFrame(parent, fg_color=("gray96", "gray17"), corner_radius=5)
        card.grid(row=idx, column=0, sticky="ew", padx=4, pady=2)
        card.grid_columnconfigure(1, weight=1)

        # Couleur de pastille selon état
        etat = (s.get("api_etat") or "").upper()
        if etat in ("TERMINE", "FINI"):
            dot_color = ("#2ea043", "#3fb950")
            dot = "●"
        elif etat in ("EN_COURS", "PLANIFIE"):
            dot_color = ("#f2a93b", "#d29922")
            dot = "●"
        elif etat in ("ERROR", "ERREUR"):
            dot_color = ("#cf222e", "#f85149")
            dot = "●"
        else:
            dot_color = ("gray60", "gray45")
            dot = "○"

        ctk.CTkLabel(
            card, text=dot, width=20,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=dot_color,
        ).grid(row=0, column=0, rowspan=2, padx=(8, 2), pady=4, sticky="nw")

        # Ligne 1 : date · Pass<N> (toujours visible si connu, sinon juste date).
        date_s = str(s.get("date_debut") or "?")[:10]
        pass_n = s.get("n_passage")
        if pass_n is not None:
            try:
                pass_txt = f"Pass{int(pass_n)}"
            except (TypeError, ValueError):
                pass_txt = f"Pass{pass_n}"
            date_line = f"{date_s}   ·   {pass_txt}"
        else:
            date_line = date_s
        title_lbl = ctk.CTkLabel(
            card, text=date_line,
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w", cursor="hand2",
        )
        title_lbl.grid(row=0, column=1, sticky="w", pady=(4, 0))

        # Bouton chevron ⌄ si météo dépliable
        meteo = s.get("_api_meteo") or {}
        has_meteo = bool(meteo and any(
            meteo.get(k) is not None
            for k in ("vent", "couverture", "temperature_debut", "temperature_fin")))
        meteo_frame_holder = {"frame": None}

        def _toggle_meteo():
            if meteo_frame_holder["frame"] is None:
                mf = ctk.CTkFrame(card, fg_color="transparent")
                mf.grid(row=2, column=1, columnspan=2, sticky="ew",
                          padx=(0, 8), pady=(0, 6))
                ctk.CTkLabel(
                    mf, text=self._format_meteo_line(meteo),
                    font=ctk.CTkFont(size=10),
                    text_color=("gray35", "gray70"),
                    anchor="w", justify="left", wraplength=280,
                ).pack(anchor="w")
                meteo_frame_holder["frame"] = mf
            else:
                try:
                    meteo_frame_holder["frame"].destroy()
                except Exception:
                    pass
                meteo_frame_holder["frame"] = None

        if has_meteo:
            chev = ctk.CTkButton(
                card, text="⌄ météo", width=70, height=18,
                font=ctk.CTkFont(size=9),
                fg_color="transparent",
                text_color=("gray40", "gray60"),
                hover_color=("gray90", "gray28"),
                command=_toggle_meteo,
            )
            chev.grid(row=0, column=2, sticky="e", padx=(4, 6), pady=(4, 0))

        # Ligne 2 : matériel
        mat_info = self._format_materiel(
            s.get("n_enregistreur"), s.get("n_serie"))
        if not mat_info:
            bits: list[str] = []
            if s.get("_api_detecteur"):
                bits.append(str(s["_api_detecteur"]))
            if s.get("_api_micro0"):
                bits.append(f"+ {s['_api_micro0']}")
            if bits:
                mat_info = " ".join(bits)
        if s.get("source") == "server":
            if mat_info:
                mat_info += "  · serveur"
            else:
                mat_info = "serveur uniquement (non synchronisé localement)"
        if mat_info or etat:
            tail = []
            if mat_info:
                tail.append(mat_info)
            if etat and etat not in ("TERMINE", "FINI"):
                tail.append(f"({etat})")
            info_lbl = ctk.CTkLabel(
                card, text="  ·  ".join(tail),
                font=ctk.CTkFont(size=10),
                text_color=("gray40", "gray65"),
                anchor="w", wraplength=280, justify="left", cursor="hand2",
            )
            info_lbl.grid(row=1, column=1, columnspan=2, sticky="w",
                          pady=(0, 4))
        else:
            info_lbl = None

        # Clic sur la ligne → ouvre la session dans le Registre (si callback)
        # La carte reçoit son clic — on bind sur les labels pour ne pas
        # interférer avec le bouton chevron.
        def _on_open(_e=None, sess=s):
            cb = getattr(self, "_on_open_in_registry_cb", None)
            if cb is None:
                return
            try:
                cb(sess)
            except Exception:
                pass

        for w in (card, title_lbl):
            try:
                w.bind("<Button-1>", _on_open)
            except Exception:
                pass
        if info_lbl is not None:
            try:
                info_lbl.bind("<Button-1>", _on_open)
            except Exception:
                pass

    def _format_meteo_line(self, meteo: dict) -> str:
        """Formate la météo d'une nuit pour affichage sous la ligne session."""
        if not meteo:
            return ""
        parts = []
        vent = meteo.get("vent")
        if vent:
            parts.append(f"💨 vent {str(vent).lower()}")
        couv = meteo.get("couverture")
        if couv:
            parts.append(f"☁ {couv}")
        t1 = meteo.get("temperature_debut")
        t2 = meteo.get("temperature_fin")
        if t1 is not None and t2 is not None:
            parts.append(f"🌡 {t1}° → {t2}°")
        elif t1 is not None:
            parts.append(f"🌡 {t1}°")
        return "  ·  ".join(parts) if parts else "(pas de météo renseignée)"

    def set_on_open_in_registry(self, callback) -> None:
        """Injecte un callback invoqué au clic sur une ligne de session.

        callback reçoit le dict session complet (avec canonical_name,
        nom_contrat, date_debut, etc.). Appelé typiquement par gui_app.py
        pour basculer sur l'onglet Registre et filtrer dessus.
        """
        self._on_open_in_registry_cb = callback

    def _format_materiel(self, n_enr, n_serie) -> str:
        """Retourne une string compacte ex: '#7 SM4BAT (S4U04784) + SMX-U1'."""
        if n_enr is None and not n_serie:
            return ""
        try:
            from materiels import find_by_id, find_by_serial, load_materiels
            mats = load_materiels()
            m = None
            if n_enr is not None:
                try:
                    m = find_by_id(mats, int(n_enr))
                except (TypeError, ValueError):
                    m = None
            if m is None and n_serie:
                m = find_by_serial(mats, str(n_serie))
        except Exception:
            m = None

        parts: list[str] = []
        if n_enr is not None:
            parts.append(f"#{n_enr}")
        if m and m.modele:
            parts.append(m.modele)
        elif n_serie:
            parts.append(str(n_serie))
        if m and m.micro_modele:
            parts.append(f"+ {m.micro_modele}")
        return " ".join(parts)

    def _on_map_click_outside_popup(self, _event):
        """Ferme le popup au clic carte — mais ignore les clics sur le popup lui-même."""
        if self._point_popup is None:
            return
        # Si le clic est dans les bounds du popup, on ne ferme pas
        try:
            x = _event.x_root
            y = _event.y_root
            px = self._point_popup.winfo_rootx()
            py = self._point_popup.winfo_rooty()
            pw = self._point_popup.winfo_width()
            ph = self._point_popup.winfo_height()
            if px <= x <= px + pw and py <= y <= py + ph:
                return
        except Exception:
            pass
        self._close_point_popup()

    def _close_point_popup(self):
        """Ferme la fiche récap (si ouverte) et retire les binds."""
        if self._point_popup is not None:
            try:
                self._point_popup.destroy()
            except Exception:
                pass
            self._point_popup = None
        # Détache le bind canvas
        if self._point_popup_bind_id:
            try:
                self.map.canvas.unbind("<Button-1>", self._point_popup_bind_id)
            except Exception:
                pass
            self._point_popup_bind_id = None
        if hasattr(self, "_point_popup_esc_id") and self._point_popup_esc_id:
            try:
                self.winfo_toplevel().unbind(
                    "<Escape>", self._point_popup_esc_id)
            except Exception:
                pass
            self._point_popup_esc_id = None

    def _on_reload_sites(self):
        self._sites_loaded = False
        self.load_sites_async()

    # -- Recherche d'adresse / commune avec autocomplétion -----------------

    def _on_search_type(self, *_):
        """Debounce puis lance l'autocomplétion."""
        if self._autocomplete_after is not None:
            try:
                self.after_cancel(self._autocomplete_after)
            except Exception:
                pass
        self._autocomplete_after = self.after(400, self._fetch_suggestions)

    def _fetch_suggestions(self):
        query = self.search_var.get().strip()
        self._autocomplete_after = None
        if len(query) < 3 or query == self._last_query:
            return
        self._last_query = query

        def _worker(q):
            try:
                data = nominatim_search(q, limit=7)
            except Exception:
                data = []
            # Retour UI sur le thread principal
            try:
                self.after(0, lambda: self._show_suggestions(q, data))
            except (RuntimeError, Exception):
                pass  # fenêtre fermée pendant la requête

        threading.Thread(target=_worker, args=(query,), daemon=True).start()

    def _show_suggestions(self, query: str, results: list[dict]):
        # Si l'utilisateur a déjà continué à taper, on ignore
        if query != self.search_var.get().strip():
            return
        self._close_suggestions()
        if not results:
            return

        # Position du dropdown juste sous la search_entry
        self.update_idletasks()
        try:
            x = self.search_entry.winfo_x()
            y = self.search_entry.winfo_y() + self.search_entry.winfo_height()
            w = self.search_entry.winfo_width()
        except Exception:
            return

        box = ctk.CTkFrame(
            self, fg_color=("white", "gray18"),
            border_width=1, border_color=("gray70", "gray35"),
            corner_radius=6,
            width=max(w, 480), height=240,
        )
        box.place(x=x, y=y + 2)
        box.pack_propagate(False)
        box.grid_propagate(False)
        box.grid_columnconfigure(0, weight=1)

        for i, res in enumerate(results[:7]):
            name = res.get("display_name", "?")
            try:
                lat = float(res.get("lat")); lon = float(res.get("lon"))
            except (TypeError, ValueError):
                continue
            # Format compact : commune en premier, puis département / pays
            parts = [p.strip() for p in name.split(",")]
            if len(parts) >= 3:
                short = f"{parts[0]}  ·  {parts[-3] if len(parts) >= 3 else ''}  ·  {parts[-1].strip()}"
            else:
                short = name
            btn = ctk.CTkButton(
                box, text=short, anchor="w", height=30,
                fg_color="transparent",
                text_color=("gray15", "gray90"),
                hover_color=("gray90", "gray28"),
                command=lambda la=lat, lo=lon, n=name: self._select_suggestion(la, lo, n),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=2, pady=1)

        self.suggestions_box = box

    def _close_suggestions(self):
        if self.suggestions_box is not None:
            try:
                self.suggestions_box.destroy()
            except Exception:
                pass
            self.suggestions_box = None

    def _select_suggestion(self, lat: float, lon: float, name: str):
        self._close_suggestions()
        # Normaliser le champ de recherche avec le 1er fragment du display_name
        short = name.split(",")[0].strip()
        self.search_var.set(short)
        # Bouger la carte avec zoom approprié
        self.map.set_position(lat, lon)
        self.map.set_zoom(13)
        self.status_lbl.configure(
            text=f"📍 {short}",
            text_color=("gray40", "gray60"),
        )

    def _on_search(self):
        """Recherche explicite (Entrée ou clic bouton). Prend le 1er résultat."""
        query = self.search_var.get().strip()
        if not query:
            return
        self._close_suggestions()
        self.status_lbl.configure(
            text=f"🔍 recherche : {query}…",
            text_color=("gray40", "gray60"),
        )

        def _worker():
            try:
                data = nominatim_search(query, limit=1)
            except Exception as e:
                self.after(0, lambda: self.status_lbl.configure(
                    text=f"✗ {e}", text_color=("#cf222e", "#f85149")))
                return
            if not data:
                self.after(0, lambda: self.status_lbl.configure(
                    text=f"✗ '{query}' introuvable",
                    text_color=("#cf222e", "#f85149")))
                return
            res = data[0]
            try:
                lat = float(res["lat"]); lon = float(res["lon"])
            except (KeyError, ValueError):
                return
            name = res.get("display_name", query)

            def _apply():
                self.map.set_position(lat, lon)
                self.map.set_zoom(13)
                short = name.split(",")[0].strip()
                self.status_lbl.configure(
                    text=f"📍 {short}",
                    text_color=("gray40", "gray60"),
                )
            try:
                self.after(0, _apply)
            except (RuntimeError, Exception):
                pass

        threading.Thread(target=_worker, daemon=True).start()

    # -- Navigation rapide --------------------------------------------------

    def _view_france(self):
        """Recentre la carte sur la France métropolitaine."""
        try:
            self.map.set_position(46.8, 2.4)
            self.map.set_zoom(6)
        except Exception:
            pass

    def _view_all_sites(self):
        """Cadre la carte pour montrer tous les sites de l'utilisateur."""
        if not self._sites_cache:
            # Pas de sites : fallback sur la France
            self._view_france()
            return
        lats: list[float] = []
        lons: list[float] = []
        for s in self._sites_cache:
            for p in s.get("points") or []:
                lat = p.get("lat")
                lon = p.get("lon")
                if lat is not None and lon is not None:
                    lats.append(float(lat))
                    lons.append(float(lon))
        if not lats:
            self._view_france()
            return
        avg_lat = sum(lats) / len(lats)
        avg_lon = sum(lons) / len(lons)
        # Calcule le zoom en fonction de la dispersion
        span = max(max(lats) - min(lats), max(lons) - min(lons))
        if len(lats) == 1 or span < 0.01:
            zoom = 14
        elif span < 0.1:
            zoom = 12
        elif span < 1:
            zoom = 9
        elif span < 5:
            zoom = 7
        else:
            zoom = 6
        try:
            self.map.set_position(avg_lat, avg_lon)
            self.map.set_zoom(zoom)
        except Exception:
            pass

    # -- Mode "ajouter un point" -------------------------------------------

    def _toggle_add_point_mode(self):
        """Active/désactive le mode clic = nouveau point."""
        if self._add_point_mode:
            self._exit_add_point_mode()
            return
        # Activer
        token = load_token()
        if not token:
            from tkinter import messagebox
            if messagebox.askyesno(
                "Token API requis",
                "L'ajout de point nécessite un token Vigie-Chiro.\n"
                "Ouvrir les préférences pour en ajouter un ?"):
                self.winfo_toplevel().event_generate("<<OpenPreferences>>")
            return
        # NB : on n'exige plus d'avoir déjà des sites à soi — le clic résout le
        # carré via l'API (qu'il existe chez un autre observateur ou pas encore).

        self._add_point_mode = True
        self.add_point_btn.configure(
            text="✖ Annuler ajout",
            fg_color=("#cf222e", "#b42318"),
            hover_color=("#b42318", "#961f17"),
        )
        self.status_lbl.configure(
            text="→ Clique sur la carte à l'emplacement du point  (Échap pour annuler)",
            text_color=("#cf222e", "#f85149"),
        )
        # Curseur crosshair sur le canvas : feedback visuel immédiat qu'on est
        # en mode capture.
        try:
            self.map.canvas.configure(cursor="crosshair")
        except Exception:
            pass
        # Bind ESC pour sortir rapidement du mode
        self._add_esc_bind = self.winfo_toplevel().bind(
            "<Escape>", lambda _e: self._exit_add_point_mode(), add="+")
        # Installer le handler de clic
        self.map.add_left_click_map_command(self._on_map_click_add_point)

    def _exit_add_point_mode(self):
        if not self._add_point_mode:
            return  # déjà sorti (évite re-entrance via ESC)
        self._add_point_mode = False
        self.add_point_btn.configure(
            text="➕ Ajouter un point",
            fg_color=("#3b8ed0", "#1f6aa5"),
            hover_color=("#36719f", "#144870"),
        )
        self.status_lbl.configure(
            text=f"{len(self._sites_cache)} site(s) chargé(s)",
            text_color=("gray40", "gray60"),
        )
        # Retirer le curseur crosshair
        try:
            self.map.canvas.configure(cursor="")
        except Exception:
            pass
        # Retirer le bind ESC
        try:
            if hasattr(self, "_add_esc_bind") and self._add_esc_bind:
                self.winfo_toplevel().unbind("<Escape>", self._add_esc_bind)
                self._add_esc_bind = None
        except Exception:
            pass
        # Retirer le marker temporaire éventuel
        if self._add_point_marker:
            try:
                self._add_point_marker.delete()
            except Exception:
                pass
            self._add_point_marker = None
        # Retirer l'aperçu des points du carré
        self._clear_carre_points()
        # Retire le handler en forçant un set (tkintermapview n'expose pas de
        # remove, mais un nouveau add écrase les précédents)
        try:
            self.map.add_left_click_map_command(lambda _c: None)
        except Exception:
            pass

    def _on_map_click_add_point(self, coords):
        """Callback de clic en mode ajout. ``coords`` = (lat, lon)."""
        try:
            lat, lon = float(coords[0]), float(coords[1])
        except Exception:
            return
        # Nouveau clic : on retire l'aperçu de points du carré précédent
        self._clear_carre_points()
        # Marker temporaire (point rouge pour distinguer)
        if self._add_point_marker:
            try:
                self._add_point_marker.delete()
            except Exception:
                pass
        self._add_point_marker = self.map.set_marker(
            lat, lon,
            text="Nouveau point",
            marker_color_circle="#cf222e",
            marker_color_outside="#961f17",
            text_color="#961f17",
        )
        # Résolution asynchrone du carré (cellule grille STOC) AVANT d'ouvrir le
        # wizard : trouve le carré quel qu'en soit le propriétaire, ou détecte
        # qu'il faut le créer.
        if getattr(self, "_carre_resolving", False):
            return          # une résolution est déjà en cours (anti double-clic)
        self._carre_resolving = True
        self.status_lbl.configure(
            text="⏳ Résolution du carré (grille STOC)…",
            text_color=("gray40", "gray70"),
        )

        def _worker():
            res, err = None, None
            try:
                from vigiechiro_api import VigieChiroClient
                client = VigieChiroClient(load_token())
                res = client.resolve_carre(lat, lon)
            except Exception as e:
                err = str(e)
            finally:
                self._carre_resolving = False
            self.after(0, lambda: self._on_carre_resolved(lat, lon, res, err))

        threading.Thread(target=_worker, daemon=True).start()

    # -- Résolution / création de carré (nouveau flux v0.2) -----------------

    def _build_target_site(self, raw_site: dict, points: list, numero) -> dict:
        """Construit le dict 'site' attendu par AddPointWizard."""
        return {
            "id": raw_site.get("_id") or "",
            "numero": str(numero).zfill(6) if numero else None,
            "titre": raw_site.get("titre", ""),
            "points": [
                {"nom": p["nom"], "lat": p["lat"], "lon": p["lon"]}
                for p in (points or []) if p.get("lat") is not None
            ],
        }

    def _draw_carre_points(self, points: list, is_mine):
        """Dessine sur la carte les points existants du carré résolu (aperçu).

        Permet de VOIR un éventuel point proche à réutiliser, y compris ceux des
        autres observateurs (non chargés par défaut car la carte n'affiche que
        tes propres sites). Couleur verte si à toi, orange sinon.
        """
        self._clear_carre_points()
        if is_mine:
            circle, outside, txt = "#2ea043", "#1b6828", "#1b6828"
        else:
            circle, outside, txt = "#e8a23a", "#7a5a24", "#7a5a24"
        for p in points or []:
            if p.get("lat") is None or p.get("lon") is None:
                continue
            try:
                m = self.map.set_marker(
                    float(p["lat"]), float(p["lon"]),
                    text=p.get("nom") or "?",
                    marker_color_circle=circle,
                    marker_color_outside=outside,
                    text_color=txt,
                )
                self._carre_preview_markers.append(m)
            except Exception:
                pass

    def _clear_carre_points(self):
        for m in self._carre_preview_markers:
            try:
                m.delete()
            except Exception:
                pass
        self._carre_preview_markers = []

    def _open_add_wizard(self, lat: float, lon: float, target: dict):
        from gui_site_wizard import AddPointWizard
        wiz = AddPointWizard(
            self.winfo_toplevel(),
            lat=lat, lon=lon,
            sites=self._sites_cache,
            on_confirm=self._on_add_point_confirmed,
            target_site=target,
        )
        self.wait_window(wiz)
        self._exit_add_point_mode()

    def _on_carre_resolved(self, lat, lon, res, err):
        from tkinter import messagebox
        if err or res is None:
            messagebox.showerror(
                "Résolution impossible",
                f"Impossible de déterminer le carré à cet endroit :\n{err}")
            self._exit_add_point_mode()
            return
        grille = res.get("grille")
        if not grille:
            messagebox.showwarning(
                "Hors grille STOC",
                "Aucune cellule de la grille nationale STOC (2×2 km) à cet "
                "endroit. Le protocole Point Fixe ne s'applique qu'au "
                "territoire couvert par cette grille.")
            self._exit_add_point_mode()
            return
        numero = grille.get("numero")

        if res.get("exists"):
            target = self._build_target_site(res["site"], res["points"], numero)
            # Aperçu visuel : dessine les points du carré (dont ceux des autres)
            self._draw_carre_points(res["points"], res.get("is_mine"))
            if not res.get("is_mine"):
                owner = res.get("owner") or "un autre observateur"
                messagebox.showinfo(
                    "Carré déjà existant",
                    f"Le carré n°{numero} existe déjà "
                    f"(propriétaire : {owner}).\n\n"
                    "Tu peux y ajouter ton propre point d'écoute, ou réutiliser "
                    "un point existant s'il est au même endroit.\n\n"
                    "→ Tu restes propriétaire de ta nuit d'enregistrement ; "
                    "la paternité du carré n'est pas modifiée.")
            self._open_add_wizard(lat, lon, target)
            return

        # Carré inexistant → proposer la création
        if not messagebox.askyesno(
                "Créer le carré ?",
                f"Le carré n°{numero} n'existe pas encore sur Vigie-Chiro.\n\n"
                "Le créer maintenant ? (tu en deviendras le propriétaire, et "
                "tu pourras y placer tes points)\n\n"
                "⚠️ Action définitive : un carré ne peut pas être supprimé par "
                "un observateur (seul un administrateur le peut)."):
            self._exit_add_point_mode()
            return
        self._create_carre_then_wizard(lat, lon, grille.get("_id"), numero)

    def _create_carre_then_wizard(self, lat, lon, grille_id, numero):
        self.status_lbl.configure(
            text=f"⏳ Création du carré n°{numero}…",
            text_color=("gray40", "gray70"))

        def _worker():
            new_site, err = None, None
            try:
                from vigiechiro_api import VigieChiroClient
                new_site = VigieChiroClient(load_token()).create_pointfixe_site(grille_id)
            except Exception as e:
                err = str(e)
            self.after(0, lambda: self._on_carre_created(lat, lon, new_site, numero, err))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_carre_created(self, lat, lon, new_site, numero, err):
        from tkinter import messagebox
        if err or not new_site:
            messagebox.showerror(
                "Échec création du carré",
                f"Le carré n°{numero} n'a pas pu être créé :\n{err}")
            self._exit_add_point_mode()
            return
        self.status_lbl.configure(
            text=f"✓ Carré n°{numero} créé",
            text_color=("#2ea043", "#3fb950"))
        target = self._build_target_site(new_site, [], numero)
        self._open_add_wizard(lat, lon, target)

    def _on_add_point_confirmed(self, *, site_id: str, point_name: str,
                                  lat: float, lon: float,
                                  reused: bool = False):
        """Callback quand le wizard a validé et l'API a répondu OK.

        - Cas création : on recharge les sites (le nouveau point apparaît).
        - Cas réutilisation : pas besoin de rechargement (point déjà présent),
          mais on ouvre la fiche récap du point pour que l'utilisateur voie
          immédiatement l'historique et puisse continuer (créer une nuit
          dessus, etc.). Avant ce fix, la confirmation se faisait sans
          retour visuel autre qu'un message en bas de la carte → testeur
          frustré qui pensait que rien ne s'était passé.
        """
        if not reused:
            # Si le carré n'est pas l'un des miens (ajout d'un point sur le carré
            # d'un autre observateur), on le mémorise pour qu'il soit re-fetché et
            # reste visible sur la carte (sinon /moi/sites ne le renverrait pas).
            own_ids = {s.get("id") for s in self._sites_cache}
            if site_id and site_id not in own_ids:
                _remember_external_site_id(site_id)
            self._sites_loaded = False
            self.load_sites_async()
            self.status_lbl.configure(
                text=f"✓ Point '{point_name}' ajouté au site (rechargement…)",
                text_color=("#2ea043", "#3fb950"),
            )
            return

        # Réutilisation : on cherche le site/point dans le cache et on ouvre
        # la fiche récap, comme si l'utilisateur avait cliqué le marker.
        target_site = None
        target_pt = None
        for site in self._sites_cache:
            if site.get("id") == site_id:
                for p in site.get("points") or []:
                    if (p.get("nom") or "").upper() == (point_name or "").upper():
                        target_site = site
                        target_pt = p
                        break
                if target_site:
                    break
        if target_site and target_pt:
            # Centre la carte sur le point puis ouvre la fiche
            try:
                self.map.set_position(float(target_pt["lat"]),
                                       float(target_pt["lon"]))
                self.map.set_zoom(15)
            except Exception:
                pass
            # Léger délai pour laisser le mode add-point se cleanup avant
            # d'ouvrir le popup (sinon le binding canvas le ferait fermer).
            self.after(150, lambda: self._show_point_popup(target_site, target_pt))
            self.status_lbl.configure(
                text=f"✓ Point '{point_name}' réutilisé — fiche affichée",
                text_color=("#2ea043", "#3fb950"),
            )
        else:
            self.status_lbl.configure(
                text=f"✓ Point '{point_name}' réutilisé",
                text_color=("#2ea043", "#3fb950"),
            )

    # -- Focus programmable (appelé depuis la sidebar) ---------------------

    def focus_on_session(self, session, *, force: bool = True):
        """Centre la carte sur une session (via son manifest ou le site_id API).

        Si ``force=False``, on ne bouge pas la carte si elle pointe déjà sur
        le même point (évite des reset intempestifs quand l'utilisateur
        a déjà zoomé ailleurs).
        """
        from manifest import Manifest
        m = Manifest.load(session.path)

        target_point = None
        if m and m.meta:
            sid = m.meta.get("vigiechiro_site_id")
            nom = m.meta.get("n_point_fixe")
            numero = m.meta.get("n_site_tadarida")
            for s in self._sites_cache:
                if (sid and s["id"] == sid) or (not sid and s.get("numero") == numero):
                    for pt in s["points"]:
                        if pt["nom"] == nom:
                            target_point = pt
                            break
                    break

        if not target_point:
            self.status_lbl.configure(
                text="point non géolocalisé (charge les sites d'abord)",
                text_color=("gray40", "gray60"),
            )
            return

        # Ne pas repositionner si on pointe déjà dessus (à 1 m près)
        if not force and self._current_focus == (target_point["lat"], target_point["lon"]):
            return

        self._current_focus = (target_point["lat"], target_point["lon"])
        self.map.set_position(target_point["lat"], target_point["lon"])
        self.map.set_zoom(15)
        self.status_lbl.configure(
            text=f"📍 {target_point['nom']} "
                 f"({target_point['lat']:.4f}, {target_point['lon']:.4f})",
            text_color=("gray40", "gray60"),
        )
