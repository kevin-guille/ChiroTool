"""
build_pdf.py — convertit TUTORIEL.md en un beau PDF partageable.

Pipeline : Markdown → HTML (avec template CSS soigné) → PDF via Chrome headless.

- Identité visuelle ChiroTool (bleu, chauve-souris)
- Page de garde
- Encadrés stylés pour les notes / astuces / emplacements de captures
- Images embarquées en base64 (PDF autonome)
- Sauts de page intelligents + pieds de page numérotés

Exécution : python docs/build_pdf.py
Sortie : docs/ChiroTool-Tutoriel.pdf
"""

from __future__ import annotations

import base64
import re
import subprocess
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))            # accès à version.py
try:
    from version import __version__ as APP_VERSION
except Exception:
    APP_VERSION = "?"
MD = HERE / "TUTORIEL.md"
CAPTURES = HERE / "captures"
OUT_HTML = HERE / "_tutoriel_render.html"
OUT_PDF = HERE / "ChiroTool-Tutoriel.pdf"

BLEU = "#1f6feb"
BLEU_FONCE = "#0d419d"


def _img_b64(path: Path) -> str:
    """Encode une image en data-URI base64."""
    if not path.is_file():
        return ""
    ext = path.suffix.lstrip(".").lower()
    mime = "image/png" if ext == "png" else f"image/{ext}"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def transform_markdown(md_text: str) -> str:
    """Pré-traite le markdown avant conversion HTML.

    - Retire le bloc <div align=center> de garde (géré par la page de garde HTML)
    - Transforme les balises « 📸 [Capture XX — … ] » en encadrés HTML
    - Transforme les blockquotes 💡 / ⚠ / 📸 en classes CSS dédiées
    """
    # Retire la bannière markdown initiale (premier <div align="center"> ... </div>)
    md_text = re.sub(r'<div align="center">.*?</div>', '', md_text,
                      count=1, flags=re.DOTALL)

    # Bloc(s) centré(s) restant(s) (ex. message de fin) : Markdown n'interprète
    # pas *italique* / **gras** dans du HTML brut → on les convertit à la main.
    def _center_repl(m):
        inner = m.group(1).strip()
        inner = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', inner)
        inner = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', inner)
        paras = [p.strip().replace("\n", " ") for p in inner.split("\n\n") if p.strip()]
        body = "<br>".join(paras)
        return f'<div class="center-msg">{body}</div>'
    md_text = re.sub(r'<div align="center">(.*?)</div>', _center_repl,
                      md_text, flags=re.DOTALL)

    # Reconstitue les balises de captures wrappées sur plusieurs lignes :
    # un bloc de lignes "> ..." qui contient 📸 est aplati en une seule ligne.
    md_text = re.sub(
        r'(>\s*📸\s*\*\*\[.*?\]\*\*)',
        lambda m: " ".join(s.lstrip("> ").strip()
                            for s in m.group(1).split("\n")),
        md_text, flags=re.DOTALL,
    )

    lines = md_text.split("\n")
    out = []
    for line in lines:
        # Emplacements de captures : 📸 **[Capture XX — texte]** (aplati)
        m = re.match(r'\s*>?\s*📸\s*\*\*\[(.+?)\]\*\*', line)
        if m:
            txt = m.group(1)
            out.append(_capture_html(txt))
            continue
        out.append(line)
    return "\n".join(out)


# Mapping numéro de capture → préfixe du fichier attendu dans captures/
_CAPTURE_FILES = {
    1: "01-exe-explorateur", 2: "02-onboarding-token",
    3: "03-onboarding-workspace", 4: "04-prefs-materiels",
    5: "05-fenetre-principale", 6: "06-vue-session",
    7: "07-wizard-metadonnees", 8: "08-progression",
    9: "09-wizard-participation", 10: "10-prefs-nettoyage",
    11: "11-recap-nettoyage", 12: "12-mode-batch", 13: "13-registre",
    14: "14-validation", 15: "15-synthesis",
}


def _capture_html(txt: str) -> str:
    """Si la vraie capture existe dans captures/, l'embarque ; sinon emplacement.

    Le numéro est extrait de « Capture NN — … ». On cherche un PNG/JPG dont le
    nom commence par le préfixe attendu (ex. `06-vue-session*.png`). Dès que
    l'utilisateur dépose ses captures (correctement nommées), elles remplacent
    automatiquement les encadrés pointillés — aucune modif du markdown requise.
    """
    m = re.search(r'Capture\s+(\d+)', txt)
    if m:
        num = int(m.group(1))
        prefix = _CAPTURE_FILES.get(num)
        if prefix:
            hits = sorted(CAPTURES.glob(f"{prefix}*"))
            hits = [h for h in hits if h.suffix.lower() in (".png", ".jpg", ".jpeg")]
            if hits:
                b64 = _img_b64(hits[0])
                if b64:
                    return (
                        f'<figure class="capture-real">'
                        f'<img src="{b64}" alt="{txt}">'
                        f'<figcaption>{txt}</figcaption></figure>'
                    )
    return (
        f'<div class="capture-box"><span class="cap-icon">📸</span>'
        f'<span class="cap-text">{txt}</span></div>'
    )


