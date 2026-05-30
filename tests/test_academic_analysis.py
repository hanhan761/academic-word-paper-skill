import json
import shutil
import unittest
from pathlib import Path

from tests.test_wordpaper_mvp import DOC_RELS, write_docx


ACADEMIC_DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>A WordPaper Study</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Abstract</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>This study evaluates a semantic layer for academic Word manuscripts.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>Keywords: WordPaper; docx; writing</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Introduction</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>Figure 1 shows the system pipeline for manuscript editing.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:drawing><a:blip r:embed="rIdImage1"/></w:drawing></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Caption"/></w:pPr><w:r><w:t>Figure 1. WordPaper pipeline.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Methods</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>We parse OOXML and build a deterministic intermediate representation.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Caption"/></w:pPr><w:r><w:t>Table 1. Parser accuracy.</w:t></w:r></w:p>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>Metric</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc></w:tr>
      <w:tr><w:tc><w:p><w:r><w:t>F1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>0.95</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Results</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>The prototype preserves structure during local edits.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Discussion</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>The approach separates writing semantics from Word storage details.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>References</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>[1] Smith J. Document engineering. 2024.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>[2] Zhang A. Academic writing systems. 2025.</w:t></w:r></w:p>
  </w:body>
</w:document>
"""


class AcademicAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path.cwd() / ".tmp-tests" / self._testMethodName
        if self.tmp.exists():
            shutil.rmtree(self.tmp)
        self.tmp.mkdir(parents=True)
        self.docx = self.tmp / "academic.docx"
        valid_rels = DOC_RELS.replace(
            '  <Relationship Id="rIdMissing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/missing.png"/>\n',
            "",
        )
        write_docx(self.docx, document_xml=ACADEMIC_DOCUMENT_XML, document_rels=valid_rels)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_analyze_writing_extracts_paper_semantics_and_checks_citations(self):
        from wordpaper.academic import analyze_writing

        report = analyze_writing(self.docx)

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["title"], "A WordPaper Study")
        self.assertEqual(report["abstract"]["text"], "This study evaluates a semantic layer for academic Word manuscripts.")
        self.assertEqual(report["keywords"], ["WordPaper", "docx", "writing"])
        self.assertEqual(
            [section["type"] for section in report["sections"]],
            ["title", "abstract", "introduction", "methods", "results", "discussion", "references"],
        )
        self.assertEqual(len(report["references"]["items"]), 2)
        self.assertTrue(report["citation_checks"]["figures"][0]["cited"])
        self.assertFalse(report["citation_checks"]["tables"][0]["cited"])
        self.assertIn("table_not_cited", {check["type"] for check in report["checks"]})

    def test_cli_exports_academic_reports(self):
        from wordpaper.cli import main

        analysis_path = self.tmp / "analysis.json"
        abstract_path = self.tmp / "abstract.json"
        refs_path = self.tmp / "references.json"
        journal_path = self.tmp / "journal.json"

        self.assertEqual(main(["analyze-writing", str(self.docx), "--out", str(analysis_path)]), 0)
        self.assertEqual(main(["extract-abstract", str(self.docx), "--out", str(abstract_path)]), 0)
        self.assertEqual(main(["list-references", str(self.docx), "--out", str(refs_path)]), 0)
        self.assertEqual(main(["check-journal", str(self.docx), "--rules", "basic", "--out", str(journal_path)]), 0)

        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        abstract = json.loads(abstract_path.read_text(encoding="utf-8"))
        references = json.loads(refs_path.read_text(encoding="utf-8"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))

        self.assertEqual(analysis["title"], "A WordPaper Study")
        self.assertEqual(abstract["word_count"], 10)
        self.assertEqual(len(references["items"]), 2)
        self.assertIn("abstract_too_short", {check["type"] for check in journal["checks"]})

    def test_review_revision_plan_and_patch_skeleton_are_actionable(self):
        from wordpaper.academic import make_section_patch, plan_revision, review_manuscript

        review = review_manuscript(self.docx)
        plan = plan_revision(self.docx)
        patch = make_section_patch(
            self.docx,
            section="abstract",
            instruction="Rewrite the abstract to 150-200 words with a clear objective, method, result, and conclusion.",
        )

        self.assertEqual(review["status"], "warning")
        self.assertEqual(review["summary"]["title"], "A WordPaper Study")
        self.assertGreaterEqual(review["summary"]["word_count"], 40)
        self.assertIn("structure", review["categories"])
        self.assertIn("tables", review["categories"])
        self.assertEqual(review["issues"][0]["severity"], "major")
        self.assertIn("priority", review["issues"][0])

        actions = [item["action"] for item in plan["actions"]]
        self.assertIn("rewrite_abstract", actions)
        self.assertIn("cite_table", actions)
        self.assertTrue(all("rationale" in item for item in plan["actions"]))

        self.assertEqual(patch["version"], 1)
        self.assertEqual(patch["actions"][0]["action"], "replace_block_text")
        self.assertEqual(patch["actions"][0]["target"]["block_id"], "p_001")
        self.assertIn("TODO", patch["actions"][0]["value"])
        self.assertEqual(patch["metadata"]["instruction"], "Rewrite the abstract to 150-200 words with a clear objective, method, result, and conclusion.")

    def test_cli_exports_review_plan_and_patch_skeleton(self):
        from wordpaper.cli import main

        review_path = self.tmp / "review.json"
        plan_path = self.tmp / "plan.json"
        patch_path = self.tmp / "abstract.patch.json"

        self.assertEqual(main(["review-manuscript", str(self.docx), "--out", str(review_path)]), 0)
        self.assertEqual(main(["plan-revision", str(self.docx), "--out", str(plan_path)]), 0)
        self.assertEqual(
            main(
                [
                    "make-section-patch",
                    str(self.docx),
                    "--section",
                    "abstract",
                    "--instruction",
                    "Make the abstract journal-ready.",
                    "--out",
                    str(patch_path),
                ]
            ),
            0,
        )

        review = json.loads(review_path.read_text(encoding="utf-8"))
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        patch = json.loads(patch_path.read_text(encoding="utf-8"))

        self.assertEqual(review["summary"]["title"], "A WordPaper Study")
        self.assertTrue(plan["actions"])
        self.assertEqual(patch["actions"][0]["target"]["block_id"], "p_001")


if __name__ == "__main__":
    unittest.main()
