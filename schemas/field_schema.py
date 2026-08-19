"""
Pydantic schemas for FormSathi.

These define the exact JSON contract we force Gemma 4 Vision to return,
and the runtime objects the rest of the app (conversation engine,
validation engine, overlay engine) operate on.
"""

from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator


# Supported validation "types" -> mapped to concrete regex/logic in utils/validation.py
FieldValidationType = Literal[
    "text",
    "13_digits",       # CNIC
    "phone_pk",        # 03XXXXXXXXX
    "date",            # DD/MM/YYYY
    "email",
    "number",
    "age",
    "postal_code",
    "yes_no",
    "signature",       # presence check only
]

FieldInputType = Literal[
    "text", "cnic", "phone", "date", "email", "number", "select", "signature"
]


class BoundingBox(BaseModel):
    """Optional pixel coordinates of the field on the original image, used by the overlay engine."""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


class FormField(BaseModel):
    id: int
    label: str                          # English label as printed on the form
    question_urdu: str                  # Conversational question in Urdu
    question_english: Optional[str] = None
    type: FieldInputType = "text"
    required: bool = True
    validation: FieldValidationType = "text"
    bbox: Optional[BoundingBox] = None  # filled in later if we can localize the field
    help_text_urdu: Optional[str] = None  # answer to "what does this field mean?"
    help_text_english: Optional[str] = None

    # runtime state (not part of Gemma's output, filled in during conversation)
    value: Optional[str] = None
    is_valid: Optional[bool] = None
    error_message: Optional[str] = None


class FormAnalysis(BaseModel):
    """Top-level object returned by Gemma 4 Vision after analyzing an uploaded form image."""
    title: str
    language: str = "English"
    explanation_english: str
    explanation_urdu: str
    estimated_time: str = "2 minutes"
    required_documents: List[str] = Field(default_factory=list)
    fields: List[FormField]
    warnings: List[str] = Field(default_factory=list)
    confidence: float = 0.9  # 0-1, image quality / understanding confidence

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class ConversationState(BaseModel):
    """Tracks progress through the one-question-at-a-time flow."""
    current_field_index: int = 0
    completed: bool = False

    def current_field(self, fields: List[FormField]) -> Optional[FormField]:
        if 0 <= self.current_field_index < len(fields):
            return fields[self.current_field_index]
        return None

    def advance(self, total_fields: int) -> None:
        self.current_field_index += 1
        if self.current_field_index >= total_fields:
            self.completed = True
