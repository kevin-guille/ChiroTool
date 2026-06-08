"""
gui_site_wizard.py — wizard de création d'un nouveau point dans un site existant.

Ouvert après clic sur la carte en mode "Ajouter un point". Demande :
  - site cible (menu déroulant des sites de l'utilisateur)
  - nom du point (A1, Z3, etc.)
  - coordonnées (affichées, pré-remplies, éditables)
  - option "site représentatif" (pour les passages aléatoires Vigie-Chiro)

À validation :
  - vérifie que le nom respecte le format protocolaire (lettre+chiffre)
  - appelle l'API pour ajouter la localité au site
  - callback on_confirm côté carte
"""

from __future__ import annotations

import math
import re
import threading
from tkinter import messagebox

import customtkinter as ctk

from credentials import load_token


POINT_NAME_RE = re.compile(r"^[A-Za-z]\d+$")

# Seuil sous lequel on propose de réutiliser un point existant plutôt que d'en
# créer un nouveau. Standard terrain : ~10-30 m pour considérer "même point".
NEARBY_THRESHOLD_M = 50

# Seuil pour considérer qu'un site "pourrait couvrir" le clic (carré STOC
# 2×2 km → on prend 2.5 km pour tenir compte du demi-diagonal).
SITE_COVERAGE_THRESHOLD_M = 2500


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance en mètres entre deux coordonnées GPS (formule de Haversine)."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class AddPointWizard(ctk.CTkToplevel):
    """Wizard modal pour l'ajout d'un point."""

    def __init__(self, master, *, lat: float, lon: float,
                 sites: list[dict], on_confirm,
                 target_site: dict | None = None):
        super().__init__(master)
        self.title("Ajouter un point")
        self.geometry("560x480")
        self.minsize(500, 420)

        self.lat = lat
        self.lon = lon
        self.all_sites = sites
        self.on_confirm = on_confirm
        self.target_site = target_site

        self._show_all_carre_points = target_site is not None
        if target_site is not None:
            # Mode "carré résolu par localisation" : on cible UN site précis
            # (le carré de la cellule cliquée, même appartenant à un autre
            # observateur, éventuellement vide). On bypass le filtrage.
            self.sites = [target_site]
            self._min_distances = {target_site["id"]: 0.0}
            # On liste TOUS les points du carré (triés par distance), pas
            # seulement ceux < 50 m : l'utilisateur doit voir l'existant pour
            # décider de réutiliser ou créer.
            self.nearby_points = []
            for pt in target_site.get("points", []) or []:
                try:
                    d = haversine_m(lat, lon, pt["lat"], pt["lon"])
                except Exception:
                    continue
                self.nearby_points.append((d, target_site, pt))
            self.nearby_points.sort(key=lambda x: x[0])
            self._nearest_site_idx = 0
        else:
            # Filtrage : on ne garde que les sites dont au moins un point est
            # à distance raisonnable du clic (= sites potentiellement sur le
            # même carré STOC 2×2 km).
            relevant: list[tuple[float, dict]] = []
            for site in sites:
                if not site.get("points"):
                    continue
                min_d = min(
                    (haversine_m(lat, lon, pt["lat"], pt["lon"])
                     for pt in site.get("points", [])),
                    default=float("inf"),
                )
                if min_d <= SITE_COVERAGE_THRESHOLD_M:
                    relevant.append((min_d, site))
            relevant.sort(key=lambda x: x[0])
            self.sites = [s for _d, s in relevant]
            self._min_distances = {s["id"]: d for d, s in relevant}

            self.nearby_points = []
            for site in self.sites:
                for pt in site.get("points", []):
                    try:
                        d = haversine_m(lat, lon, pt["lat"], pt["lon"])
                    except Exception:
                        continue
                    if d <= NEARBY_THRESHOLD_M:
                        self.nearby_points.append((d, site, pt))
            self.nearby_points.sort(key=lambda x: x[0])
            self._nearest_site_idx = 0 if self.sites else None

        self.transient(master)
        self.after(50, self.grab_set)
        self.focus()

        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _on_site_change(self):
        """Mis à jour quand l'utilisateur change de site cible."""
        if not hasattr(self, "existing_pts_lbl") or not self.sites:
            return
        # Retrouver le site sélectionné
        try:
            idx = self._site_menu_index()
        except Exception:
            return
        if idx is None:
            return
        site = self.sites[idx]
        names = [pt.get("nom", "?") for pt in site.get("points", []) or []]
        if names:
            self.existing_pts_lbl.configure(
                text=f"Déjà dans ce site : {', '.join(sorted(names))}")
        else:
            self.existing_pts_lbl.configure(
                text="(aucun point n'existe encore dans ce site)")

        # Auto-suggestion du nom SI le champ est vide
        if hasattr(self, "name_var") and not self.name_var.get().strip():
            self.name_var.set(self._suggest_next_point_name(site))

    def _site_menu_index(self) -> int | None:
        """Retrouve l'index dans self.sites du site sélectionné dans le menu."""
        if not self.sites:
            return None
        choice = self.site_var.get()
        for i, s in enumerate(self.sites):
            d = self._min_distances.get(s["id"], 0)
            label = (f"#{s['numero'] or '?'}  ({len(s.get('points', []))} pts)  "
                     f"{s.get('titre','')}  · {d:.0f} m")
            if label == choice:
                return i
        return None

    def _suggest_next_point_name(self, site: dict) -> str:
        """Propose un nom de point disponible basé sur les codes existants.

        Exemple : si le site contient ['Z1', 'Z2'] → suggère 'Z3'.
        Par défaut (site vide) → 'Z1'.
        """
        existing = set()
        prefix_to_nums: dict[str, list[int]] = {}
        for pt in site.get("points", []) or []:
            name = (pt.get("nom") or "").strip().upper()
            if not name:
                continue
            existing.add(name)
            m = re.match(r"^([A-Z])(\d+)$", name)
            if m:
                prefix_to_nums.setdefault(m.group(1), []).append(int(m.group(2)))

        if prefix_to_nums:
            # Préfixe majoritaire
            prefix = max(prefix_to_nums, key=lambda k: len(prefix_to_nums[k]))
            used = set(prefix_to_nums[prefix])
            for n in range(1, 100):
                if n not in used:
                    return f"{prefix}{n}"
        return "Z1"

    # -- UI -----------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        ctk.CTkLabel(
            self, text="Ajouter un point d'écoute",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))

        ctk.CTkLabel(
            self,
            text=f"Coordonnées cliquées : {self.lat:.5f}, {self.lon:.5f}",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))

        # Conteneur scrollable (bannière "points proches" peut prendre de la place)
        main = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main.grid(row=2, column=0, sticky="nsew", padx=12, pady=(4, 0))
        main.grid_columnconfigure(0, weight=1)

        # --- Bannière "Points existants à proximité" (si pertinent) ---
        if self.nearby_points:
            self._build_nearby_banner(main).grid(
                row=0, column=0, sticky="ew", padx=4, pady=(4, 8))

        # Cas : aucun site ne couvre la zone cliquée
        if not self.sites:
            no_site_banner = ctk.CTkFrame(
                main, fg_color=("#fdeaea", "#4a2020"),
                corner_radius=8, border_width=1,
                border_color=("#f5a0a0", "#8a4040"),
            )
            no_site_banner.grid(row=1, column=0, sticky="ew", padx=4, pady=(4, 8))
            no_site_banner.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                no_site_banner,
                text="⚠  Aucun site Vigie-Chiro ne couvre cette zone",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=("#7a1a1a", "#f08080"),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))

            ctk.CTkLabel(
                no_site_banner,
                text=(
                    f"Tes sites existants sont tous à plus de "
                    f"{SITE_COVERAGE_THRESHOLD_M/1000:.1f} km du point cliqué. "
                    f"Pour ajouter un point ici, il faut d'abord créer un "
                    f"nouveau site associé au carré STOC correspondant "
                    f"(opération non encore prise en charge dans l'outil, "
                    f"à faire sur le portail web Vigie-Chiro)."),
                font=ctk.CTkFont(size=11),
                text_color=("gray20", "gray75"),
                justify="left", anchor="w", wraplength=640,
            ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
            return   # on ne crée pas de formulaire

        # --- Formulaire de création ---
        form = ctk.CTkFrame(
            main, fg_color=("gray92", "gray20"),
            corner_radius=8, border_width=1,
            border_color=("gray80", "gray25"),
        )
        form.grid(row=1, column=0, sticky="ew", padx=4, pady=0)
        form.grid_columnconfigure(1, weight=1)

        # Titre du bloc
        create_title = "Créer un nouveau point"
        if self.nearby_points:
            create_title += "  (ou réutilise un point ci-dessus)"
        ctk.CTkLabel(
            form, text=create_title,
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew",
               padx=16, pady=(12, 8))

        row = 1

        # -- Site --
        self._field_label(form, row, "Site cible *",
                           help="Sites qui couvrent cette zone (≤ 2,5 km)")
        self.site_var = ctk.StringVar()
        site_options = []
        for s in self.sites:
            d = self._min_distances.get(s["id"], 0)
            label = (f"#{s['numero'] or '?'}  ({len(s.get('points', []))} pts)  "
                     f"{s.get('titre','')}  · {d:.0f} m")
            site_options.append(label)
        self.site_menu = ctk.CTkOptionMenu(
            form, variable=self.site_var, width=420,
            values=site_options,
            command=lambda _v: self._on_site_change(),
        )
        # Pré-sélection : site le plus proche
        self.site_var.set(site_options[self._nearest_site_idx or 0])
        self.site_menu.grid(row=row, column=1, sticky="ew", padx=(4, 16), pady=4)
        row += 1

        # -- Rappel points existants dans le site choisi --
        self.existing_pts_lbl = ctk.CTkLabel(
            form, text="", anchor="w",
            font=ctk.CTkFont(size=10),
            text_color=("gray45", "gray65"),
            justify="left", wraplength=440,
        )
        self.existing_pts_lbl.grid(row=row, column=1, sticky="w",
                                     padx=(4, 16), pady=(0, 4))
        row += 1

        # -- Nom du point --
        self._field_label(form, row, "Nom du point *",
                           help="Lettre + chiffre (A1, C2, Z4…)")
        self.name_var = ctk.StringVar()
        self.name_entry = ctk.CTkEntry(
            form, textvariable=self.name_var, width=140,
            placeholder_text="ex: Z5",
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.name_entry.grid(row=row, column=1, sticky="w", padx=(4, 16), pady=4)
        self.name_entry.focus()
        row += 1

        # Initialise l'affichage du site sélectionné
        self._on_site_change()

        # -- Latitude --
        self._field_label(form, row, "Latitude")
        self.lat_var = ctk.StringVar(value=f"{self.lat:.6f}")
        ctk.CTkEntry(form, textvariable=self.lat_var, width=160,
                       font=ctk.CTkFont(family="Consolas", size=12)
                       ).grid(row=row, column=1, sticky="w", padx=(4, 16), pady=4)
        row += 1

        # -- Longitude --
        self._field_label(form, row, "Longitude")
        self.lon_var = ctk.StringVar(value=f"{self.lon:.6f}")
        ctk.CTkEntry(form, textvariable=self.lon_var, width=160,
                       font=ctk.CTkFont(family="Consolas", size=12)
                       ).grid(row=row, column=1, sticky="w", padx=(4, 16), pady=4)
        row += 1

        # -- Représentatif --
        self.repr_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            form, text="Point représentatif (tirage aléatoire Vigie-Chiro)",
            variable=self.repr_var,
        ).grid(row=row, column=1, sticky="w", padx=(4, 16), pady=(12, 4))
        row += 1

        ctk.CTkLabel(
            form,
            text=("Un point \"représentatif\" entre dans l'échantillonnage "
                   "aléatoire strict du protocole.\n"
                   "Un point \"choisi\" (par défaut) est opportuniste."),
            font=ctk.CTkFont(size=10),
            text_color=("gray45", "gray65"),
            justify="left", anchor="w", wraplength=440,
        ).grid(row=row, column=1, sticky="w", padx=(4, 16), pady=(0, 12))
        row += 1

        # Erreurs
        self.err_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=11),
            text_color=("#cf222e", "#f85149"),
            anchor="w", justify="left", wraplength=640,
        )
        self.err_lbl.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 0))

        # Footer
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 14))
        footer.grid_columnconfigure(0, weight=1)

        self.status_lbl = ctk.CTkLabel(
            footer, text="", anchor="w",
            font=ctk.CTkFont(size=11),
        )
        self.status_lbl.grid(row=0, column=0, sticky="w")

        self.cancel_btn = ctk.CTkButton(
            footer, text="Annuler", width=100, height=32,
            fg_color=("gray85", "gray25"),
            text_color=("gray15", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self.destroy,
        )
        self.cancel_btn.grid(row=0, column=1, padx=(6, 6))

        self.validate_btn = ctk.CTkButton(
            footer, text="Créer le point", width=140, height=32,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_validate,
        )
        self.validate_btn.grid(row=0, column=2)

    def _field_label(self, form, row, text, *, help=""):
        """Crée un label de champ avec aide optionnelle, proprement empilés
        dans un frame interne pour éviter les overlaps."""
        container = ctk.CTkFrame(form, fg_color="transparent", width=180)
        container.grid(row=row, column=0, sticky="nw", padx=(16, 4), pady=4)
        container.grid_propagate(False)  # garde la largeur fixée
        ctk.CTkLabel(
            container, text=text, anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", fill="x")
        if help:
            ctk.CTkLabel(
                container, text=help, anchor="w",
                font=ctk.CTkFont(size=10),
                text_color=("gray50", "gray60"),
                justify="left",
            ).pack(anchor="w", fill="x")
        # Ajuste la hauteur du conteneur selon qu'il y a ou non du help
        container.configure(height=44 if help else 26)

    def _build_nearby_banner(self, parent) -> ctk.CTkFrame:
        """Bannière 'Points existants à proximité' avec boutons 'Utiliser'."""
        banner = ctk.CTkFrame(
            parent, fg_color=("#fff4e6", "#3d2d1a"),
            corner_radius=8, border_width=1,
            border_color=("#e8a23a", "#7a5a24"),
        )
        banner.grid_columnconfigure(0, weight=1)

        if getattr(self, "_show_all_carre_points", False):
            title_txt = "📍  Points déjà présents sur ce carré"
            intro_txt = ("Ce carré contient déjà les points ci-dessous (triés du "
                         "plus proche au plus loin du clic). Si l'un d'eux est au "
                         "même endroit que ton point, réutilise-le (recommandé "
                         "pour un suivi long-terme) ; sinon, crée un nouveau "
                         "point dans le formulaire.")
        else:
            title_txt = "📍  Points existants à proximité"
            intro_txt = (f"Un ou plusieurs points existent à moins de "
                         f"{NEARBY_THRESHOLD_M} m de l'endroit cliqué. Pour un "
                         f"suivi long-terme, il est recommandé de réutiliser un "
                         f"point existant plutôt que d'en créer un nouveau.")

        ctk.CTkLabel(
            banner, text=title_txt,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("#7a4a00", "#e8a23a"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))

        ctk.CTkLabel(
            banner, text=intro_txt,
            font=ctk.CTkFont(size=11),
            text_color=("gray25", "gray75"),
            justify="left", anchor="w", wraplength=640,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

        for i, (d, site, pt) in enumerate(self.nearby_points[:5]):
            row = ctk.CTkFrame(banner, fg_color="transparent")
            row.grid(row=2 + i, column=0, sticky="ew", padx=12, pady=2)
            row.grid_columnconfigure(1, weight=1)

            info = (f"{pt['nom']}  ·  site #{site.get('numero', '?')}  ·  "
                    f"à {d:.0f} m")
            ctk.CTkLabel(
                row, text=info, anchor="w",
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=0, sticky="w", padx=(0, 12))

            ctk.CTkButton(
                row, text=f"✓ Utiliser {pt['nom']}", height=28, width=140,
                fg_color=("#2ea043", "#238636"),
                hover_color=("#258038", "#1b6828"),
                command=lambda s=site, p=pt, dist=d: self._reuse_existing_point(s, p, dist),
            ).grid(row=0, column=1, sticky="e")

        # Espace bas
        ctk.CTkLabel(banner, text="").grid(row=10, column=0, pady=2)
        return banner

    def _reuse_existing_point(self, site: dict, pt: dict, distance_m: float):
        """L'utilisateur choisit de réutiliser un point existant au lieu
        d'en créer un nouveau."""
        msg = (
            f"Tu vas réutiliser le point '{pt['nom']}' du site "
            f"#{site.get('numero', '?')} (à {distance_m:.0f} m du clic).\n\n"
            f"Aucune création de point ne sera faite côté Vigie-Chiro — "
            f"sa fiche récapitulative s'affichera immédiatement après.\n\n"
            f"Pour créer une nouvelle nuit (participation) sur ce point :\n"
            f"  1. Dépose tes WAV dans <campagne>/<dossier_session>/\n"
            f"  2. Clique « 🔄 Scanner » pour détecter la session\n"
            f"  3. Sélectionne-la dans la sidebar puis clique\n"
            f"     « ▶ Upload + Tadarida » — le point sera utilisé.\n\n"
            f"Confirmer ?"
        )
        if not messagebox.askyesno("Réutiliser un point existant", msg):
            return
        # Signaler à l'appelant via on_confirm. reused=True pour que la carte
        # ouvre la fiche récap du point au lieu de juste un message statut.
        try:
            if self.on_confirm:
                self.on_confirm(
                    site_id=site["id"],
                    point_name=pt["nom"],
                    lat=pt["lat"], lon=pt["lon"],
                    reused=True,
                )
        except TypeError:
            # Compatibilité : si on_confirm n'accepte pas reused= (caller
            # ancien), on retombe sur la signature historique.
            try:
                self.on_confirm(
                    site_id=site["id"], point_name=pt["nom"],
                    lat=pt["lat"], lon=pt["lon"],
                )
            except Exception:
                pass
        except Exception:
            pass
        self.destroy()

    # -- Validation ---------------------------------------------------------

    def _on_validate(self):
        self.err_lbl.configure(text="")
        if not self.sites:
            self.err_lbl.configure(text="aucun site disponible")
            return

        idx = self._site_menu_index()
        if idx is None:
            self.err_lbl.configure(text="site non reconnu")
            return
        site = self.sites[idx]

        name = self.name_var.get().strip().upper()
        if not name or not POINT_NAME_RE.match(name):
            self.err_lbl.configure(
                text="Nom de point invalide : attendu une lettre + un chiffre "
                     "(ex A1, Z3, C2)")
            return

        # Vérifier unicité locale
        for pt in site.get("points", []):
            if pt["nom"].upper() == name:
                self.err_lbl.configure(
                    text=f"Le point '{name}' existe déjà dans ce site.")
                return

        try:
            lat = float(self.lat_var.get().replace(",", "."))
            lon = float(self.lon_var.get().replace(",", "."))
        except ValueError:
            self.err_lbl.configure(text="coordonnées invalides")
            return

        # Appel API en arrière-plan
        self.validate_btn.configure(state="disabled", text="Création…")
        self.cancel_btn.configure(state="disabled")
        self.status_lbl.configure(
            text="⏳ Appel API Vigie-Chiro…",
            text_color=("gray40", "gray70"),
        )

        def _worker():
            try:
                from vigiechiro_api import VigieChiroClient
                token = load_token()
                if not token:
                    raise RuntimeError("token API manquant")
                client = VigieChiroClient(token)
                client.add_localite(
                    site["id"], name, lat, lon,
                    representatif=self.repr_var.get(),
                )
            except Exception as e:
                self.after(0, lambda: self._on_error(str(e)))
                return
            self.after(0, lambda: self._on_success(site["id"], name, lat, lon))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_error(self, msg: str):
        self.validate_btn.configure(state="normal", text="Créer le point")
        self.cancel_btn.configure(state="normal")
        self.err_lbl.configure(text=f"✗  {msg}")
        self.status_lbl.configure(text="")

    def _on_success(self, site_id: str, name: str, lat: float, lon: float):
        self.status_lbl.configure(
            text=f"✓ Point '{name}' créé avec succès",
            text_color=("#2ea043", "#3fb950"),
        )
        try:
            if self.on_confirm:
                self.on_confirm(
                    site_id=site_id, point_name=name, lat=lat, lon=lon)
        except Exception:
            pass
        # Fermeture après court délai pour que l'utilisateur voie le succès
        self.after(800, self.destroy)
