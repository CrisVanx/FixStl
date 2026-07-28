# CBZ to Kindle EPUB Converter

This script converts CBZ archives (manhwa/manga) into EPUB files optimized for basic Kindle devices.
It resizes wide images to fit a Kindle screen width, and splits tall pages vertically into Kindle-height segments without scaling vertically.

## Features

- Converts `.cbz` files into `.epub`
- Keeps image quality by avoiding vertical rescaling
- Splits long pages into multiple Kindle-height pages when needed
- Supports external cover image injection
- Processes a single file or all `.cbz` files in a directory

## Requirements

- Python 3.8+
- Pillow

Install dependencies with:

```bash
python3 -m pip install Pillow
```

## Usage

From the `cbz_to_kindle` folder:

```bash
python3 convert.py my-comic.cbz
```

With a custom output file:

```bash
python3 convert.py my-comic.cbz -o my-comic.epub
```

With an external cover image:

```bash
python3 convert.py my-comic.cbz --cover cover.jpg
```

Process all CBZ files in a folder:

```bash
python3 convert.py ./my-folder/
```

## Notes

- Target Kindle resolution is `600x800`.
- Image formats supported inside CBZ: `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`.
- If a cover image is provided, it becomes the first page and is included as the EPUB cover metadata.
- The script writes an EPUB file with the same basename as the CBZ by default.

## Example

```bash
python3 convert.py SL112-123.cbz --cover portada.jpg
```

This creates `SL112-123.epub` and includes the provided `portada.jpg` as the EPUB cover.
