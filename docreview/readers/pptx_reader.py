"""Step 02 for PowerPoint: one unit per slide, one container per text box or table cell."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.enum.dml import MSO_COLOR_TYPE
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE

from docreview.config import EMU_PER_POINT
from docreview.models import Container, Document, Paragraph, TextRun, Unit

AUTO_FIT_MODES = (MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT, MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE)


@dataclass(frozen=True)
class FrameRef:
    slide_number: int
    container: Container
    text_frame: Any


def _walk_shapes(shapes: Any) -> Iterator[Any]:
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _walk_shapes(shape.shapes)
        else:
            yield shape


def _points(emu: int | None) -> float | None:
    return round(emu / EMU_PER_POINT, 1) if emu else None


def _shape_frames(slide_number: int, shape: Any) -> Iterator[FrameRef]:
    base_id = f"s{slide_number}/sh{shape.shape_id}"
    if shape.has_text_frame:
        frame = shape.text_frame
        container = Container(
            container_id=base_id,
            locator=f'Folie {slide_number}, Form "{shape.name}"',
            width_pt=_points(shape.width),
            height_pt=_points(shape.height),
            auto_fit=frame.auto_size in AUTO_FIT_MODES,
            word_wrap=frame.word_wrap is not False,
        )
        yield FrameRef(slide_number, container, frame)
        return
    if not getattr(shape, "has_table", False):
        return
    table = shape.table
    for row_index, row in enumerate(table.rows):
        for column_index, cell in enumerate(row.cells):
            container = Container(
                container_id=f"{base_id}/r{row_index}c{column_index}",
                locator=(
                    f'Folie {slide_number}, Tabelle "{shape.name}", '
                    f"Zeile {row_index + 1} Spalte {column_index + 1}"
                ),
                width_pt=_points(table.columns[column_index].width),
                height_pt=_points(row.height),
            )
            yield FrameRef(slide_number, container, cell.text_frame)


def iter_frames(presentation: Any) -> Iterator[FrameRef]:
    """Shared by reader and writer so paragraph IDs resolve to the same objects."""
    for slide_number, slide in enumerate(presentation.slides, start=1):
        for shape in _walk_shapes(slide.shapes):
            yield from _shape_frames(slide_number, shape)


def paragraph_id(container_id: str, index: int) -> str:
    return f"{container_id}/p{index}"


def _run_color(font: Any) -> str | None:
    color = font.color
    if color is None or color.type != MSO_COLOR_TYPE.RGB:
        return None
    return str(color.rgb).upper()


def _read_run(run: Any) -> TextRun:
    font = run.font
    return TextRun(
        text=run.text,
        font=font.name,
        size_pt=font.size.pt if font.size is not None else None,
        color=_run_color(font),
        bold=font.bold,
    )


def _read_paragraphs(ref: FrameRef) -> list[Paragraph]:
    paragraphs = []
    for index, paragraph in enumerate(ref.text_frame.paragraphs):
        text = "".join(run.text for run in paragraph.runs)
        if not text.strip():
            continue
        alignment = paragraph.alignment
        paragraphs.append(
            Paragraph(
                paragraph_id=paragraph_id(ref.container.container_id, index),
                locator=f"{ref.container.locator}, Absatz {index + 1}",
                text=text,
                runs=tuple(_read_run(run) for run in paragraph.runs),
                alignment=alignment.name if alignment is not None else None,
                container_id=ref.container.container_id,
            )
        )
    return paragraphs


def read_pptx(path: Path) -> Document:
    presentation = Presentation(str(path))
    frames = list(iter_frames(presentation))
    units = []
    for slide_number in range(1, len(presentation.slides) + 1):
        slide_frames = [ref for ref in frames if ref.slide_number == slide_number]
        units.append(
            Unit(
                unit_id=f"slide-{slide_number}",
                label=f"Folie {slide_number}",
                paragraphs=tuple(p for ref in slide_frames for p in _read_paragraphs(ref)),
                containers=tuple(ref.container for ref in slide_frames),
            )
        )
    return Document(file_type="pptx", source_path=str(path), units=tuple(units))
