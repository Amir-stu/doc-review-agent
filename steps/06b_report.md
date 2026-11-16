---
name: doc-review-06b-report
description: Box 6b "Prüfliste ausgeben". Writes the findings list as Excel and Markdown.
executor: python
tools: Bash
---
# 06b Report – Prüfliste ausgeben

**Run.** `docreview run-step report <run-ordner>`

**Input.** `04_findings.json` (or the last re-check after corrections), `04_meta.json`, the decision and
applied files if present.

**Output.** `Pruefliste.xlsx` (filterable table) and `Pruefliste.md`, columns:
Nr. · Fundstelle · Kategorie · Schwere · Sicherheit · Befund · Original · Vorschlag · Status.

Status values: `offen`, `korrigiert`, `abgelehnt`, `manuell` (no automatic fix possible or the fix
failed), `nicht behoben`, `neu`.

The Markdown file starts with a summary: findings per category and severity, units the language agent
could not check, and – for Excel corrections – the openpyxl warning.
