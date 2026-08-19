"""
Overlay engine — the "Live Filled Preview" from Step 6.

MVP approach: rather than trying to precisely localize each printed field
on arbitrary form layouts (a hard vision problem on its own), we render a
clean "filled answer sheet" panel next to the original image, plus draw
lightweight number badges. This is honest about what's reliable in a
hackathon timeframe while still giving the live left/right preview UX
described in the spec. bbox support is wired in for fields where Gemma
does return coordinates, so it upgrades gracefully.
"""

from __future__ import annotations
from typing import List
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

from schemas.field_schema import FormField

BADGE_COLOR = (200, 30, 60)
FILLED_COLOR = (20, 120, 60)
TEXT_COLOR = (20, 20, 20)


def _shape_urdu(text: str) -> str:
    """Urdu/Arabic script needs reshaping + bidi reordering to render correctly
    with PIL, which doesn't do this natively."""
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def _load_font(size: int, urdu: bool = False) -> ImageFont.FreeTypeFont:
    # Falls back to PIL's default bitmap font if no TTF is found on the system.
    # Covers Linux, macOS, and Windows install locations for each font.
    import os
    candidates = (
        [
            # Linux (apt install fonts-noto)
            "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
            # macOS (Font Book install, user or system)
            "/Library/Fonts/NotoNastaliqUrdu-Regular.ttf",
            os.path.expanduser("~/Library/Fonts/NotoNastaliqUrdu-Regular.ttf"),
            # Windows (installed via right-click > Install)
            "C:\\Windows\\Fonts\\NotoNastaliqUrdu-Regular.ttf",
            "C:\\Windows\\Fonts\\NotoNastaliqUrdu-VariableFont_wght.ttf",
            "C:\\Windows\\Fonts\\NotoSansArabic-Regular.ttf",
        ]
        if urdu
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/Library/Fonts/Arial.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",
        ]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_bbox_overlays(original: Image.Image, fields: List[FormField]) -> Image.Image:
    """Draw badges/answers directly on the original image for fields that DO
    have bounding boxes from Gemma. Fields without bboxes are skipped here
    and instead shown in the answer-sheet panel (see render_answer_sheet)."""
    img = original.copy()
    draw = ImageDraw.Draw(img)
    font = _load_font(16)

    for f in fields:
        if not f.bbox or (f.bbox.width == 0 and f.bbox.height == 0):
            continue
        x, y, w, h = f.bbox.x, f.bbox.y, f.bbox.width, f.bbox.height
        draw.rectangle([x, y, x + w, y + h], outline=BADGE_COLOR, width=2)
        if f.value:
            draw.text((x + 2, y + h + 2), str(f.value), fill=FILLED_COLOR, font=font)
        else:
            draw.ellipse([x - 10, y - 10, x + 10, y + 10], outline=BADGE_COLOR, width=2)
            draw.text((x - 4, y - 8), str(f.id), fill=BADGE_COLOR, font=font)

    return img


def render_answer_sheet(fields: List[FormField], title: str, width: int = 900) -> Image.Image:
    """Renders a clean, printable 'filled answers' panel — used as the right-hand
    side of the live preview, and as the base for the downloadable filled image."""
    padding = 40
    row_height = 70
    height = padding * 2 + 90 + row_height * max(len(fields), 1)

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    title_font = _load_font(28)
    label_font = _load_font(18)
    value_font = _load_font(20)
    urdu_font = _load_font(20, urdu=True)

    draw.text((padding, padding), title, fill=(10, 10, 10), font=title_font)
    draw.line(
        [(padding, padding + 45), (width - padding, padding + 45)],
        fill=(220, 220, 220), width=2,
    )

    y = padding + 65
    for f in fields:
        status_color = FILLED_COLOR if (f.is_valid and f.value) else (
            BADGE_COLOR if f.error_message else (160, 160, 160)
        )
        draw.ellipse([padding, y + 6, padding + 14, y + 20], fill=status_color)

        draw.text((padding + 26, y), f"{f.id}. {f.label}", fill=TEXT_COLOR, font=label_font)

        value_display = f.value if f.value else "—"
        draw.text((padding + 26, y + 26), str(value_display), fill=(40, 40, 40), font=value_font)

        if f.error_message:
            shaped = _shape_urdu(f.error_message)
            draw.text((padding + 26, y + 48), shaped, fill=BADGE_COLOR, font=urdu_font)

        y += row_height

    return img


def side_by_side(original: Image.Image, filled_sheet: Image.Image) -> Image.Image:
    """Combine original (left) and filled answer sheet (right) into one preview image."""
    h = max(original.height, filled_sheet.height)

    def _fit(img: Image.Image, target_h: int) -> Image.Image:
        scale = target_h / img.height
        return img.resize((int(img.width * scale), target_h), Image.LANCZOS)

    left = _fit(original, h)
    right = _fit(filled_sheet, h)

    combined = Image.new("RGB", (left.width + right.width + 20, h), (255, 255, 255))
    combined.paste(left, (0, 0))
    combined.paste(right, (left.width + 20, 0))
    return combined
