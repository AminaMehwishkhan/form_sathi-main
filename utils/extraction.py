"""
Bridges the raw dict Gemma returns and our strict Pydantic schema.
Handles the messy reality of LLM output: missing keys, wrong types,
extra keys, etc.
"""

from __future__ import annotations
from typing import Any
from pydantic import ValidationError

from schemas.field_schema import FormAnalysis, FormField


def _coerce_field(raw: dict, fallback_id: int) -> dict:
    """Fill in sane defaults for anything Gemma omitted on a single field."""
    raw = dict(raw)  # don't mutate caller's dict
    raw.setdefault("id", fallback_id)
    raw.setdefault("label", f"Field {fallback_id}")
    raw.setdefault("question_urdu", raw.get("label", f"Field {fallback_id}") + "؟")
    raw.setdefault("question_english", raw.get("label"))
    raw.setdefault("type", "text")
    raw.setdefault("required", True)
    raw.setdefault("validation", "text")

    # Some models return validation types outside our enum (e.g. "digits13").
    # Normalize the common near-misses rather than hard-failing.
    validation_aliases = {
        "digits13": "13_digits",
        "cnic": "13_digits",
        "13digits": "13_digits",
        "phone": "phone_pk",
        "mobile": "phone_pk",
        "dob": "date",
    }
    v = str(raw.get("validation", "text")).lower().strip()
    raw["validation"] = validation_aliases.get(v, v if v else "text")

    valid_validations = {
        "text", "13_digits", "phone_pk", "date", "email",
        "number", "age", "postal_code", "yes_no", "signature",
    }
    if raw["validation"] not in valid_validations:
        raw["validation"] = "text"

    valid_types = {"text", "cnic", "phone", "date", "email", "number", "select", "signature"}
    if str(raw.get("type", "text")).lower() not in valid_types:
        raw["type"] = "text"
    else:
        raw["type"] = str(raw["type"]).lower()

    return raw


def parse_gemma_response(raw: dict) -> FormAnalysis:
    """
    Turn Gemma's raw dict into a validated FormAnalysis, patching common
    small mistakes instead of throwing on the first missing field.

    Raises pydantic.ValidationError only if the response is unusable even
    after coercion (e.g. no fields at all, or not a dict).
    """
    if not isinstance(raw, dict):
        raise ValidationError.from_exception_data("FormAnalysis", [])

    raw = dict(raw)
    raw.setdefault("title", "Untitled Form")
    raw.setdefault("language", "English")
    raw.setdefault("explanation_english", "This form could not be summarized automatically.")
    raw.setdefault("explanation_urdu", "اس فارم کا خلاصہ خودکار طور پر فراہم نہیں ہو سکا۔")
    raw.setdefault("estimated_time", "a few minutes")
    raw.setdefault("required_documents", [])
    raw.setdefault("warnings", [])
    raw.setdefault("confidence", 0.7)

    fields_raw = raw.get("fields") or []
    coerced_fields = [_coerce_field(f, i + 1) for i, f in enumerate(fields_raw)]
    raw["fields"] = coerced_fields

    if not coerced_fields:
        raw["warnings"] = list(raw["warnings"]) + [
            "No fillable fields were detected. Try retaking the photo with better lighting."
        ]

    return FormAnalysis.model_validate(raw)
