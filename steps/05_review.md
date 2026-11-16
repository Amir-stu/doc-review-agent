---
name: doc-review-05-review
description: Box 5 "Deine Prüfung". Human gate - shows the findings and records which corrections are approved or that only a report is wanted.
executor: human
tools: Bash
---
# 05 Review – Deine Prüfung

**Purpose.** Nothing changes in any file without a person deciding. This step cannot be done by an agent.

**Run.** `docreview run-step review <run-ordner>` (interactive) or
`docreview run-step review <run-ordner> --decision <entscheidung.json>` (non-interactive).

**Shown.** All findings from `04_findings.json`: number, locator, description, original → suggestion,
and whether a fix can be applied automatically.

**Decision.**
1. `b` – **Nur Bericht gewünscht** → step 06b.
2. `k` – **Korrektur freigegeben** → then each automatically fixable finding is asked one by one:
   `j` accept · `n` reject · `a` accept all remaining · `q` reject all remaining.

**Output.** `05_decision.json`: `{mode: "correct" | "report", accepted: ["F001", …]}`.
A decision file passed with `--decision` must have the same shape; unknown finding IDs are rejected.
