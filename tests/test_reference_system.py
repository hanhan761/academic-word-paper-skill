import json
import shutil
import unittest
from pathlib import Path

from tests.test_wordpaper_mvp import DOC_RELS, write_docx


REFERENCE_DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Reference Stress Paper</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Abstract</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>This paper tests reference auditing for Word manuscripts.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>Keywords: references; citations; docx</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Introduction</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>Prior work [1,3] shows that Word references need structured auditing. Smith (2024) also describes document engineering.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Methods</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>We parse numbered and author-year references conservatively.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Results</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>The audit reports missing, uncited, duplicate, and incomplete references.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Discussion</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>Reference metadata remains local and deterministic.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Conclusion</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>Structured reference checks make manuscript preparation safer.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>References</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>[1] Smith J. Document engineering. Journal of Word Systems. 2024. doi:10.1000/word.2024.001 PMID: 12345678.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>[2] Smith J. Document engineering. Journal of Word Systems. 2024. DOI: 10.1000/word.2024.001.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>[4] NoYear A. Incomplete reference without a publication year.</w:t></w:r></w:p>
  </w:body>
</w:document>
"""


class ReferenceSystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path.cwd() / ".tmp-tests" / self._testMethodName
        if self.tmp.exists():
            shutil.rmtree(self.tmp)
        self.tmp.mkdir(parents=True)
        self.docx = self.tmp / "references.docx"
        valid_rels = DOC_RELS.replace(
            '  <Relationship Id="rIdMissing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/missing.png"/>\n',
            "",
        )
        write_docx(self.docx, document_xml=REFERENCE_DOCUMENT_XML, document_rels=valid_rels)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_audit_references_parses_metadata_and_body_citations(self):
        from wordpaper.academic import audit_references

        report = audit_references(self.docx)

        first = report["items"][0]
        self.assertEqual(report["status"], "warning")
        self.assertEqual(first["label"], "1")
        self.assertEqual(first["style"], "numbered")
        self.assertEqual(first["year"], "2024")
        self.assertEqual(first["doi"], "10.1000/word.2024.001")
        self.assertEqual(first["pmid"], "12345678")
        self.assertIn("Smith", first["authors"])
        self.assertEqual(report["citations"]["numeric"], ["1", "3"])
        self.assertIn({"author": "Smith", "year": "2024"}, report["citations"]["author_year"])

    def test_audit_references_reports_actionable_integrity_issues(self):
        from wordpaper.academic import audit_references

        report = audit_references(self.docx)
        issue_types = {issue["type"] for issue in report["issues"]}

        self.assertIn("citation_without_reference", issue_types)
        self.assertIn("reference_not_cited", issue_types)
        self.assertIn("duplicate_doi", issue_types)
        self.assertIn("numbered_reference_sequence_gap", issue_types)
        self.assertIn("missing_year", issue_types)
        self.assertIn("reference_author_year_cited", {check["type"] for check in report["checks"]})

    def test_cli_exports_reference_audit(self):
        from wordpaper.cli import main

        out = self.tmp / "reference-audit.json"

        rc = main(["audit-references", str(self.docx), "--out", str(out)])
        report = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertEqual(report["reference_count"], 3)
        self.assertIn("citation_without_reference", {issue["type"] for issue in report["issues"]})


if __name__ == "__main__":
    unittest.main()