def style_callouts(html: str) -> str:
    """Transforme les <blockquote> contenant 💡 / ⚠ / Note en encadrés stylés."""
    def repl(m):
        inner = m.group(1)
        cls = "note"
        if "💡" in inner:
            cls = "tip"
        elif "⚠" in inner or "Note Windows" in inner or "attention" in inner.lower():
            cls = "warn"
        return f'<div class="callout {cls}">{inner}</div>'
    return re.sub(r'<blockquote>(.*?)</blockquote>', repl, html, flags=re.DOTALL)


def build_html() -> str:
    md_text = MD.read_text(encoding="utf-8")
    md_text = transform_markdown(md_text)

    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "attr_list"],
    )
    body = style_callouts(body)
    # supprime le séparateur juste avant le message de fin (évite une page orpheline)
    body = re.sub(r'<hr\s*/?>\s*(<div class="center-msg">)', r'\1', body)

    # Remplace les <img src="captures/...png"> par du base64
    def img_repl(m):
        src = m.group(1)
        name = src.split("/")[-1]
        b64 = _img_b64(CAPTURES / name)
        if not b64:
            return m.group(0)
        return f'<img src="{b64}"'
    body = re.sub(r'<img src="(captures/[^"]+)"', img_repl, body)

    icon_b64 = _img_b64(CAPTURES / "icon_256.png")

    css = f"""
    @page {{
        size: A4;
        margin: 14mm 16mm 14mm 16mm;
        @bottom-center {{
            content: "ChiroTool · Tutoriel utilisateur · page " counter(page);
            font-size: 8pt; color: #999;
        }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        font-size: 10.5pt; line-height: 1.55; color: #222;
        margin: 0; padding: 0;
    }}
    /* Page de garde */
    .cover {{
        text-align: center;
        padding-top: 60mm;
        page-break-after: always;
        height: 100vh;
    }}
    .cover img {{ width: 110px; height: 110px; margin-bottom: 18px; }}
    .cover h1 {{
        font-size: 40pt; color: {BLEU}; margin: 0 0 6px 0;
        letter-spacing: -1px; border: none;
    }}
    .cover .sub {{ font-size: 15pt; color: #444; margin-bottom: 4px; font-weight: 600; }}
    .cover .proto {{ font-size: 11pt; color: #777; font-style: italic; }}
    .cover .ver {{
        margin-top: 36px; font-size: 11pt; color: #999;
        border-top: 1px solid #e0e0e0; display: inline-block;
        padding-top: 14px;
    }}
    /* Titres */
    h1, h2, h3 {{ color: {BLEU_FONCE}; page-break-after: avoid; }}
    h2 {{
        font-size: 18pt; margin-top: 16px; margin-bottom: 6px;
        padding-bottom: 5px; border-bottom: 2.5px solid {BLEU};
    }}
    h3 {{ font-size: 13pt; margin-top: 12px; margin-bottom: 5px; color: #333; }}
    h2 + p, h3 + p {{ margin-top: 4px; }}
    p {{ margin: 6px 0; }}
    a {{ color: {BLEU}; text-decoration: none; }}
    code {{
        background: #f3f4f6; padding: 1px 5px; border-radius: 3px;
        font-family: "Consolas", monospace; font-size: 9.2pt; color: #b4002a;
    }}
    pre {{
        background: #f7f8fa; border: 1px solid #e2e4e8; border-radius: 6px;
        padding: 12px 14px; overflow-x: auto; page-break-inside: avoid;
        font-size: 8.8pt; line-height: 1.4;
    }}
    pre code {{ background: none; color: #333; padding: 0; }}
    /* Tableaux */
    table {{
        border-collapse: collapse; width: 100%; margin: 12px 0;
        font-size: 9.5pt; page-break-inside: avoid;
    }}
    th {{
        background: {BLEU}; color: white; text-align: left;
        padding: 7px 10px; font-weight: 600;
    }}
    td {{ padding: 6px 10px; border-bottom: 1px solid #e8e8e8; vertical-align: top; }}
    tr:nth-child(even) td {{ background: #fafbfc; }}
    /* Encadrés callout */
    .callout {{
        border-radius: 6px; padding: 9px 14px; margin: 10px 0;
        page-break-inside: avoid; font-size: 10pt;
    }}
    .callout p {{ margin: 4px 0; }}
    .callout.tip {{ background: #eaf5ea; border-left: 4px solid #2ea043; }}
    .callout.warn {{ background: #fff4e0; border-left: 4px solid #e6a000; }}
    .callout.note {{ background: #eef2f8; border-left: 4px solid {BLEU}; }}
    /* Emplacement de capture */
    .capture-box {{
        background: #f0f4fa; border: 1.5px dashed {BLEU};
        border-radius: 8px; padding: 16px 18px; margin: 14px 0;
        text-align: center; page-break-inside: avoid;
    }}
    .cap-icon {{ font-size: 22pt; display: block; margin-bottom: 4px; }}
    .cap-text {{ font-size: 9.5pt; color: #555; font-style: italic; }}
    /* Capture réelle embarquée */
    .capture-real {{
        margin: 14px 0; text-align: center; page-break-inside: avoid;
    }}
    .capture-real img {{
        max-width: 100%; border: 1px solid #d0d7de;
        border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }}
    .capture-real figcaption {{
        font-size: 8.8pt; color: #777; font-style: italic; margin-top: 5px;
    }}
    /* Message centré (fin de doc) */
    .center-msg {{
        text-align: center; margin: 7px 0 2px 0; color: #444;
        font-size: 10.5pt; line-height: 1.4; page-break-inside: avoid;
    }}
    .center-msg strong {{ font-size: 12.5pt; color: {BLEU_FONCE}; }}
    /* Images réelles */
    img {{ max-width: 100%; border-radius: 6px; border: 1px solid #e0e0e0; }}
    p img {{ display: block; margin: 10px auto; }}
    em {{ color: #666; }}
    ul, ol {{ margin: 8px 0; padding-left: 22px; }}
    li {{ margin: 3px 0; }}
    hr {{ border: none; border-top: 1px solid #e0e0e0; margin: 13px 0; }}
    /* Sommaire compact */
    h2#sommaire + ol {{ font-size: 10pt; }}
    blockquote {{ margin: 10px 0; }}
    """

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>ChiroTool — Tutoriel utilisateur</title>
<style>{css}</style>
</head>
<body>
  <div class="cover">
    <img src="{icon_b64}" alt="logo">
    <h1>ChiroTool</h1>
    <div class="sub">Le traitement de vos nuits chiroptères, automatisé de A à Z</div>
    <div class="proto">Outil libre pour le protocole Vigie-Chiro Point Fixe (MNHN)</div>
    <div class="ver">Version {APP_VERSION} &middot; Tutoriel utilisateur</div>
  </div>
  {body}
