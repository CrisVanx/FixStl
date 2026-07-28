#!/usr/bin/env python3
#!/usr/bin/env python3
"""
cbz_to_kindle_epub.py
Converts manhwa CBZ archives into EPUB files optimized for basic Kindle.
Long pages are split vertically into Kindle screen-sized segments without
resizing, preserving original quality.

Usage:
    python3 cbz_to_kindle_epub.py file.cbz
    python3 cbz_to_kindle_epub.py file.cbz -o output.epub
    python3 convert.py Epílogo.cbz --cover portada.jpg
    python3 cbz_to_kindle_epub.py folder/ --cover cover.jpg
    python3 cbz_to_kindle_epub.py folder/  (processes all CBZ files)

Target basic Kindle resolution: 600x800px
"""

import argparse
import io
import re
import sys
import zipfile
from pathlib import Path

from PIL import Image

# ── Basic Kindle resolution (input) ───────────────────────────────────────
KINDLE_W = 600
KINDLE_H = 800

# If the image is taller than this multiple of Kindle height, split it
SPLIT_RATIO_THRESHOLD = 1.2

# Supported image formats
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def natural_sort_key(s):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", str(s))]


def resize_to_kindle(img: Image.Image) -> Image.Image:
    """Scale the image so the width fits Kindle while never enlarging it."""
    orig_w, orig_h = img.size
    if orig_w <= KINDLE_W:
        return img
    scale = KINDLE_W / orig_w
    return img.resize((KINDLE_W, int(orig_h * scale)), Image.LANCZOS)


def make_cover(img: Image.Image) -> Image.Image:
    """
    Scale the cover image so it fits exactly in 600x800px while preserving
    aspect ratio, adding black letterbox bars if needed.
    """
    img = img.convert("RGB")
    img.thumbnail((KINDLE_W, KINDLE_H), Image.LANCZOS)
    canvas = Image.new("RGB", (KINDLE_W, KINDLE_H), (0, 0, 0))
    x = (KINDLE_W - img.width) // 2
    y = (KINDLE_H - img.height) // 2
    canvas.paste(img, (x, y))
    return canvas


def split_image(img: Image.Image) -> list[Image.Image]:
    """Split a tall image into Kindle-height segments."""
    img = resize_to_kindle(img)
    w, h = img.size

    if h <= KINDLE_H * SPLIT_RATIO_THRESHOLD:
        return [img]

    segments = []
    top = 0
    while top < h:
        bottom = min(top + KINDLE_H, h)
        segments.append(img.crop((0, top, w, bottom)))
        top += KINDLE_H
    return segments


def image_to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


def extract_images_from_cbz(cbz_path: Path) -> list[tuple[str, bytes]]:
    results = []
    with zipfile.ZipFile(cbz_path, "r") as zf:
        names = sorted(
            [n for n in zf.namelist() if Path(n).suffix.lower() in IMAGE_EXTS],
            key=natural_sort_key,
        )
        for name in names:
            results.append((name, zf.read(name)))
    return results


