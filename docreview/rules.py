"""Format rules (the "Formatvorgaben"): loaded from YAML, validated, frozen."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml

DATE_FORMATS = ("DD.MM.YYYY", "YYYY-MM-DD")
CURRENCY_POSITIONS = ("before", "after")
PERCENT_STYLES = ("10 %", "10%")

RULES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fonts": {
            "type": "object",
            "properties": {
                "allowed": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "replacement": {"type": "string"},
            },
            "required": ["allowed"],
        },
        "font_size_pt": {
            "type": "object",
            "properties": {"min": {"type": "number"}, "max": {"type": "number"}},
            "required": ["min", "max"],
        },
        "colors_allowed": {"type": "array", "items": {"type": "string", "pattern": "^[0-9A-Fa-f]{6}$"}},
        "date_format": {"enum": list(DATE_FORMATS)},
        "currency": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}, "position": {"enum": list(CURRENCY_POSITIONS)}},
            "required": ["symbol", "position"],
        },
        "percent_style": {"enum": list(PERCENT_STYLES)},
        "terms": {"type": "object", "additionalProperties": {"type": "string"}},
    },
}


class RulesError(ValueError):
    """The rules file is missing, unreadable, or does not match the schema."""


@dataclass(frozen=True)
class FormatRules:
    allowed_fonts: tuple[str, ...] = ()
    replacement_font: str | None = None
    min_font_size_pt: float | None = None
    max_font_size_pt: float | None = None
    allowed_colors: tuple[str, ...] = ()
    date_format: str | None = None
    currency_symbol: str | None = None
    currency_position: str | None = None
    percent_style: str | None = None
    terms: dict[str, str] = field(default_factory=dict)


def parse_rules(raw: dict[str, Any]) -> FormatRules:
    try:
        jsonschema.validate(raw, RULES_SCHEMA)
    except jsonschema.ValidationError as error:
        raise RulesError(f"Formatvorgaben ungültig: {error.message}") from error
    fonts = raw.get("fonts", {})
    sizes = raw.get("font_size_pt", {})
    currency = raw.get("currency", {})
    return FormatRules(
        allowed_fonts=tuple(fonts.get("allowed", ())),
        replacement_font=fonts.get("replacement"),
        min_font_size_pt=sizes.get("min"),
        max_font_size_pt=sizes.get("max"),
        allowed_colors=tuple(color.upper() for color in raw.get("colors_allowed", ())),
        date_format=raw.get("date_format"),
        currency_symbol=currency.get("symbol"),
        currency_position=currency.get("position"),
        percent_style=raw.get("percent_style"),
        terms=dict(raw.get("terms", {})),
    )


def load_rules(path: Path) -> FormatRules:
    if not path.is_file():
        raise RulesError(f"Formatvorgaben nicht gefunden: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise RulesError(f"Formatvorgaben sind kein gültiges YAML: {error}") from error
    if not isinstance(raw, dict):
        raise RulesError("Formatvorgaben müssen ein YAML-Objekt sein")
    return parse_rules(raw)
