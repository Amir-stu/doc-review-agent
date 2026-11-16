# Spec: doc-review-agent (Korrekturlese-Agent)

Status: approved 2026-11-16 and built (v0.1). Open questions were not answered; defaults used:
German + English, per-finding approval, example rules file, lean build. Question 4 (real use case) is still open.
Deviation from the plan: step 04 got a second instruction file (04a collect, 04b term-consistency
subagent), so there are 9 step files for the 6 diagram boxes.

## Objective

Proofread a PowerPoint, Word, or Excel file against a set of format rules.
Produce a findings list with location and suggested fix. After a human reviews
it, either write a corrected **copy** and re-check it, or output the findings
list only.

User: one person (Amir) checking client-facing documents before sending them.
Success: on a seeded test file with N known errors, the agent finds ≥ 90 % of
them, invents no fixes that change meaning, and never touches the original file.

### Checks (from the requirements table)

| Area | Examples | Detected by |
|---|---|---|
| Rechtschreibung | typos, grammar, punctuation | LLM |
| Formulierungen | unclear sentences, repetition, inconsistent terms | LLM |
| Formatierung | fonts, font sizes, colours, spacing, alignment | Rules (Python, against the format spec) |
| Konsistenz | date formats, currencies, units, headings | Rules first (regex), LLM for terms |
| File-specific | PPT: overflowing text · Word: inconsistent headings · Excel: inconsistent number formats, visible error values (`#DIV/0!`, `#REF!`, …) | Rules |

Design choice: anything that can be read from the file's XML is checked by
code, not by an LLM. LLMs are used only where language judgement is needed.
An LLM guessing a font size from extracted text is wrong by construction.

## Pipeline: one instruction file per diagram box

```
01 intake ─▶ 02 split ─▶ 03 check (fan-out) ─▶ 04 collect ─▶ 05 review gate ─┬─▶ 06a correct + recheck ─┐
                                                                             └─▶ 06b report             │
                                                       03 ◀── re-check on corrected copy (max 2 rounds) ┘
```

| # | Box | Instruction file | Executor | Input → Output |
|---|---|---|---|---|
| 01 | Datei und Formatvorgaben übergeben | `steps/01_intake.md` | Python | file path + `format_rules.yaml` → `01_intake.json` (validated file type, hash, rules) |
| 02 | In Folien, Abschnitte oder Tabellenblätter aufteilen | `steps/02_split.md` | Python | `01_intake.json` → `02_units.json` (one unit per slide / section / sheet, with text runs + formatting attributes + stable locator) |
| 03 | Rechtschreibung, Formulierungen, Formatierung prüfen | `steps/03a_language_check.md`, `steps/03b_format_check.md` | 03a: subagent (`claude -p`, one per unit, parallel) · 03b: Python rules | `02_units.json` → `03_findings/<unit>.json` |
| 04 | Fehler mit Fundstelle und Korrekturvorschlag sammeln | `steps/04_collect.md` | Python (+ one subagent pass for cross-unit term consistency) | all `03_findings/*` → `04_findings.json` (deduped, ranked, IDs) |
| 05 | Deine Prüfung | `steps/05_review.md` | Human (CLI) | `04_findings.json` → `05_decision.json` (mode = correct/report, accepted finding IDs) |
| 06a | Kopie korrigieren und erneut prüfen | `steps/06a_correct.md` | Python writes copy → re-runs 02–04 on the copy | → `<name>_korrigiert.<ext>` + `06a_recheck.json` |
| 06b | Prüfliste ausgeben | `steps/06b_report.md` | Python | → `Prüfliste.xlsx` + `Prüfliste.md` |

Each instruction file has the same header: purpose, input file + JSON schema,
output file + JSON schema, rules, failure behaviour. For LLM steps the file
body **is** the subagent system prompt, and the output schema is passed to
`claude -p --json-schema`, so the agent cannot return free text.

Output passing: every step reads and writes JSON in `runs/<timestamp>_<filename>/`.
Any step can be re-run on its own from that folder (`docreview run-step 03 runs/...`).

## Tech Stack

- Python 3.13, `python-pptx`, `python-docx`, `openpyxl`, `pyyaml`, `jsonschema`
- Subagents: headless `claude -p` via the runner pattern from
  `deep-research-cli/deep_research/runner.py` (native claude.exe,
  `--strict-mcp-config --disable-slash-commands --setting-sources ""`,
  `--json-schema`, run from a folder outside the home directory). No API key.
- Models: 03a on sonnet, 04 consistency pass on sonnet. No opus needed.