def build_epub(title: str, image_pages: list[bytes], output_path: Path,
               cover_bytes: bytes | None = None):
    """
    Build the EPUB file.
    If cover_bytes are provided, add an official cover entry so Kindle
    recognizes the cover in the library and includes it as the first page.
    """
    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype is uncompressed and must be first in the EPUB archive
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")

        css = (
            "body{margin:0;padding:0;background:#000;text-align:center;}"
            "img{display:block;margin:0 auto;max-width:100%;height:auto;}"
        )
        zf.writestr("OEBPS/style/manga.css", css)

        manifest_items = []
        spine_items = []

        # ── Cover page ───────────────────────────────────────────────────────
        cover_meta = ""
        if cover_bytes is not None:
            zf.writestr("OEBPS/images/cover.jpg", cover_bytes)
            cover_html = (
                "<?xml version='1.0' encoding='utf-8'?>"
                "<!DOCTYPE html>"
                '<html xmlns="http://www.w3.org/1999/xhtml">'
                "<head><title>Cover</title>"
                '<link rel="stylesheet" type="text/css" href="../style/manga.css"/>'
                "<style>body{background:#000;margin:0;padding:0;}"
                "img{width:100%;height:auto;}</style>"
                "</head><body>"
                '<img src="../images/cover.jpg" alt="Cover"/>'
                "</body></html>"
            )
            zf.writestr("OEBPS/pages/cover.xhtml", cover_html)

            manifest_items += [
                '<item id="cover-img" href="images/cover.jpg" '
                'media-type="image/jpeg" properties="cover-image"/>',
                '<item id="cover-page" href="pages/cover.xhtml" '
                'media-type="application/xhtml+xml"/>',
            ]
            spine_items.append('<itemref idref="cover-page"/>')
            # cover meta so Kindle recognizes it in the library
            cover_meta = '<meta name="cover" content="cover-img"/>'

        # ── Comic pages ──────────────────────────────────────────────────────
        for i, img_bytes in enumerate(image_pages):
            img_name = f"images/p{i:04d}.jpg"
            page_name = f"pages/p{i:04d}.xhtml"
            img_id = f"img{i:04d}"
            page_id = f"page{i:04d}"

            zf.writestr(f"OEBPS/{img_name}", img_bytes)
            html = (
                "<?xml version='1.0' encoding='utf-8'?>"
                "<!DOCTYPE html>"
                '<html xmlns="http://www.w3.org/1999/xhtml">'
                f"<head><title>p{i+1}</title>"
                '<link rel="stylesheet" type="text/css" href="../style/manga.css"/>'
                "</head><body>"
                f'<img src="../{img_name}" alt="p{i+1}"/>'
                "</body></html>"
            )
            zf.writestr(f"OEBPS/{page_name}", html)

            manifest_items += [
                f'<item id="{img_id}" href="{img_name}" media-type="image/jpeg"/>',
                f'<item id="{page_id}" href="{page_name}" media-type="application/xhtml+xml"/>',
            ]
            spine_items.append(f'<itemref idref="{page_id}"/>')

        # ── OPF package file ───────────────────────────────────────────────
        manifest_xml = "\n    ".join(manifest_items)
        spine_xml = "\n    ".join(spine_items)
        opf = f"""<?xml version='1.0' encoding='utf-8'?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:language>es</dc:language>
    <dc:identifier id="uid">manhwa-{title}</dc:identifier>
    <meta name="fixed-layout" content="true"/>
    <meta name="original-resolution" content="{KINDLE_W}x{KINDLE_H}"/>
    <meta name="RegionMagnification" content="false"/>
    {cover_meta}
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="css" href="style/manga.css" media-type="text/css"/>
    {manifest_xml}
  </manifest>
  <spine toc="ncx">
    {spine_xml}
  </spine>
</package>"""
        zf.writestr("OEBPS/content.opf", opf)

        # ── NCX table of contents ───────────────────────────────────────────
        all_pages = (["cover"] if cover_bytes else []) + [f"p{i:04d}" for i in range(len(image_pages))]
        nav_points = "\n".join(
            f'<navPoint id="np{i}" playOrder="{i+1}">'
            f'<navLabel><text>{name}</text></navLabel>'
            f'<content src="pages/{name}.xhtml"/></navPoint>'
            for i, name in enumerate(all_pages)
        )
        ncx = f"""<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"
  "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="manhwa-{title}"/></head>
  <docTitle><text>{title}</text></docTitle>
  <navMap>{nav_points}</navMap>
</ncx>"""
        zf.writestr("OEBPS/toc.ncx", ncx)

        # ── container.xml ────────────────────────────────────────────────────
        zf.writestr(
            "META-INF/container.xml",
            "<?xml version='1.0' encoding='utf-8'?>"
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            "<rootfiles>"
            '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            "</rootfiles></container>",
        )


