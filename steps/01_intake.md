---
name: doc-review-01-intake
description: Box 1 "Datei und Formatvorgaben übergeben". Validates the input file and the format rules, creates the run folder.
executor: python
tools: Bash
---
# 01 Intake – Datei und Formatvorgaben übergeben

**Purpose.** Accept one PowerPoint, Word or Excel file plus a format rules file and open a run folder
that every later step reads from and writes to.

**Run.**
```
docreview run-step intake <datei> --rules <formatvorgaben.yaml>
```
Prints the run folder path.

**Input.** A `.pptx`, `.docx` or `.xlsx` file. A YAML rules file matching `format_rules.example.yaml`.

**Output.** `runs/<zeitstempel>_<dateiname>/01_intake.json`:
`{source_path, file_type, sha256, rules_path, rules}`. The source file is never modified.

**Rules.**
- Reject any other file type, a missing file, or rules that fail schema validation – stop with a clear error.
- Legacy formats (`.ppt`, `.doc`, `.xls`) are rejected; convert them to the XML format first.

**On failure.** Exit non-zero, write nothing.
