# doc-review-agent

Proofreads PowerPoint, Word and Excel files against your format rules. Every box of the process
diagram is one step with its own instruction file in [`steps/`](steps/). The orchestrator runs them in
order and passes each step's output to the next through a run folder.

```
01 intake → 02 split → 03a language (subagent per slide/section/sheet) ┐
                     → 03b format rules (Python)                       ┴→ 04 collect (+04b term subagent)
→ 05 Deine Prüfung ─┬─ Korrektur freigegeben → 06a correct copy + re-check (back to 05, max 2 rounds)
                    └─ Nur Bericht           → 06b Prüfliste (.xlsx + .md)
```

Spelling and wording go to LLM subagents. Fonts, sizes, colours, dates, currencies, number formats
and Excel error values are read from the file and checked by code, because an LLM would only be
guessing them from extracted text.

## Use

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
```

```bash
.venv/Scripts/docreview check deck.pptx --rules format_rules.example.yaml
```

```bash
.venv/Scripts/docreview check bericht.docx --report-only
```

Flags: `--no-llm` (rule checks only), `--decision entscheidung.json` (non-interactive gate),
`--parallel N`. Single steps: `docreview run-step <intake|split|check-rules|check-language|collect|analyse|review|correct|report> <run-folder>`.

Subagents run as headless `claude -p` on your Claude Code login (no API key), from a sandbox folder
outside your home directory. Each step file's frontmatter is valid Claude Code subagent frontmatter,
so a step can also be started as a subagent on its own.

## Verified (2026-11-16, live subagents on the seeded files in `tests/fixture_files.py`)

| File | Seeded errors | Found | False positives | Cost | Time |
|---|---|---|---|---|---|
| Quartalsbericht.pptx | 9 | 9 | 0 | $0.05 | 14 s analysis + 11 s correct/re-check |
| Projektbericht.docx | 8 | 8 | 0 | $0.02 | – |
| Umsatz.xlsx | 5 | 5 | 1 duplicate (now deduped) | $0.02 | – |

The PowerPoint run also applied 7 approved fixes to the copy. The live re-check found nothing new, and
the original's SHA-256 was unchanged. These are small, synthetic files. Recall on real client
documents has **not** been measured.

## Limits

- Inherited formatting (theme, master slide, style) is not judged; only explicit run formatting.
- PowerPoint overflow is an estimate (no layout engine) and is marked `wahrscheinlich`.
- A text fix spanning differently formatted runs is not applied; it goes to the report as `manuell`.
- Excel: openpyxl drops charts and images when it saves the copy, and error values only exist if
  Excel saved the file.
- Not read: headers/footers, speaker notes, comments, charts, legacy `.ppt/.doc/.xls`.

Tests: `.venv/Scripts/pytest` (115 tests, 97 % coverage, `claude -p` mocked at the subprocess boundary).
