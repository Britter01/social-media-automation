"""Image post-processing — brand overlay compositing via Pillow.

Applies the Brite Tech Lifestyle wordmark to every Imagen-generated image
so branding is always correct and consistent, regardless of what the image
model renders in the photo itself.

Overlay design (matches brand-kit footer / platform wordmark spec):
  • Pure black bar at the bottom of the image
  • "Brite" — Figtree Bold 700, white, tight tracking (−4%)
  • "TECH LIFESTYLE" — Figtree Regular, UPPERCASE, wide tracking (+22%), white 28% opacity
  • Thin Brite Blue (#0066CC) rule above the bar — matches YouTube thumbnail spec

Fonts are downloaded from the jsDelivr/Fontsource CDN on first use and cached
in the system temp directory so Railway containers pick them up automatically.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Brand tokens (from brand-kit CSS variables)                                 #
# --------------------------------------------------------------------------- #
_BLACK       = (0, 0, 0)
_WHITE       = (255, 255, 255)
_BRITE_BLUE  = (0, 102, 204)        # #0066CC

# Wordmark opacities
_BRITE_ALPHA = 255                  # "Brite" — full white
_SUB_ALPHA   = 71                   # "TECH LIFESTYLE" — white at ~28%

# Bar dimensions (fixed px — consistent across all aspect ratios)
_BAR_H       = 88                   # total bar height
_RULE_H      = 2                    # blue accent rule above bar
_PAD_X       = 24                   # horizontal padding from edge

# Font sizes
_SIZE_BRITE  = 36                   # "Brite" display size
_SIZE_SUB    = 11                   # "TECH LIFESTYLE" size

# Letter-spacing simulation (extra pixels between characters)
_TRACKING_BRITE = -1                # slight tightening for the hero name
_TRACKING_SUB   = 3                 # wide tracking for the subtitle

# --------------------------------------------------------------------------- #
# Font loading                                                                 #
# --------------------------------------------------------------------------- #
_FONT_CACHE_DIR = os.path.join(tempfile.gettempdir(), "btl_fonts")
_FONT_URLS = {
    "figtree-bold":    "https://cdn.jsdelivr.net/fontsource/fonts/figtree@latest/latin-700-normal.ttf",
    "figtree-regular": "https://cdn.jsdelivr.net/fontsource/fonts/figtree@latest/latin-400-normal.ttf",
}


def _get_font(name: str, size: int):
    """Load a TrueType font, downloading and caching it on first use."""
    from PIL import ImageFont

    os.makedirs(_FONT_CACHE_DIR, exist_ok=True)
    path = os.path.join(_FONT_CACHE_DIR, f"{name}.ttf")

    if not os.path.exists(path):
        url = _FONT_URLS.get(name)
        if url:
            try:
                import requests
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                with open(path, "wb") as fh:
                    fh.write(resp.content)
                logger.info("Downloaded font %s -> %s", name, path)
            except Exception:
                logger.warning("Could not download font %s; using default", name, exc_info=True)
                path = None

    if path and os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass

    # Fallback — Pillow built-in bitmap font (Pillow 10.1+ supports size param)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_width(font, text: str, tracking: int = 0) -> int:
    """Measure the rendered width of ``text`` including extra tracking."""
    try:
        bbox = font.getbbox(text)
        base_w = bbox[2] - bbox[0]
    except Exception:
        base_w = len(text) * (font.size if hasattr(font, "size") else 10)
    return base_w + tracking * max(0, len(text) - 1)


def _draw_tracked(draw, xy: tuple, text: str, font, fill: tuple, tracking: int = 0) -> None:
    """Draw text with per-character letter-spacing (tracking).

    Pillow doesn't support CSS letter-spacing natively, so we place each
    character individually with the extra gap applied between them.
    """
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        try:
            bbox = font.getbbox(char)
            char_w = bbox[2] - bbox[0]
        except Exception:
            char_w = font.size if hasattr(font, "size") else 10
        x += char_w + tracking


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def add_brand_overlay(
    image_bytes: bytes,
    brand_name: str = "Brite Tech Lifestyle",
    tagline: str = "",
    bar_opacity: int = 255,
) -> bytes:
    """Composite the Brite Tech Lifestyle wordmark onto the bottom of an image.

    Args:
        image_bytes: Raw PNG/JPEG bytes from Imagen.
        brand_name:  Ignored — overlay always uses the canonical two-line wordmark.
        tagline:     Ignored — the bar is kept clean per brand-kit footer spec.
        bar_opacity: Alpha for the black bar (default 255 = solid).

    Returns:
        PNG bytes with the brand wordmark applied.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("Pillow not installed; skipping brand overlay")
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size
    total_h = _BAR_H + _RULE_H

    font_brite = _get_font("figtree-bold",    _SIZE_BRITE)
    font_sub   = _get_font("figtree-regular", _SIZE_SUB)

    # ── Build the overlay layer ──────────────────────────────────────────────
    overlay = Image.new("RGBA", (width, total_h), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)

    # Solid black bar
    draw.rectangle(
        [(0, _RULE_H), (width, total_h)],
        fill=(*_BLACK, bar_opacity),
    )

    # Brite Blue accent rule at top edge (matches YouTube thumbnail spec)
    draw.rectangle(
        [(0, 0), (width, _RULE_H)],
        fill=(*_BRITE_BLUE, 255),
    )

    # ── "Brite" — centred, bold, white ──────────────────────────────────────
    brite_w = _text_width(font_brite, "Brite", _TRACKING_BRITE)
    brite_x = (width - brite_w) // 2
    brite_y = _RULE_H + 10                          # top padding inside bar

    _draw_tracked(
        draw,
        (brite_x, brite_y),
        "Brite",
        font_brite,
        (*_WHITE, _BRITE_ALPHA),
        _TRACKING_BRITE,
    )

    # ── "TECH LIFESTYLE" — centred, wide-tracked, faded ────────────────────
    sub_text = "TECH LIFESTYLE"
    sub_w    = _text_width(font_sub, sub_text, _TRACKING_SUB)
    sub_x    = (width - sub_w) // 2
    sub_y    = brite_y + _SIZE_BRITE + 6            # below "Brite" with gap

    _draw_tracked(
        draw,
        (sub_x, sub_y),
        sub_text,
        font_sub,
        (*_WHITE, _SUB_ALPHA),
        _TRACKING_SUB,
    )

    # ── Composite onto original ──────────────────────────────────────────────
    img.paste(overlay, (0, height - total_h), overlay)

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    logger.debug("Brand overlay applied (%dx%d)", width, height)
    return out.getvalue()