</body>
</html>"""
    return html


def clean_pdf_metadata(pdf_path: Path) -> None:
    """Réécrit le PDF avec des métadonnées propres (pas de nom de fichier
    interne ni d'user-agent navigateur). Sans effet si pypdf est absent."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        print("  (pypdf absent : métadonnées PDF non nettoyées)")
        return
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({
        "/Title": "ChiroTool — Tutoriel utilisateur",
        "/Author": "Kevin Guille",
        "/Subject": "Protocole Vigie-Chiro Point Fixe (MNHN)",
        "/Creator": "ChiroTool",
        "/Producer": "ChiroTool",
    })
    with open(pdf_path, "wb") as fh:
        writer.write(fh)


def find_chrome() -> str | None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if Path(c).is_file():
            return c
    return None


def main() -> int:
    html = build_html()
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"HTML genere : {OUT_HTML} ({len(html)//1024} Ko)")

    chrome = find_chrome()
    if not chrome:
        print("⚠ Chrome/Edge introuvable — le HTML est prêt, convertis-le "
              "manuellement (Imprimer → PDF dans le navigateur).")
        return 1

    # Chrome headless → PDF
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={OUT_PDF}",
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        OUT_HTML.as_uri(),
    ]
    print("Conversion PDF via Chrome headless...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if OUT_PDF.is_file():
        clean_pdf_metadata(OUT_PDF)
        size_kb = OUT_PDF.stat().st_size / 1024
        print(f"[OK] PDF genere : {OUT_PDF} ({size_kb:.0f} Ko)")
        return 0
    print("[ECHEC] generation PDF")
    print(r.stderr[:500])
    return 1


if __name__ == "__main__":
    sys.exit(main())