## Commands

```
Install: python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
Run:     .venv/Scripts/docreview check deck.pptx --rules format_rules.yaml
Report:  .venv/Scripts/docreview check deck.pptx --rules format_rules.yaml --report-only
Step:    .venv/Scripts/docreview run-step 03 runs/<run-id>
Test:    .venv/Scripts/pytest --cov=docreview --cov-fail-under=80
Lint:    .venv/Scripts/ruff check . && .venv/Scripts/mypy docreview
```

## Project Structure

```
doc-review-agent/
  SPEC.md
  format_rules.example.yaml   fonts, sizes, colours, date/currency formats, term list
  steps/                      7 instruction files (the diagram boxes)
  docreview/
    cli.py                    argparse entry point
    orchestrator.py           runs steps in order, owns the run folder, the loop, the gate
    runner.py                 claude -p subprocess wrapper
    schemas/                  JSON schemas, one per step output
    readers/  pptx.py docx.py xlsx.py      step 02
    checks/   format.py consistency.py file_specific.py   step 03b
    writers/  pptx.py docx.py xlsx.py      step 06a
    report.py                 step 06b
  tests/fixtures/             seeded test files with a known error list
  runs/                       gitignored
```

## Code Style

```python
def split_presentation(path: Path) -> list[Unit]:
    presentation = Presentation(path)
    return [_slide_to_unit(index, slide) for index, slide in enumerate(presentation.slides, start=1)]
```

Pure functions, no mutation, dataclasses frozen, no magic numbers (thresholds in
`config.py`), files 200–800 lines.

## Testing Strategy

- pytest, TDD per task. Fixtures: one `.pptx`, `.docx`, `.xlsx` generated by a
  script with seeded errors and an `expected_findings.json`.
- Unit: readers, every rule check, dedupe, writers (round-trip: write fix → re-read → error gone, formatting of untouched runs unchanged).
- Integration: orchestrator with `claude -p` mocked at the subprocess boundary.
- One live E2E run on each fixture before calling it done; recall measured against the seeded list.
- 80 % coverage gate.

## Requirements (EARS)

- THE SYSTEM SHALL never write to the input file.
- WHEN a file other than .pptx/.docx/.xlsx is given THE SYSTEM SHALL stop at step 01 with a clear error.
- WHEN step 02 runs THE SYSTEM SHALL give every finding a locator a human can find (e.g. `Folie 4, Textfeld "Titel"`, `Abschnitt 2.1, Absatz 3`, `Blatt Umsatz!C14`).
- WHILE step 03a runs THE SYSTEM SHALL return only JSON that validates against the findings schema.
- IF a subagent output fails validation twice THEN THE SYSTEM SHALL record the unit as `unchecked` and continue.
- THE SYSTEM SHALL not proceed past step 05 without an explicit human decision.
- WHEN the human selects "Nur Bericht" THE SYSTEM SHALL write the report and stop.
- WHEN the human approves corrections THE SYSTEM SHALL apply only the accepted findings, to a copy.
- WHEN corrections are applied THE SYSTEM SHALL re-run steps 02–04 on the copy and report remaining and newly introduced findings.
- IF the re-check finds new errors after 2 rounds THEN THE SYSTEM SHALL stop and hand back to the human.
- THE SYSTEM SHALL preserve the formatting of text runs it does not change.

## Boundaries

- Always: work on a copy; keep every step's output in the run folder; validate JSON at every hand-off.
- Ask first: new dependencies beyond the list above; any LLM-based automatic fix of formatting.
- Never: modify the original; let the LLM decide font/size/colour findings; send document content anywhere except the local `claude -p`.

## Known risks

1. **PPT overflow detection is approximate.** python-pptx has no text layout engine. Plan: estimate from box size, font size, and character count; label these findings "wahrscheinlich" rather than certain.
2. **Text replacement across runs.** A typo can span two runs with different formatting. Fixes that cross runs are not applied automatically; they go to the report as "manuell".
3. **Excel formulas.** Error values come from cached values; a file never saved in Excel has none. Fixes in Excel limited to number formats and text cells, never formulas.
4. **Cost/time.** One subagent call per unit. A 40-slide deck ≈ 40 calls; parallelism capped at 4.

## Open Questions

1. Language: German only, or German + English documents?
2. Gate granularity: approve per finding (recommended) or all-or-nothing as in the diagram?
3. Format rules: do you have a real style guide (company template) to turn into `format_rules.yaml`, or do I write an example one?
4. Who is this for? A real workflow with real files (which?), or a portfolio piece?
