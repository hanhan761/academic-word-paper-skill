import json
import shutil
import unittest
from pathlib import Path

from tests.test_academic_analysis import ACADEMIC_DOCUMENT_XML
from tests.test_wordpaper_mvp import DOC_RELS, write_docx


class WordCompilerTests(unittest.TestCase):
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

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_compile_document_applies_semantic_plan_and_reports_validation(self):
        from wordpaper.academic import analyze_writing
        from wordpaper.compiler import compile_document

        out = self.tmp / "compiled.docx"
        plan = {
            "version": 1,
            "actions": [
                {
                    "action": "replace_section_text",
                    "target": {"section": "abstract"},
                    "value": [
                        "This study evaluates WordPaper as a semantic compiler for academic Word manuscripts.",
                        "It separates manuscript intent from OOXML storage so agents can edit safely.",
                    ],
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
                    "paragraphs": ["WordPaper provides a safer foundation for AI-assisted manuscript editing."],
                },
            ],
        }

        report = compile_document(self.docx, plan, out)
        analysis = analyze_writing(out)

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["patch"]["status"], "ok")
        self.assertEqual(report["validation"]["status"], "ok")
        self.assertTrue(report["diff"]["changes"])
        self.assertIn("semantic compiler", analysis["keywords"])
        self.assertTrue(analysis["citation_checks"]["tables"][0]["cited"])
        self.assertIn("conclusion", {section["type"] for section in analysis["sections"]})
        self.assertIn("semantic compiler", analysis["abstract"]["text"])

    def test_cli_compile_writes_docx_and_report(self):
        from wordpaper.academic import analyze_writing
        from wordpaper.cli import main

        plan_path = self.tmp / "compile-plan.json"
        out = self.tmp / "compiled.docx"
        report_path = self.tmp / "compile-report.json"
        plan_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "actions": [
                        {
                            "action": "replace_section_text",
                            "target": {"section": "abstract"},
                            "value": "This paper presents a compiled Word workflow for academic manuscripts.",
                        },
                        {"action": "set_keywords", "value": ["WordPaper", "compiler"]},
                    ],
                }
            ),
            encoding="utf-8",
        )

        rc = main(["compile", str(self.docx), str(plan_path), "--out", str(out), "--report", str(report_path)])
        report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertTrue(out.exists())
        self.assertEqual(report["patch"]["status"], "ok")
        self.assertIn("compiled Word workflow", analyze_writing(out)["abstract"]["text"])


if __name__ == "__main__":
    unittest.main()
