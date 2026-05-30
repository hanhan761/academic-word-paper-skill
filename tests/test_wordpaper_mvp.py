import json
import shutil
import unittest
import zipfile
from pathlib import Path


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>
  <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>
"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="Heading 2"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="Heading 3"/></w:style>
  <w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="Caption"/></w:style>
</w:styles>
"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImage1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
  <Relationship Id="rIdMissing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/missing.png"/>
</Relationships>
"""

FOOTNOTES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:footnote w:id="-1"><w:p><w:r><w:t>Separator should not count.</w:t></w:r></w:p></w:footnote>
  <w:footnote w:id="0"><w:p><w:r><w:t>Continuation separator should not count.</w:t></w:r></w:p></w:footnote>
  <w:footnote w:id="1"><w:p><w:r><w:t>Footnote body.</w:t></w:r></w:p></w:footnote>
</w:footnotes>
"""

COMMENTS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="0" w:author="Reviewer"><w:p><w:r><w:t>Please clarify.</w:t></w:r></w:p></w:comment>
</w:comments>
"""

DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>Introduction</w:t></w:r>
    </w:p>
    <w:p>
      <w:pPr><w:pStyle w:val="Normal"/></w:pPr>
      <w:r><w:t>This study </w:t></w:r>
      <w:r><w:rPr><w:i/></w:rPr><w:t>examines</w:t></w:r>
      <w:r><w:t> Word papers.</w:t></w:r>
    </w:p>
    <w:p>
      <w:pPr><w:pStyle w:val="Normal"/></w:pPr>
      <w:r><w:drawing><a:blip r:embed="rIdImage1"/></w:drawing></w:r>
    </w:p>
    <w:p>
      <w:pPr><w:pStyle w:val="Caption"/></w:pPr>
      <w:r><w:t>Figure 1. Model results.</w:t></w:r>
    </w:p>
    <w:p>
      <w:pPr><w:pStyle w:val="Caption"/></w:pPr>
      <w:r><w:t>Table 1. Regression results.</w:t></w:r>
    </w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Variable</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Model 1</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>x</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>0.42</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>
"""

HEADING_SKIP_XML = DOCUMENT_XML.replace(
    '<w:pStyle w:val="Heading1"/>', '<w:pStyle w:val="Heading1"/>', 1
).replace(
    '<w:pPr><w:pStyle w:val="Caption"/></w:pPr>\n      <w:r><w:t>Figure 1. Model results.</w:t></w:r>',
    '<w:pPr><w:pStyle w:val="Heading3"/></w:pPr>\n      <w:r><w:t>Deep Result</w:t></w:r>',
    1,
)


def write_docx(path, document_xml=DOCUMENT_XML, document_rels=DOC_RELS):
    zip_path = path.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", STYLES_XML)
        archive.writestr("word/footnotes.xml", FOOTNOTES_XML)
        archive.writestr("word/comments.xml", COMMENTS_XML)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("word/media/image1.png", b"not-a-real-image-but-a-package-target")
    zip_path.replace(path)


class WordPaperMvpTests(unittest.TestCase):
    def setUp(self):
        tmp_root = Path.cwd() / ".tmp-tests"
        tmp_root.mkdir(exist_ok=True)
        self.tmp = tmp_root / self._testMethodName
        if self.tmp.exists():
            shutil.rmtree(self.tmp)
        self.tmp.mkdir()
        self.docx = self.tmp / "paper.docx"
        write_docx(self.docx)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_export_ir_recovers_academic_blocks_and_objects(self):
        from wordpaper import export_ir

        ir = export_ir(self.docx)

        self.assertEqual(ir["type"], "academic_paper")
        self.assertEqual(ir["blocks"][0]["type"], "heading")
        self.assertEqual(ir["blocks"][0]["level"], 1)
        self.assertEqual(ir["blocks"][0]["text"], "Introduction")
        self.assertEqual(ir["blocks"][1]["runs"][1]["text"], "examines")
        self.assertTrue(ir["blocks"][1]["runs"][1]["italic"])
        self.assertEqual(ir["figures"][0]["caption"]["text"], "Figure 1. Model results.")
        self.assertEqual(ir["tables"][0]["caption"]["text"], "Table 1. Regression results.")
        self.assertEqual(ir["tables"][0]["rows"][1]["cells"][1]["text"], "0.42")
        self.assertEqual(len(ir["footnotes"]), 1)
        self.assertEqual(ir["footnotes"][0]["id"], "1")
        self.assertEqual(ir["footnotes"][0]["text"], "Footnote body.")
        self.assertEqual(ir["comments"][0]["author"], "Reviewer")
        self.assertIn("word/media/image1.png", ir["media"])

    def test_validate_reports_relationship_errors_and_heading_skips(self):
        from wordpaper import validate_docx

        skipped = self.tmp / "skipped.docx"
        write_docx(skipped, document_xml=HEADING_SKIP_XML)
        report = validate_docx(skipped)

        codes = {item["type"] for item in report["errors"] + report["warnings"]}
        self.assertEqual(report["status"], "error")
        self.assertIn("missing_relationship_target", codes)
        self.assertIn("heading_level_skip", codes)

    def test_apply_patch_replaces_block_text_and_inserts_paragraph(self):
        from wordpaper import apply_patch, export_ir, validate_docx

        ir = export_ir(self.docx)
        target_id = ir["blocks"][1]["id"]
        out = self.tmp / "revised.docx"
        patch = {
            "version": 1,
            "actions": [
                {
                    "action": "replace_block_text",
                    "target": {"block_id": target_id},
                    "value": "This study validates the WordPaper IR.",
                },
                {
                    "action": "insert_after",
                    "target": {"block_id": target_id},
                    "block": {
                        "type": "paragraph",
                        "text": "Additional robustness checks are reported in Appendix B.",
                        "style": "Normal",
                    },
                },
            ],
        }

        result = apply_patch(self.docx, patch, out)
        revised = export_ir(out)

        self.assertEqual(result["status"], "ok")
        texts = [block["text"] for block in revised["blocks"]]
        self.assertIn("This study validates the WordPaper IR.", texts)
        self.assertIn("Additional robustness checks are reported in Appendix B.", texts)
        self.assertEqual(validate_docx(out)["status"], "error")

    def test_cli_export_ir_and_apply_accept_json_patch_files(self):
        from wordpaper.cli import main

        ir_path = self.tmp / "paper.ir.json"
        patch_path = self.tmp / "patch.json"
        out = self.tmp / "cli-revised.docx"

        rc = main(["export-ir", str(self.docx), "--out", str(ir_path)])
        self.assertEqual(rc, 0)
        block_id = json.loads(ir_path.read_text(encoding="utf-8"))["blocks"][1]["id"]
        patch_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "actions": [
                        {
                            "action": "replace_block_text",
                            "target": {"block_id": block_id},
                            "value": "CLI patch succeeded.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        rc = main(["apply", str(self.docx), str(patch_path), "--out", str(out)])
        self.assertEqual(rc, 0)
        self.assertIn("CLI patch succeeded.", [b["text"] for b in json.loads(json.dumps(__import__("wordpaper").export_ir(out)))["blocks"]])


if __name__ == "__main__":
    unittest.main()
