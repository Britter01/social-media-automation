"""Image post-processing — brand overlay compositing via Pillow.

Composites a pre-made transparent-background PNG logo onto Imagen-generated
photos.  No text rendering, no font downloads.

Two logo variants are available:
  • final_logo_transparent_allwhite.png — white text; use on dark/photo backgrounds
  • final_logo_transparent_allblack.png — black text; use on light/white backgrounds

The logo PNG is 1024×1024 with the actual wordmark centred inside it.
The content bounding box (from alpha inspection) is (264, 386, 758, 623), so
the logo is cropped to that region before scaling to keep sizing predictable.

Logo placement:
  The four corners of the image are scored by edge density (text and busy
  graphics produce high-contrast edges).  The logo is placed in whichever
  corner has the least activity, keeping it away from any writing already
  present in the photo.

Logo colour:
  After the corner is chosen, the average brightness of that region is
  measured.  Light backgrounds get the dark/black logo; dark backgrounds
  get the white logo.  No manual override needed.
"""

from __future__ import annotations

import io
import logging
import os

logger = logging.getLogger(__name__)

# Resolve logo paths relative to this file's package root
_ASSETS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "assets", "logos"))
_LOGO_WHITE = os.path.join(_ASSETS_DIR, "final_logo_transparent_allwhite.png")
_LOGO_BLACK = os.path.join(_ASSETS_DIR, "final_logo_transparent_allblack.png")

# Layout constants — small, placed in the quietest corner
_LOGO_WIDTH_RATIO = 0.15  # logo width as a fraction of the photo width
_LOGO_MIN_WIDTH = 80  # pixels
_LOGO_MAX_WIDTH = 160  # pixels
_PAD = 18  # pixels of padding from each edge

# Brightness threshold: regions above this are considered "light" → use dark logo
_LIGHT_THRESHOLD = 140  # 0–255 greyscale average

# Bar-crop settings
_MAX_BAR_RATIO = 0.22  # ignore bars taller than 22% of image (probably intentional design)
_MIN_BAR_ROWS = 4  # require at least this many consecutive low-variance rows to call it a bar
_BAR_VAR_FRACTION = 0.20  # a bar row must have <20% of the median photo variance

# Pre-computed content bbox inside the 1024×1024 logo canvas (alpha getbbox result)
_LOGO_CONTENT_BOX = (264, 386, 758, 623)


