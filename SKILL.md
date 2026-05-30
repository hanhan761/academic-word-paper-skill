---
name: word
description: "Academic Word Paper workflow and tooling for `.docx` manuscripts. Use when Codex needs to inspect, edit, validate, restructure, analyze, or convert a Word academic paper; extract or check abstracts, keywords, sections, references, headings, paragraphs, tables, figures, captions, footnotes, comments, or citations; generate a WordPaper IR JSON file; create or apply declarative patch plans; preserve original Word formatting while making local edits; or validate that a revised `.docx` package remains structurally sound."
---

# Academic Word Paper

Use this skill to handle academic manuscripts stored as `.docx`. Treat Word as an OOXML package with a paper-oriented semantic layer, not as plain text.

## Core Rule

Do not directly rewrite a Word document from scratch unless the user explicitly asks for a regenerated document. Prefer this pipeline:

1. Inspect the `.docx`.
2. Run writing analysis for paper-facing tasks.
3. Generate a manuscript review and revision plan for broad writing requests.
4. Export WordPaper IR when block-level patching is needed.
5. Read the IR and identify stable block IDs.
6. Create a declarative compile plan, patch plan, or section patch skeleton.
7. Prefer `compile` for semantic manuscript edits; use `apply` for low-level block edits.
8. Validate the revised `.docx`.
9. Return the revised document path, diff or change summary, and validation status.

## Commands

Run these from this skill folder, or run them with this folder on `PYTHONPATH`.

```bash
python -m wordpaper inspect paper.docx
python -m wordpaper export-ir paper.docx --out paper.ir.json
python -m wordpaper list-sections paper.docx
python -m wordpaper list-figures paper.docx
python -m wordpaper list-tables paper.docx
python -m wordpaper extract-comments paper.docx
python -m wordpaper analyze-writing paper.docx --out writing-report.json
python -m wordpaper extract-abstract paper.docx --out abstract.json
python -m wordpaper list-references paper.docx --out references.json
python -m wordpaper check-journal paper.docx --rules basic --out journal-check.json
python -m wordpaper review-manuscript paper.docx --out manuscript-review.json
python -m wordpaper plan-revision paper.docx --out revision-plan.json
python -m wordpaper make-section-patch paper.docx --section abstract --instruction "Rewrite to 150-200 words with objective, method, result, and conclusion." --out abstract.patch.json
python -m wordpaper compile paper.docx compile-plan.json --out paper_revised.docx --report compile-report.json
python -m wordpaper quality-gate paper.docx --gold gold.json --compile-plan compile-plan.json --compiled-out paper_revised.docx --require-100 --out quality-report.json
python -m wordpaper apply paper.docx patch.json --out paper_revised.docx
python -m wordpaper validate paper_revised.docx
python -m wordpaper diff paper.docx paper_revised.docx --out diff.json
python -m wordpaper export-md paper.docx --out paper.md
```

The MVP accepts JSON patches and simple YAML patches. Prefer JSON if exact parsing matters.

## Writing Analysis

Use `analyze-writing` before editing when the request is about academic writing quality, manuscript structure, or submission readiness.

The report includes:

- `title`: first detected paper title heading.
- `abstract`: abstract text, word count, and source block IDs.
- `keywords`: parsed keyword line.
- `sections`: classified headings such as abstract, introduction, methods, results, discussion, conclusion, references, acknowledgements, funding, and competing interests.
- `references`: reference-section items.
- `citation_checks`: whether detected figures and tables are cited in body text.
- `checks`: warnings for missing core sections, missing keywords/references, and uncited figures/tables.

Use `check-journal --rules basic` for deterministic basic checks such as abstract length and keyword count. Use these outputs to guide the agent's writing decisions, then generate a patch if the Word document needs local edits.

For broad requests such as "make this paper better", "check whether this manuscript is ready", or "revise this Word paper", use:

1. `review-manuscript` to produce prioritized issues grouped by structure, abstract, figures, tables, references, and writing.
2. `plan-revision` to turn issues into concrete actions such as `rewrite_abstract`, `cite_table`, `cite_figure`, or `add_section`.
3. `make-section-patch` to create a patch skeleton for a specific section. Replace the `TODO` value with the agent-written revised text before applying it.
4. `compile` for semantic edits that target sections, keywords, missing sections, and figure/table citations.
5. `apply`, `validate`, and `diff` only when you need low-level block control.

Do not apply a patch skeleton while it still contains `TODO`; it is a scaffold for the agent's revised prose.

## Compile Plans

Prefer compile plans when the user asks for flexible manuscript editing rather than a single block replacement. A compile plan is JSON with `version` and `actions`.

