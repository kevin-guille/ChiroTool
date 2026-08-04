"""
point_selection.py — contrat unique « où travaille-t-on ? » (SPEC v0.6).

PointSelection relie carte (pick / create / reuse), wizard meta et manifest.
Logique pure (sauf I/O optionnelle via callers) → testable.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


PICK_RADIUS_KM = 5.0


@dataclass
class PointSelection:
    """Point d'écoute retenu pour une préparation / session."""
    site_numero: str = ""
    point_code: str = ""
    lat: float | None = None
    lon: float | None = None
    site_id: str = ""
    provenance: str = "mine"  # mine | other | created
    commune: str | None = None
    label_humain: str = ""

    def __post_init__(self) -> None:
        self.site_numero = _norm_site(self.site_numero)
        self.point_code = (self.point_code or "").strip().upper()
        self.site_id = (self.site_id or "").strip()
        self.provenance = self.provenance if self.provenance in (
            "mine", "other", "created") else "mine"
        if not self.label_humain:
            self.label_humain = format_point_label(
                self.site_numero, self.point_code,
                commune=self.commune, provenance=self.provenance,
            )

    def has_coords(self) -> bool:
        return self.lat is not None and self.lon is not None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> PointSelection | None:
        if not d or not isinstance(d, dict):
            return None
        try:
            lat = d.get("lat")
            lon = d.get("lon")
            return cls(
                site_numero=str(d.get("site_numero") or d.get("numero") or ""),
                point_code=str(d.get("point_code") or d.get("point") or ""),
                lat=float(lat) if lat is not None else None,
                lon=float(lon) if lon is not None else None,
                site_id=str(d.get("site_id") or ""),
                provenance=str(d.get("provenance") or (
                    "other" if d.get("is_mine") is False else "mine")),
                commune=d.get("commune"),
                label_humain=str(d.get("label_humain") or ""),
            )
        except (TypeError, ValueError):
            return None

    def to_manifest_meta(self) -> dict[str, Any]:
        """Champs à fusionner dans ``manifest.meta`` (D8)."""
        out: dict[str, Any] = {}
        if self.site_numero:
            out["n_site_tadarida"] = self.site_numero
        if self.point_code:
            out["n_point_fixe"] = self.point_code
        if self.site_id:
            out["vigiechiro_site_id"] = self.site_id
        if self.has_coords():
            out["point_lat"] = float(self.lat)  # type: ignore[arg-type]
            out["point_lon"] = float(self.lon)  # type: ignore[arg-type]
        if self.commune:
            out["point_commune"] = self.commune
        if self.provenance:
            out["point_provenance"] = self.provenance
        return out


def _norm_site(numero) -> str:
    if numero is None:
        return ""
    s = str(numero).strip()
    digits = "".join(c for c in s if c.isdigit())
    if digits:
        return digits.zfill(6) if len(digits) <= 6 else digits[:6]
    return s


def format_point_label(
    site_numero: str,
    point_code: str,
    *,
    commune: str | None = None,
    provenance: str = "mine",
) -> str:
    """Libellé humain d’abord (D6)."""
    parts: list[str] = []
    if commune:
        parts.append(str(commune).strip())
    pc = (point_code or "").strip().upper()
    if pc:
        parts.append(pc)
    num = _norm_site(site_numero)
    if num:
        parts.append(f"carré {num}")
    if provenance == "other":
        parts.append("autre obs.")
    elif provenance == "created":
        parts.append("nouveau")
    return " · ".join(parts) if parts else (pc or num or "point")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance grand cercle en km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def filter_points_within_radius(
    points: Iterable[dict],
    *,
    center_lat: float,
    center_lon: float,
    radius_km: float = PICK_RADIUS_KM,
    lat_key: str = "lat",
    lon_key: str = "lon",
) -> list[dict]:
    """Sous-ensemble des points à moins de ``radius_km`` du centre.

    Ajoute la clé ``_distance_km`` sur chaque dict retourné (copie shallow).
    """
    out: list[dict] = []
    for p in points:
        try:
            la = p.get(lat_key)
            lo = p.get(lon_key)
            if la is None or lo is None:
                continue
            d = haversine_km(center_lat, center_lon, float(la), float(lo))
        except (TypeError, ValueError):
            continue
        if d <= radius_km:
            cp = dict(p)
            cp["_distance_km"] = round(d, 3)
            out.append(cp)
    out.sort(key=lambda x: x.get("_distance_km", 9999))
    return out


def point_selection_from_active(ap: dict | None) -> PointSelection | None:
    """Construit un PointSelection depuis active_point.json."""
    if not ap:
        return None
    return PointSelection.from_dict({
        "site_numero": ap.get("numero"),
        "point_code": ap.get("point"),
        "lat": ap.get("lat"),
        "lon": ap.get("lon"),
        "site_id": ap.get("site_id"),
        "is_mine": ap.get("is_mine", True),
        "commune": ap.get("commune"),
    })


