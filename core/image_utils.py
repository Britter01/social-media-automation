"""Image post-processing utilities.

Applies brand overlays to Imagen-generated photos using Pillow. Overlays
are composited after generation so the brand name is always spelled correctly
and styled consistently — never left to the image model to render.

Overlay design: a semi-transparent dark bar at the bottom of the image
containing the brand name (large) and tagline (small). Subtle enough to
not distract from the photo, visible enough to brand every asset.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


def add_brand_overlay(
    image_bytes: bytes,
    brand_name: str,
    tagline: str = "",
    bar_opacity: int = 175,
) -> bytes:
    """Composite a branded footer bar onto an image.

    Args:
        image_bytes: Raw PNG/JPEG bytes from Imagen.
        brand_name:  The brand name to display (e.g. "Brite Tech Lifestyle").
        tagline:     Optional tagline shown below the brand name in smaller text.
        bar_opacity: Alpha for the dark bar (0=transparent, 255=solid). Default 175.

    Returns:
        PNG bytes with the overlay applied.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning("Pillow not installed; skipping brand overlay")
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size

    # Fixed pixel sizes so the overlay looks identical regardless of image dimensions.
    bar_height = 80
    name_size  = 30
    tag_size   = 18

    # Build the overlay layer.
    overlay = Image.new("RGBA", (width, bar_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Fade from transparent at top to bar_opacity at bottom — softer edge.
    for y in range(bar_height):
        alpha = int(bar_opacity * (y / bar_height) ** 0.6)
        draw.line([(0, y), (width, y)], fill=(10, 10, 10, alpha))

    # Load fonts — Pillow 10.1+ load_default supports size; fall back gracefully.
    try:
        font_name = ImageFont.load_default(size=name_size)
        font_tag  = ImageFont.load_default(size=tag_size)
    except TypeError:
        font_name = ImageFont.load_default()
        font_tag  = font_name

    # Brand name — centred, upper portion of bar.
    name_y = int(bar_height * 0.38)
    draw.text(
        (width // 2, name_y),
        brand_name,
        font=font_name,
        fill=(255, 255, 255, 230),
        anchor="mm",
    )

    # Tagline — centred, lower portion of bar.
    if tagline:
        tag_y = int(bar_height * 0.72)
        draw.text(
            (width // 2, tag_y),
            tagline,
            font=font_tag,
            fill=(210, 210, 210, 180),
            anchor="mm",
        )

    # Composite overlay onto original.
    img.paste(overlay, (0, height - bar_height), overlay)

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    logger.debug("Brand overlay applied (%dx%d, bar=%dpx)", width, height, bar_height)
    return out.getvalue()