```json
{
  "version": 1,
  "actions": [
    {
      "action": "replace_section_text",
      "target": {"section": "abstract"},
      "value": [
        "Objective and method paragraph...",
        "Key result and conclusion paragraph..."
      ]
    },
    {
      "action": "set_keywords",
      "value": ["WordPaper", "docx", "semantic compiler"]
    },
    {
      "action": "cite_table",
      "target": {"table_index": 1, "section": "results"},
      "sentence": "Table 1 summarizes the parser accuracy for the prototype."
    },
    {
      "action": "insert_section_after",
      "target": {"section": "discussion"},
      "heading": "Conclusion",
      "level": 2,
      "paragraphs": ["This study establishes a safer foundation for AI-assisted manuscript editing."]
    }
  ]
}
```

Supported semantic compile actions:

- `replace_section_text`: replace editable paragraphs in a named section.
- `set_keywords`: update or insert the keyword line.
- `cite_table` / `cite_figure`: insert an interpretive citation sentence into a target section.
- `insert_section_after`: add a heading and paragraphs after a named section.

`compile` returns a report containing patch status, validation status, and semantic diff. Treat `validation.status: error` as a failed compile.

## 100% Quality Gate

Do not claim the skill reaches 100% in general. Claim 100% only for a declared gold corpus and supported feature set.

Use `quality-gate` whenever the user asks for hard acceptance or "all metrics at 100%". It scores six categories:

- `word_safety`
- `structure_analysis`
- `writing_assist`
- `submission_prep`
- `citation_system`
- `end_to_end`

The command requires:

- source `.docx`
- `gold.json` with expected title, abstract text marker, keywords, sections, object counts, and required review/revision outputs
- compile plan that should revise the document successfully
- output path for the compiled `.docx`

With `--require-100`, the command fails unless every category is exactly 100. Treat this as the acceptance gate for supported-scope releases.

## Patch DSL

Use block IDs from `export-ir`; do not guess IDs. Keep patches small and local.

```json
{
  "version": 1,
  "actions": [
    {
      "action": "replace_block_text",
      "target": {"block_id": "p_003"},
      "value": "This study proposes a conservative WordPaper IR for academic manuscripts."
    },
    {
      "action": "insert_after",
      "target": {"block_id": "p_003"},
      "block": {
        "type": "paragraph",
        "text": "Additional robustness checks are reported in Appendix B.",
        "style": "Normal"
      }
    },
    {
      "action": "update_caption",
      "target": {"figure_index": 1},
      "caption": "Figure 1. Overview of the WordPaper pipeline."
    }
  ]
}
```

Supported MVP actions:

- `replace_block_text`
- `insert_after`
- `apply_style`
- `change_heading_level` or `set_heading_level`
- `update_caption`
- `delete_paragraph`

## IR Model

`export-ir` returns JSON with these top-level fields:

- `blocks`: ordered headings, paragraphs, and tables with stable IDs and OOXML locations.
- `sections`: heading-derived paper sections.
- `figures`: image anchors plus nearby figure captions.
- `tables`: table rows plus nearby table captions.
- `footnotes`, `endnotes`, `comments`: extracted review and note text.
- `relationships`, `media`: OOXML package references and embedded media paths.

IDs are generated from document order. After applying a patch, export IR again before making a second patch.

## Validation

Always validate after writing a revised `.docx`.

The MVP validator checks:

- docx zip readability.
- presence of `[Content_Types].xml` and `word/document.xml`.
- XML well-formedness for XML and relationship parts.
- missing relationship targets.
- heading level skips and empty headings.
- duplicate figure/table numbers.
- missing nearby captions for figures and tables.

Treat `status: error` as a failed edit unless the error was already present in the input and is explicitly reported to the user. Treat `status: warning` as usable but mention the warning.

## Safety Rules

- Preserve the source `.docx`; always write a new output file.
- Do not flatten tables into text unless exporting Markdown.
- Do not delete relationship files, styles, numbering, media, footnotes, comments, or settings.
- Do not edit OOXML manually when a patch action can express the change.
- Avoid editing paragraphs that contain complex tracked changes unless the user accepts the risk.
- Use small patches; validate after each meaningful batch.

## MVP Boundary

This first version is for ordinary academic paper editing tasks. It supports headings, paragraphs, run text flags, tables, simple figure/table caption heuristics, footnotes, comments, local paragraph edits, style changes, and structural validation.

It does not yet promise full Zotero or Mendeley field-code rewriting, automatic TOC refresh, complex tracked-change workflows, multi-column layout control, SmartArt, embedded Excel, or OMML equation round-tripping.
