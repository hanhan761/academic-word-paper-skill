import json
import shutil
import unittest
from pathlib import Path

from tests.test_academic_analysis import ACADEMIC_DOCUMENT_XML
from tests.test_wordpaper_mvp import DOC_RELS, write_docx


class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path.cwd() / ".tmp-tests" / self._testMethodName
        if self.tmp.exists():
            shutil.rmtree(self.tmp)
        self.tmp.mkdir(parents=True)
        self.docx = self.tmp / "paper.docx"
        valid_rels = DOC_RELS.replace(
            '  <Relationship Id="rIdMissing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/missing.png"/>\n',
            "",
        )
        write_docx(self.docx, document_xml=ACADEMIC_DOCUMENT_XML, document_rels=valid_rels)
        self.gold = self.tmp / "gold.json"
        self.plan = self.tmp / "plan.json"
        self.gold.write_text(
            json.dumps(
                {
                    "title": "A WordPaper Study",
                    "abstract_contains": "semantic layer",
                    "keywords": ["WordPaper", "docx", "writing"],
                    "sections": ["title", "abstract", "introduction", "methods", "results", "discussion", "references"],
                    "figures": 1,
                    "tables": 1,
                    "references": 2,
                    "requires_review_issue_types": ["missing_conclusion", "table_not_cited", "abstract_underdeveloped"],
                    "requires_revision_actions": ["add_section", "cite_table", "rewrite_abstract"],
                }
            ),
            encoding="utf-8",
        )
        self.plan.write_text(
            json.dumps(
                {
                    "version": 1,
                    "actions": [
                        {
                            "action": "replace_section_text",
                            "target": {"section": "abstract"},
                            "value": "This paper presents a semantic compiler for academic Word manuscripts.",
                        },
                        {"action": "set_keywords", "value": ["WordPaper", "docx", "semantic compiler"]},
                        {
                            "action": "cite_table",
                            "target": {"table_index": 1, "section": "results"},
                            "sentence": "Table 1 summarizes parser accuracy for the prototype.",
                        },
                        {
                            "action": "insert_section_after",
                            "target": {"section": "discussion"},
                            "heading": "Conclusion",
                            "level": 2,
                            "paragraphs": ["WordPaper supports safer AI-assisted manuscript editing."],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_quality_gate_scores_every_category_at_100_for_supported_gold(self):
        from wordpaper.quality import evaluate_quality_gate

        report = evaluate_quality_gate(self.docx, self.gold, self.plan, self.tmp / "compiled.docx")

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["overall_score"], 100)
        self.assertEqual(
            {category["name"]: category["score"] for category in report["categories"]},
            {
                "word_safety": 100,
                "structure_analysis": 100,
                "writing_assist": 100,
                "submission_prep": 100,
                "citation_system": 100,
                "end_to_end": 100,
            },
        )
        self.assertTrue(all(check["passed"] for category in report["categories"] for check in category["checks"]))

    def test_cli_quality_gate_requires_100_percent_when_requested(self):
        from wordpaper.cli import main

        out = self.tmp / "quality-report.json"
        compiled = self.tmp / "compiled.docx"

        rc = main(
            [
                "quality-gate",
                str(self.docx),
                "--gold",
                str(self.gold),
                "--compile-plan",
                str(self.plan),
                "--compiled-out",
                str(compiled),
                "--require-100",
                "--out",
                str(out),
            ]
        )
        report = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["overall_score"], 100)
        self.assertTrue(compiled.exists())

    def test_cli_quality_gate_fails_when_gold_does_not_match(self):
        from wordpaper.cli import main

        bad_gold = self.tmp / "bad-gold.json"
        out = self.tmp / "quality-report.json"
        compiled = self.tmp / "compiled.docx"
        data = json.loads(self.gold.read_text(encoding="utf-8"))
        data["title"] = "Wrong Title"
        bad_gold.write_text(json.dumps(data), encoding="utf-8")

        rc = main(
            [
                "quality-gate",
                str(self.docx),
                "--gold",
                str(bad_gold),
                "--compile-plan",
                str(self.plan),
                "--compiled-out",
                str(compiled),
                "--require-100",
                "--out",
                str(out),
            ]
        )
        report = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(rc, 1)
        self.assertEqual(report["status"], "fail")
        self.assertLess(report["overall_score"], 100)


if __name__ == "__main__":
    unittest.main()
