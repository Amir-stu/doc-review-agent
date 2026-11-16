"""Step 02 dispatch: pick the reader by file type."""

from pathlib import Path

from docreview.models import Document
from docreview.readers.docx_reader import read_docx
from docreview.readers.pptx_reader import read_pptx
from docreview.readers.xlsx_reader import read_xlsx

READERS = {".pptx": read_pptx, ".docx": read_docx, ".xlsx": read_xlsx}


def read_document(path: Path) -> Document:
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"Nicht unterstützter Dateityp: {path.suffix}")
    return reader(path)
