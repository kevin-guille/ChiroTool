"""
make_icon.py — génère icon.ico pour ChiroTool.

Design : cercle bleu uni avec silhouette de chauve-souris blanche au centre.
Style simple, plat, reconnaissable même en 16×16 (taskbar Windows).

Produit icon.ico multi-résolutions (16, 32, 48, 64, 128, 256) embarquable
par PyInstaller via `icon="icon.ico"` dans le .spec.

Exécution : python make_icon.py
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw


# Bleu cohérent avec l'identité CustomTkinter (légèrement plus saturé que
# le bleu par défaut de CTk, pour que l'icône ressorte en taskbar).
BLUE_FILL = (31, 114, 199, 255)       # bleu moyen
BLUE_DARKER = (22, 86, 158, 255)      # bordure plus foncée
WHITE = (255, 255, 255, 255)


def _draw_bat(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float):
    """Dessine une silhouette stylisée de chauve-souris centrée en (cx, cy).

    Style : 2 ailes + corps + 2 petites oreilles. Tout en blanc.
    La forme est construite en Bezier approximatif via polygones (fiable
    à toutes les tailles, pas d'anti-alias cassé en 16×16).
    """
    s = scale  # facteur d'échelle

    # Corps central (ovale vertical court)
    body_w = 5 * s
    body_h = 8 * s
    draw.ellipse(
        [cx - body_w / 2, cy - body_h / 2,
         cx + body_w / 2, cy + body_h / 2],
        fill=WHITE,
    )

    # 2 petites oreilles triangulaires au sommet du corps
    ear_h = 3 * s
    ear_w = 2 * s
    # oreille gauche
    draw.polygon([
        (cx - body_w / 4, cy - body_h / 2),
        (cx - body_w / 2 - ear_w / 2, cy - body_h / 2 - ear_h),
        (cx - body_w / 4 + ear_w / 2, cy - body_h / 2 - ear_h * 0.3),
    ], fill=WHITE)
    # oreille droite (miroir)
    draw.polygon([
        (cx + body_w / 4, cy - body_h / 2),
        (cx + body_w / 2 + ear_w / 2, cy - body_h / 2 - ear_h),
        (cx + body_w / 4 - ear_w / 2, cy - body_h / 2 - ear_h * 0.3),
    ], fill=WHITE)

    # Aile gauche — polygone avec 3 "doigts" pour l'effet membrane
    wing_span = 14 * s   # demi-envergure
    wing_top = cy - 3 * s
    wing_bot = cy + 5 * s
    left_wing = [
        (cx - body_w / 2 + 0.5, wing_top),                  # attache haute
        (cx - wing_span * 0.4, wing_top - 2 * s),           # pic 1
        (cx - wing_span * 0.7, cy - 1 * s),                  # pic 2
        (cx - wing_span, cy + 2 * s),                        # pic extrême
        (cx - wing_span * 0.75, cy + 3.5 * s),              # creux
        (cx - wing_span * 0.5, cy + 3 * s),                  # pic 3
        (cx - wing_span * 0.25, cy + 4.5 * s),              # creux
        (cx - body_w / 2 + 0.5, wing_bot),                   # attache basse
    ]
    draw.polygon(left_wing, fill=WHITE)

    # Aile droite — miroir de la gauche
    right_wing = [(cx * 2 - x, y) for (x, y) in left_wing]
    draw.polygon(right_wing, fill=WHITE)


def _make_icon(size: int) -> Image.Image:
    """Génère une image RGBA d'un disque bleu avec chauve-souris blanche."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Cercle de fond (bordure légèrement plus foncée pour définir le contour
    # quand l'icône est posée sur un fond clair)
    pad = max(1, size // 32)   # marge pour que le cercle ne touche pas les bords
    draw.ellipse([pad, pad, size - pad, size - pad],
                 fill=BLUE_FILL, outline=BLUE_DARKER,
                 width=max(1, size // 64))

    # Chauve-souris centrée. Le scale est calibré pour que la silhouette
    # occupe ~60 % du diamètre (lisible même en 16×16).
    scale = size / 64.0
    _draw_bat(draw, size // 2, size // 2, scale)

    return img


def _write_multi_ico(ico_path: Path, images: list[Image.Image]):
    """Écrit un .ico multi-résolution.

    Contrairement à PIL par défaut (qui écrit du BMP pour toutes les tailles),
    on force le format PNG pour les entrées ≥ 64 px — c'est ce que Windows
    Explorer attend pour afficher l'icône en vignette d'un .exe sur un
    écran haute résolution. Avec du BMP pur, Explorer retombe parfois sur
    l'icône générique.

    Format ICO : ICONDIR (6 o) + N × ICONDIRENTRY (16 o chacun) + données.
    Spec : https://en.wikipedia.org/wiki/ICO_(file_format)
    """
    import io
    import struct

    # Tri décroissant pour que Windows prenne d'abord la plus grande
    images = sorted(images, key=lambda im: im.size[0], reverse=True)

    # Encode chaque image en PNG (taille ≥ 64) ou BMP (taille < 64, pour
    # compat Win XP/7 très anciens). En pratique Windows 10+ accepte PNG
    # partout, on pourrait tout mettre en PNG, mais 16×16 et 32×32 en BMP
    # restent une sécurité.
    encoded: list[tuple[Image.Image, bytes, str]] = []
    for im in images:
        w, _h = im.size
        if w >= 64:
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            encoded.append((im, buf.getvalue(), "png"))
        else:
            # BMP DIB pour petites tailles : PIL produit un BMP avec header
            # 40 bytes. Pour un ICO, on doit enlever le BITMAPFILEHEADER
            # (14 bytes) et doubler la hauteur dans le header DIB (pour
            # représenter image + masque AND), en laissant les pixels tels quels.
            buf = io.BytesIO()
            im.save(buf, format="BMP")
            bmp = buf.getvalue()
            # Skip le BITMAPFILEHEADER (14 bytes)
            dib = bmp[14:]
            # Patch le champ height dans le BITMAPINFOHEADER (offset 8..12)
            # → doubler pour tenir compte du masque AND (même s'il est vide)
            height = struct.unpack_from("<i", dib, 8)[0]
            dib = dib[:8] + struct.pack("<i", height * 2) + dib[12:]
            # Append le masque AND (1 bit par pixel, tout à 0 car alpha dans RGBA)
            mask_row_bytes = ((w + 31) // 32) * 4
            mask = b"\x00" * mask_row_bytes * w
            encoded.append((im, dib + mask, "bmp"))

    # Construit le .ico
    n = len(encoded)
    header = struct.pack("<HHH", 0, 1, n)  # reserved=0, type=1(icon), count

    # ICONDIRENTRY (16 bytes each)
    # Les données commencent après header + N entries
    data_offset = 6 + 16 * n
    entries = []
    blobs = []
    for im, data, _fmt in encoded:
        w, h = im.size
        # Windows exige 0 dans les champs width/height si ≥ 256
        bw = 0 if w >= 256 else w
        bh = 0 if h >= 256 else h
        entry = struct.pack(
            "<BBBBHHII",
            bw, bh,         # width, height
            0,              # color palette (0 = non utilisé)
            0,              # reserved
            1,              # color planes
            32,             # bits per pixel
            len(data),      # bytes in resource
            data_offset,    # offset from start of file
        )
        entries.append(entry)
        blobs.append(data)
        data_offset += len(data)

    ico_path.write_bytes(header + b"".join(entries) + b"".join(blobs))


def main():
    here = Path(__file__).parent
    sizes = [16, 32, 48, 64, 128, 256]
    images = [_make_icon(s) for s in sizes]

    # PNG 256 pour aperçu rapide
    preview = here / "icon_256.png"
    images[-1].save(preview, format="PNG")

    # ICO multi-résolution (PNG pour ≥64, BMP pour les petites)
    ico = here / "icon.ico"
    _write_multi_ico(ico, images)

    print(f"  OK  {preview}  ({preview.stat().st_size // 1024} KB)")
    print(f"  OK  {ico}  ({ico.stat().st_size // 1024} KB, {len(sizes)} tailles, "
          f"PNG pour >=64)")


if __name__ == "__main__":
    main()
