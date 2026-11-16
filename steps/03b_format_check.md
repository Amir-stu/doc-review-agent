---
name: doc-review-03b-format-check
description: Box 3 (format part) "Formatierung prüfen". Deterministic checks of formatting, consistency and file-specific errors against the format rules.
executor: python
tools: Bash
---
# 03b Format check – Formatierung, Konsistenz, dateispezifische Fehler

**Purpose.** Check everything that can be read exactly from the file. An LLM is not used here: it
would have to guess fonts and sizes from extracted text.

**Run.** `docreview run-step check-rules <run-ordner>`

**Input.** `02_units.json`, rules from `01_intake.json`. **Output.** `03_findings/rules.json`.

| Check | Rule | Fix offered |
|---|---|---|
| Schriftart | run font not in `fonts.allowed` | yes → `fonts.replacement` |
| Schriftgröße | outside `font_size_pt.min/max` | yes → clamped to the bound |
| Farbe | RGB colour not in `colors_allowed` | no |
| Ausrichtung, Abstände | differs from the majority of paragraphs with the same style | no |
| Datum | not in `date_format` (DD.MM.YYYY or YYYY-MM-DD; US dates marked probable) | yes |
| Währung | `EUR`, symbol position or spacing differs from `currency` | yes |
| Prozent | spacing differs from `percent_style` | yes |
| Begriffe | variant from `terms` used | yes → preferred term |
| PowerPoint | text probably cut off (estimate from box size, font size, characters; skipped for auto-fit boxes) | no |
| Word | heading ends with a period · bold "heading" without heading style · same-level headings formatted differently | period only |
| Excel | visible error value (`#DIV/0!`, `#REF!`, …) · number format differs from its column · number stored as text | number format only |

Findings marked `probable` are estimates (overflow, majority-based layout); `certain` ones follow
directly from a rule.
