---
name: doc-review-06a-correct
description: Box 6a "Kopie korrigieren und erneut prüfen". Applies the approved fixes to a copy, then re-runs steps 02-04 on the copy.
executor: python
tools: Bash
---
# 06a Correct – Kopie korrigieren und erneut prüfen

**Run.** `docreview run-step correct <run-ordner>`

**Input.** Source file, `04_findings.json`, `05_decision.json` with `mode = correct`.

**Output.**
- `<name>_korrigiert.<ext>` in the run folder – the original is never written to.
- `06a_applied_<runde>.json`: per accepted finding `applied` or `failed` with the reason.
- `06a_recheck_<runde>.json`: steps 02–04 run again on the copy. Each finding is labelled
  `nicht behoben` (an accepted fix did not take effect) or `neu` (introduced or newly visible).

**What can be applied.**

| Fix | PowerPoint | Word | Excel |
|---|---|---|---|
| Text ersetzen | yes, inside one run | yes, inside one run | text cells only, never formulas |
| Schriftart / -größe | yes | yes | – |
| Zahlenformat | – | – | yes |

A replacement whose text spans several runs (differently formatted parts) is **not** applied – it is
marked `failed: über mehrere Formatierungen verteilt` and goes to the report for manual correction.

**Loop.** If the re-check finds open findings, the orchestrator goes back to step 05 with them.
After 2 rounds it stops and hands the remaining list to the person.

**Excel warning.** `openpyxl` drops charts, images and cached formula results when it saves. Open
the copy in Excel and save it once before sending.