def _crop_hallucinated_bars(img):
    """Detect and remove solid-colour header/footer bars hallucinated by Imagen.

    Measures per-row pixel variance in grayscale.  A flat-colour bar (text
    header/footer added by Imagen) has very low variance; real photo content
    has high variance.  Consecutive low-variance rows at the top and/or bottom
    are cropped off and the image is resized back to its original dimensions so
    the aspect ratio is preserved.

    Returns the (possibly cropped+resized) image unchanged if no bars are found.
    """
    from PIL import Image

    gray = img.convert("L")
    w, h = img.size
    max_rows = int(h * _MAX_BAR_RATIO)
    sample_step = max(1, w // 64)  # sample ~64 pixels per row for speed

    def _row_var(y: int) -> float:
        row = [gray.getpixel((x, y)) for x in range(0, w, sample_step)]
        mean = sum(row) / len(row)
        return sum((p - mean) ** 2 for p in row) / len(row)

    # Estimate typical photo variance from the middle third of the image
    mid_ys = range(h // 3, 2 * h // 3, max(1, h // 30))
    mid_vars = [_row_var(y) for y in mid_ys]
    if not mid_vars:
        return img
    mid_median = sorted(mid_vars)[len(mid_vars) // 2]
    bar_threshold = mid_median * _BAR_VAR_FRACTION

    # Scan from top: count consecutive low-variance rows
    top_crop = 0
    run = 0
    for y in range(max_rows):
        if _row_var(y) < bar_threshold:
            run += 1
        else:
            break
    if run >= _MIN_BAR_ROWS:
        top_crop = run

    # Scan from bottom
    bottom_crop = h
    run = 0
    for y in range(h - 1, h - 1 - max_rows, -1):
        if _row_var(y) < bar_threshold:
            run += 1
        else:
            break
    if run >= _MIN_BAR_ROWS:
        bottom_crop = h - run

    if top_crop == 0 and bottom_crop == h:
        return img  # nothing to crop

    cropped = img.crop((0, top_crop, w, bottom_crop))
    result = cropped.resize((w, h), Image.LANCZOS)
    logger.info(
        "Cropped hallucinated bars: top=%dpx bottom=%dpx on %dx%d image",
        top_crop,
        h - bottom_crop,
        w,
        h,
    )
    return result


def _quietest_corner(
    img,
    logo_w: int,
    logo_h: int,
    pad: int,
) -> tuple[int, int]:
    """Return (x, y) for the corner with the lowest edge density.

    Each corner is sampled over the exact region the logo would occupy.
    Edge density is a proxy for text and busy graphics — the logo is placed
    in the corner where the sum of edge intensities is lowest.
    """
    from PIL import ImageFilter

    width, height = img.size

    candidates = {
        "top_right": (width - logo_w - pad, pad),
        "top_left": (pad, pad),
        "bottom_right": (width - logo_w - pad, height - logo_h - pad),
        "bottom_left": (pad, height - logo_h - pad),
    }

    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)

    best_pos = candidates["top_right"]  # default preference
    best_score: float = float("inf")

    for pos in candidates.values():
        x, y = pos
        region = edges.crop((x, y, x + logo_w, y + logo_h))
        score = sum(region.getdata())
        if score < best_score:
            best_score = score
            best_pos = pos

    return best_pos


def _corner_is_light(img, x: int, y: int, w: int, h: int) -> bool:
    """Return True if the average greyscale brightness of the region exceeds the threshold."""
    region = img.crop((x, y, x + w, y + h)).convert("L")
    pixels = list(region.getdata())
    return (sum(pixels) / len(pixels)) > _LIGHT_THRESHOLD


def add_brand_overlay(
    image_bytes: bytes,
    brand_name: str = "Brite Tech Lifestyle",
    tagline: str = "",
    bar_opacity: int = 255,
    dark_logo: bool = False,
) -> bytes:
    """Composite the brand logo PNG onto *image_bytes*.

    Scales the logo to ~15% of the image width, places it in whichever corner
    has the least visual activity, then auto-selects white or black logo based
    on the brightness of that corner region.

    Returns PNG bytes with the logo applied.  If Pillow is unavailable or the
    logo file is missing, the original bytes are returned unchanged.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed; skipping brand overlay")
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size

    # Remove any solid-colour header/footer bar hallucinated by Imagen
    img = _crop_hallucinated_bars(img)

    # Crop to just the visible wordmark — removes blank transparent margins
    logo_ref_path = _LOGO_WHITE  # use either variant just to get dimensions
    if not os.path.exists(logo_ref_path):
        logger.warning("Brand logo not found at %s; skipping overlay", logo_ref_path)
        return image_bytes

    try:
        logo_full_ref = Image.open(logo_ref_path).convert("RGBA")
    except Exception:
        logger.warning("Could not load brand logo; skipping overlay", exc_info=True)
        return image_bytes

    logo_cropped_ref = logo_full_ref.crop(_LOGO_CONTENT_BOX)

    # Scale proportionally to a sensible width for this image
    target_w = int(max(_LOGO_MIN_WIDTH, min(_LOGO_MAX_WIDTH, width * _LOGO_WIDTH_RATIO)))
    target_h = int(logo_cropped_ref.height * target_w / logo_cropped_ref.width)

    # Pick the corner furthest from any writing or busy graphics
    paste_x, paste_y = _quietest_corner(img, target_w, target_h, _PAD)

    # Auto-select logo colour: light background → black logo, dark → white logo
    light_bg = _corner_is_light(img, paste_x, paste_y, target_w, target_h)
    logo_path = _LOGO_BLACK if light_bg else _LOGO_WHITE
    logger.debug(
        "Corner brightness: %s → using %s logo",
        "light" if light_bg else "dark",
        "black" if light_bg else "white",
    )

    try:
        logo_full = Image.open(logo_path).convert("RGBA")
    except Exception:
        logger.warning("Could not load brand logo %s; skipping overlay", logo_path, exc_info=True)
        return image_bytes

    logo_cropped = logo_full.crop(_LOGO_CONTENT_BOX)
    logo_scaled = logo_cropped.resize((target_w, target_h), Image.LANCZOS)

    # Composite logo onto a blank RGBA layer then merge with photo
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay.paste(logo_scaled, (paste_x, paste_y), logo_scaled)
    img = Image.alpha_composite(img, overlay)

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    logger.debug("Brand overlay applied (%dx%d) at (%d,%d)", width, height, paste_x, paste_y)
    return out.getvalue()
