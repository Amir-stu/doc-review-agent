---
name: doc-review-04a-collect
description: Box 4 "Fehler mit Fundstelle und Korrekturvorschlag sammeln". Merges, dedupes, ranks and numbers all findings.
executor: python
tools: Bash
---
# 04a Collect – Fehler mit Fundstelle und Korrekturvorschlag sammeln

**Run.** `docreview run-step collect <run-ordner>` (runs 04b first unless `--no-llm`).

**Input.** All files in `03_findings/` plus the 04b result.

**Output.** `04_findings.json`: list of findings, each with
`finding_id` (F001…), `locator`, `category`, `severity`, `confidence`, `description`, `original`,
`suggestion`, `source` (rules/llm) and `fix` (null = must be fixed by hand).
`04_meta.json`: units the language agent could not check, rejected agent findings, cost.

**Rules.**
- Duplicate = same target, same original, same suggestion (case-insensitive). Rule findings win over
  agent findings.
- Order: document order, then severity (high → low).
- A unit whose agent failed twice is listed as `unchecked` – never silently dropped.
