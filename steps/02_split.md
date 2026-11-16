---
name: doc-review-02-split
description: Box 2 "In Folien, Abschnitte oder Tabellenblätter aufteilen". Reads the file into review units with locators and formatting.
executor: python
tools: Bash
---
# 02 Split – In Folien, Abschnitte oder Tabellenblätter aufteilen

**Purpose.** Turn the file into units a reviewer can work through one at a time.

**Run.** `docreview run-step split <run-ordner>`

**Input.** `01_intake.json`.

**Output.** `02_units.json`: `{file_type, source_path, units: [...]}`.

| File | Unit | Contents per unit |
|---|---|---|
| PowerPoint | one per slide | text boxes and table cells (size, auto-fit, wrap), paragraphs, runs |
| Word | one per `Heading 1` section (text before the first heading = "Dokumentanfang") | paragraphs and table cells in document order, style, alignment, spacing, runs |
| Excel | one per sheet | every non-empty cell: cached value, data type, number format, formula flag |

Every paragraph and cell gets a stable ID (used by the writer in step 06a) and a human locator,
e.g. `Folie 4, Form "Titel 1", Absatz 1`, `Abschnitt "Einleitung", Absatz 3`, `Blatt "Umsatz", Zelle C14`.

**Rules.** Only explicit run formatting is recorded; inherited values (theme, master, style) are `null`
and are not judged. Headers, footers, speaker notes and charts are not read.