def point_selection_from_manifest_meta(meta: dict | None) -> PointSelection | None:
    """Depuis manifest.meta (priorité coords D8)."""
    if not meta:
        return None
    lat, lon = meta.get("point_lat"), meta.get("point_lon")
    site = meta.get("n_site_tadarida")
    point = meta.get("n_point_fixe")
    if not (site or point or (lat is not None and lon is not None)):
        return None
    return PointSelection(
        site_numero=str(site or ""),
        point_code=str(point or ""),
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
        site_id=str(meta.get("vigiechiro_site_id") or ""),
        provenance=str(meta.get("point_provenance") or "mine"),
        commune=meta.get("point_commune"),
    )


def resolve_focus_coords(
    *,
    manifest_meta: dict | None = None,
    active: dict | None = None,
    sites_cache: list[dict] | None = None,
    campaign_points: list[dict] | None = None,
) -> tuple[float, float, str] | None:
    """Résout (lat, lon, label) pour le mode FOCUS carte.

    Ordre SPEC §2.2 : manifest → active_point → cache API → points campagne.
    """
    ps = point_selection_from_manifest_meta(manifest_meta)
    if ps and ps.has_coords():
        return float(ps.lat), float(ps.lon), ps.label_humain or ps.point_code  # type: ignore[arg-type]

    ap_ps = point_selection_from_active(active)
    if ap_ps and ap_ps.has_coords():
        # Si même site+point que manifest, ou manifest sans coords
        if not manifest_meta or not (
            manifest_meta.get("n_site_tadarida") and manifest_meta.get("n_point_fixe")
        ):
            return float(ap_ps.lat), float(ap_ps.lon), ap_ps.label_humain  # type: ignore[arg-type]
        if (_norm_site(manifest_meta.get("n_site_tadarida")) == ap_ps.site_numero
                and (manifest_meta.get("n_point_fixe") or "").upper() == ap_ps.point_code):
            return float(ap_ps.lat), float(ap_ps.lon), ap_ps.label_humain  # type: ignore[arg-type]

    if manifest_meta and sites_cache:
        sid = manifest_meta.get("vigiechiro_site_id")
        nom = (manifest_meta.get("n_point_fixe") or "").upper()
        numero = _norm_site(manifest_meta.get("n_site_tadarida"))
        for s in sites_cache:
            match = (sid and s.get("id") == sid) or (
                not sid and _norm_site(s.get("numero")) == numero)
            if not match:
                continue
            for pt in s.get("points") or []:
                if (pt.get("nom") or "").upper() == nom:
                    try:
                        la, lo = float(pt["lat"]), float(pt["lon"])
                        return la, lo, format_point_label(
                            numero, nom, provenance="mine")
                    except (TypeError, ValueError, KeyError):
                        pass

    if campaign_points and manifest_meta:
        nom = (manifest_meta.get("n_point_fixe") or "").upper()
        numero = _norm_site(manifest_meta.get("n_site_tadarida"))
        for p in campaign_points:
            if (_norm_site(p.get("numero") or p.get("site_numero")) == numero
                    and (p.get("point") or p.get("point_code") or "").upper() == nom):
                try:
                    return (float(p["lat"]), float(p["lon"]),
                            format_point_label(numero, nom, commune=p.get("commune")))
                except (TypeError, ValueError, KeyError):
                    pass

    return None


def campaign_points_from_sessions(
    session_paths: Iterable,
) -> list[dict]:
    """Extrait les points GPS connus des manifests d'une liste de sessions.

    Un même point (carré + Zx + coords) n'apparaît qu'**une** fois, avec
    ``n_nights`` = nombre de sessions (nuits) dessus.
    """
    from pathlib import Path
    from manifest import Manifest

    by_key: dict[tuple, dict] = {}
    for sp in session_paths:
        path = Path(sp)
        m = Manifest.load(path)
        if not m or not m.meta:
            continue
        ps = point_selection_from_manifest_meta(m.meta)
        if not ps or not ps.has_coords():
            continue
        key = (ps.site_numero, ps.point_code, round(ps.lat, 5), round(ps.lon, 5))  # type: ignore[arg-type]
        if key in by_key:
            by_key[key]["n_nights"] = int(by_key[key].get("n_nights") or 1) + 1
            continue
        by_key[key] = {
            "numero": ps.site_numero,
            "point": ps.point_code,
            "lat": ps.lat,
            "lon": ps.lon,
            "site_id": ps.site_id,
            "commune": ps.commune,
            "session": path.name,
            "n_nights": 1,
        }
    return list(by_key.values())
