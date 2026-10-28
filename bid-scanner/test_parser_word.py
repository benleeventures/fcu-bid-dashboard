"""
Tests for reading Word (.docx) documents that downloaders saved as <id>.pdf.

    python test_parser_word.py
"""

import io
import tempfile
import zipfile
from pathlib import Path

from parser import _word_file_text

DOC_XML = (
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
    '<w:p><w:r><w:t>NOTICE IS HEREBY GIVEN that the District</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>UNIT PRICE </w:t></w:r><w:r><w:t>FLOORING</w:t></w:r></w:p>'
    '</w:body></w:document>'
)


def _write(path: Path, data: bytes):
    path.write_bytes(data)
    return path


def test_docx_saved_as_pdf_is_read():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", DOC_XML)
    with tempfile.TemporaryDirectory() as d:
        text = _word_file_text(_write(Path(d) / "444212731521.pdf", buf.getvalue()))
    assert text == "NOTICE IS HEREBY GIVEN that the District\nUNIT PRICE FLOORING"


def test_real_pdf_and_other_zip_are_left_alone():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("plans.pdf", b"%PDF-1.7")
    with tempfile.TemporaryDirectory() as d:
        assert _word_file_text(_write(Path(d) / "a.pdf", b"%PDF-1.7\n%...")) is None
        assert _word_file_text(_write(Path(d) / "b.pdf", buf.getvalue())) is None


if __name__ == "__main__":
    test_docx_saved_as_pdf_is_read()
    test_real_pdf_and_other_zip_are_left_alone()
    print("✓ Word document tests pass")
