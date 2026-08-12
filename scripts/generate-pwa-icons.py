#!/usr/bin/env python3
"""Build phone PWA icons from the full Car-RO mark (car + lift + RO).

The exported carro-mark-1024.png on disk is only the car outline. The complete
logo lives in the GIMP XCF (hdd1/logos or branding) and the flattened
carro-mark-full.png. Output is charcoal + brand-blue for iOS Dark Icons.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "mobile" / "public"
# Dark home-screen icons (iOS 18+): charcoal fill + brand-blue mark.
# PWAs cannot ship a separate dark/tinted variant; this is the asset
# iOS caches at Add to Home Screen and darkens further if needed.
BG = (28, 28, 30)  # iOS dark grouped / greyish black
# Same hue as app --accent (#1a4f8c), lifted so it still reads after
# iOS Dark Icons further darkens the asset.
INK = (61, 143, 214)
# Background fills the rounded square; glyph uses the usual iOS inset
# so it sits with other apps instead of kissing the top and bottom.
PAD = 0.12

XCF_CANDIDATES = (
    Path("/mnt/hdd1/logos/carro-mark-1024.xcf"),
    ROOT / "advisor" / "ui" / "src" / "assets" / "branding" / "carro-mark-1024.xcf",
)
PNG_CANDIDATES = (
    ROOT / "advisor" / "ui" / "src" / "assets" / "branding" / "carro-mark-full.png",
    Path("/mnt/hdd1/logos/carro-mark-1024.png"),
    ROOT / "advisor" / "ui" / "src" / "assets" / "branding" / "carro-mark-1024.png",
    ROOT / "docs" / "branding" / "carro-mark.png",
)


def _flatten_xcf(src: Path) -> Path | None:
    convert = shutil.which("convert") or shutil.which("magick")
    if not convert:
        return None
    dest = Path("/tmp/carro-mark-xcf-flat.png")
    cmd = [convert, str(src)]
    if Path(convert).name == "magick":
        cmd = [convert, str(src)]
    cmd += ["-background", "white", "-flatten", str(dest)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return dest if dest.is_file() else None


def _source() -> Path:
    for xcf in XCF_CANDIDATES:
        if xcf.is_file():
            flat = _flatten_xcf(xcf)
            if flat:
                return flat
    for path in PNG_CANDIDATES:
        if path.is_file():
            return path
    raise SystemExit("error: missing Car-RO mark (XCF or carro-mark-full.png)")


def _logo_mask(im):
    """L mask, 255 = logo ink (car / lift / RO)."""
    g = im.convert("L")
    w, h = g.size
    corners = [
        g.getpixel((2, 2)),
        g.getpixel((w - 3, 2)),
        g.getpixel((2, h - 3)),
        g.getpixel((w - 3, h - 3)),
    ]
    bg = sum(corners) / 4
    if bg > 127:
        from PIL import ImageOps

        return ImageOps.invert(g)
    return g


def _fit(mask, size: int):
    from PIL import Image

    bw = mask.point(lambda x: 255 if x > 12 else 0)
    box = bw.getbbox()
    if not box:
        return mask.resize((size, size), Image.Resampling.LANCZOS)
    crop = mask.crop(box)
    inner = max(8, int(size * (1 - 2 * PAD)))
    cw, ch = crop.size
    scale = min(inner / cw, inner / ch)
    nw = max(1, int(cw * scale))
    nh = max(1, int(ch * scale))
    fitted = crop.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("L", (size, size), 0)
    canvas.paste(fitted, ((size - nw) // 2, (size - nh) // 2))
    return canvas


def main() -> None:
    from PIL import Image

    OUT.mkdir(parents=True, exist_ok=True)
    src_path = _source()
    src = Image.open(src_path)
    mask = _logo_mask(src)
    sizes = {
        "icon-512.png": 512,
        "icon-192.png": 192,
        "apple-touch-icon.png": 180,
        "apple-touch-icon-167.png": 167,
        "apple-touch-icon-152.png": 152,
    }
    for name, size in sizes.items():
        m = _fit(mask, size)
        fg = Image.new("RGB", (size, size), INK)
        bg = Image.new("RGB", (size, size), BG)
        Image.composite(fg, bg, m).save(OUT / name, format="PNG", optimize=True)
    try:
        shown = src_path.relative_to(ROOT)
    except ValueError:
        shown = src_path
    print(f"wrote PWA icons from {shown} → {OUT}")


if __name__ == "__main__":
    main()
