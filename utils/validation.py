"""
Validation engine. Deliberately rule-based (not another LLM call) so it's
instant and 100% predictable — the user needs to trust it more than they
trust the AI's fluent explanations.

Every validator returns (is_valid: bool, error_message_urdu: str | None).
"""

from __future__ import annotations
import re
from datetime import datetime


def _ok():
    return True, None


def validate_text(value: str) -> tuple[bool, str | None]:
    if not value or not value.strip():
        return False, "یہ خانہ خالی نہیں ہو سکتا۔"
    return _ok()


def validate_13_digits(value: str) -> tuple[bool, str | None]:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 13:
        return False, "شناختی کارڈ نمبر میں پورے 13 ہندسے ہونے چاہئیں۔"
    return _ok()


def validate_phone_pk(value: str) -> tuple[bool, str | None]:
    digits = re.sub(r"\D", "", value or "")
    # Pakistani mobile: 03XXXXXXXXX (11 digits) or +923XXXXXXXXX
    if digits.startswith("92"):
        digits = "0" + digits[2:]
    if not re.fullmatch(r"03\d{9}", digits):
        return False, "فون نمبر درست نہیں۔ مثال: 03123456789"
    return _ok()


def validate_date(value: str) -> tuple[bool, str | None]:
    value = (value or "").strip()
    formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.year < 1900 or dt > datetime.now():
                return False, "تاریخ درست نہیں لگتی۔ براہ کرم دوبارہ چیک کریں۔"
            return _ok()
        except ValueError:
            continue
    return False, "تاریخ درست فارمیٹ میں نہیں ہے۔ مثال: 15/03/1998"


def validate_email(value: str) -> tuple[bool, str | None]:
    value = (value or "").strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}", value):
        return False, "ای میل ایڈریس درست نہیں لگتا۔"
    return _ok()


def validate_number(value: str) -> tuple[bool, str | None]:
    value = (value or "").strip()
    if not re.fullmatch(r"-?\d+(\.\d+)?", value):
        return False, "براہ کرم صرف نمبر درج کریں۔"
    return _ok()


def validate_age(value: str) -> tuple[bool, str | None]:
    value = (value or "").strip()
    if not value.isdigit():
        return False, "عمر صرف ہندسوں میں لکھیں۔"
    age = int(value)
    if age < 0 or age > 130:
        return False, "درج کردہ عمر درست نہیں لگتی۔"
    return _ok()


def validate_postal_code(value: str) -> tuple[bool, str | None]:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) not in (5, 6):
        return False, "پوسٹل کوڈ درست نہیں لگتا۔"
    return _ok()


def validate_yes_no(value: str) -> tuple[bool, str | None]:
    v = (value or "").strip().lower()
    if v not in {"yes", "no", "ہاں", "نہیں", "y", "n"}:
        return False, "براہ کرم 'ہاں' یا 'نہیں' میں جواب دیں۔"
    return _ok()


def validate_signature(value: str) -> tuple[bool, str | None]:
    # Presence check only — actual signature capture happens as an image stroke,
    # this validator just confirms the user has acknowledged/provided it.
    if not value or not value.strip():
        return False, "دستخط درکار ہیں۔"
    return _ok()


VALIDATORS = {
    "text": validate_text,
    "13_digits": validate_13_digits,
    "phone_pk": validate_phone_pk,
    "date": validate_date,
    "email": validate_email,
    "number": validate_number,
    "age": validate_age,
    "postal_code": validate_postal_code,
    "yes_no": validate_yes_no,
    "signature": validate_signature,
}


def validate_field(validation_type: str, value: str, required: bool = True) -> tuple[bool, str | None]:
    """Main entry point used by the conversation engine in app.py."""
    if not required and not (value or "").strip():
        return True, None  # optional and empty is fine

    validator = VALIDATORS.get(validation_type, validate_text)
    return validator(value)


def find_missing_required(fields: list) -> list[str]:
    """fields: list of FormField-like objects with .required, .value, .label"""
    missing = []
    for f in fields:
        required = getattr(f, "required", True)
        value = getattr(f, "value", None)
        if required and not (value and str(value).strip()):
            missing.append(getattr(f, "label", "Unknown field"))
    return missing
