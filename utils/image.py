"""
Image preprocessing before it's sent to Gemma, plus helpers to prep the
image for the overlay engine later.
"""

from __future__ import annotations
import io
from PIL import Image, ImageOps
import numpy as np
import cv2

MAX_DIMENSION = 1600  # keep uploads reasonably sized for a local CPU/GPU vision call


def load_image(file_bytes: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(file_bytes))
    img = ImageOps.exif_transpose(img)  # respect phone camera orientation
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def resize_if_needed(img: Image.Image, max_dim: int = MAX_DIMENSION) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_dim:
        return img
    scale = max_dim / longest
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def deskew_and_denoise(img: Image.Image) -> Image.Image:
    """Light cleanup pass: grayscale-based deskew + denoise, then recompose as RGB.
    Improves OCR/vision reliability on phone photos of paper forms."""
    cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # Denoise
    gray = cv2.fastNlMeansDenoising(gray, h=10)

    # Estimate skew via minAreaRect on thresholded text mask
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    angle = 0.0
    if len(coords) > 0:
        rect_angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + rect_angle) if rect_angle < -45 else -rect_angle
        # Ignore wild angle estimates (likely noise, not real skew)
        if abs(angle) > 15:
            angle = 0.0

    if abs(angle) > 0.3:
        (h, w) = cv_img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        cv_img = cv2.warpAffine(
            cv_img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )

    return Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))


def prepare_for_analysis(file_bytes: bytes, clean: bool = True) -> tuple[Image.Image, bytes]:
    """Full pipeline: load -> resize -> (optional) deskew/denoise -> re-encode to JPEG bytes."""
    img = load_image(file_bytes)
    img = resize_if_needed(img)
    if clean:
        try:
            img = deskew_and_denoise(img)
        except Exception:
            pass  # cleanup is a nice-to-have; never block the pipeline on it

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return img, buf.getvalue()


def blur_score(img: Image.Image) -> float:
    """Laplacian-variance blur metric. Lower = blurrier. Used to warn the user
    before they even hit Gemma, e.g. 'this photo looks blurry, retake?'"""
    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())