def load_cover(cover_path: Path) -> bytes:
    """Load and prepare the cover image at exact Kindle size."""
    img = Image.open(cover_path)
    cover_img = make_cover(img)
    return image_to_bytes(cover_img)


def process_cbz(cbz_path: Path, output_path: Path | None = None,
                cover_path: Path | None = None):
    if output_path is None:
        output_path = cbz_path.with_suffix(".epub")

    print(f"\n📖 Procesando: {cbz_path.name}")
    print(f"   → Salida:    {output_path.name}")

    raw_images = extract_images_from_cbz(cbz_path)
    print(f"   → {len(raw_images)} imágenes encontradas en el CBZ")

    # external cover image
    cover_bytes = None
    if cover_path:
        try:
            cover_bytes = load_cover(cover_path)
            print(f"   🖼 Portada:   {cover_path.name}")
        except Exception as e:
            print(f"   ⚠ No se pudo cargar la portada ({e}), se omitirá.")

    all_page_bytes = []
    total_segments = 0

    for name, img_bytes in raw_images:
        try:
            img = Image.open(io.BytesIO(img_bytes))
        except Exception as e:
            print(f"   ⚠ Saltando {name}: {e}")
            continue

        segments = split_image(img)
        total_segments += len(segments)

        if len(segments) > 1:
            print(f"   ✂ {Path(name).name}: {img.size[0]}×{img.size[1]}px → {len(segments)} segmentos")

        for seg in segments:
            all_page_bytes.append(image_to_bytes(seg))

    print(f"   → {total_segments} páginas en el EPUB final")

    build_epub(cbz_path.stem, all_page_bytes, output_path, cover_bytes=cover_bytes)

    size_mb = output_path.stat().st_size / 1_048_576
    print(f"   ✅ Listo — {size_mb:.1f} MB → {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convierte CBZ de manhwa a EPUB optimizado para Kindle básico.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", nargs="+", help="Archivo(s) .cbz o carpeta con archivos .cbz")
    parser.add_argument("-o", "--output", help="Ruta de salida (solo con un archivo único)")
    parser.add_argument(
        "--cover",
        help="Imagen de portada externa (JPG, PNG). Se añade como portada oficial del EPUB.",
        metavar="IMAGEN",
    )
    args = parser.parse_args()

    cbz_files = []
    for inp in args.input:
        p = Path(inp)
        if p.is_dir():
            cbz_files.extend(sorted(p.glob("*.cbz"), key=natural_sort_key))
            cbz_files.extend(sorted(p.glob("*.CBZ"), key=natural_sort_key))
        elif p.suffix.lower() == ".cbz" and p.exists():
            cbz_files.append(p)
        else:
            print(f"⚠ No encontrado o no es CBZ: {inp}", file=sys.stderr)

    if not cbz_files:
        print("❌ No se encontraron archivos CBZ.", file=sys.stderr)
        sys.exit(1)

    if args.output and len(cbz_files) > 1:
        print("⚠ -o solo funciona con un archivo único. Se ignorará.", file=sys.stderr)
        args.output = None

    cover_path = Path(args.cover) if args.cover else None
    if cover_path and not cover_path.exists():
        print(f"❌ Portada no encontrada: {cover_path}", file=sys.stderr)
        sys.exit(1)

    print(f"🗂  {len(cbz_files)} archivo(s) a convertir")
    print(f"📱 Resolución objetivo: {KINDLE_W}×{KINDLE_H}px (Kindle básico)")

    for cbz_file in cbz_files:
        out = Path(args.output) if args.output else None
        process_cbz(cbz_file, out, cover_path=cover_path)

    print("\n🎉 ¡Conversión completada!")
    print("   Envía el EPUB a tu Kindle con 'Send to Kindle' o por cable USB.")


if __name__ == "__main__":
    main()