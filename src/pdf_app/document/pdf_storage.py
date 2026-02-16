"""
pdf_storage.py — Bridge between AnnotationStore and PDF file via PyMuPDF.

Responsibilities:
  - Extract annotations from a PDF into Annotation objects (on open).
  - Write annotations from AnnotationStore back into a PDF (on save).
  - All supported annotations (highlight, underline, FreeText) are fully editable.
  - Unsupported annotation types are left untouched in the PDF.
"""

import fitz  # PyMuPDF
import tempfile
import os
from typing import List, Tuple, Optional
from pdf_app.document.store import Annotation

APP_CREATOR = "Inlinea"

# PyMuPDF annotation type constants
_SUPPORTED_TYPES = {
    fitz.PDF_ANNOT_HIGHLIGHT: "highlight",
    fitz.PDF_ANNOT_UNDERLINE: "underline",
    fitz.PDF_ANNOT_FREE_TEXT: "text",
}

_TYPE_TO_FITZ = {v: k for k, v in _SUPPORTED_TYPES.items()}


def _is_supported(annot) -> bool:
    """Check if annotation type is supported by Inlinea."""
    return annot.type[0] in _SUPPORTED_TYPES


def create_render_copy(source_path: str) -> str:
    """
    Create a temp copy of the PDF with ALL supported annotations removed.

    Poppler renders this clean copy, so our overlay is the only thing
    that draws annotations (making them interactive and editable).

    Returns the path to the temp file.
    """
    doc = fitz.open(source_path)

    for page_index in range(len(doc)):
        page = doc[page_index]
        annots_to_delete = []
        for annot in page.annots():
            if _is_supported(annot):
                annots_to_delete.append(annot)
        for annot in annots_to_delete:
            page.delete_annot(annot)

    fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc.save(temp_path, garbage=4, deflate=True)
    doc.close()

    return temp_path


def _color_from_annot(annot, annot_type: str) -> Tuple[float, float, float, float]:
    """Extract RGBA color from a PyMuPDF annotation."""
    colors = annot.colors

    if annot_type in ("highlight", "underline"):
        rgb = colors.get("stroke") or colors.get("fill")
        if rgb:
            return (rgb[0], rgb[1], rgb[2], 0.4 if annot_type == "highlight" else 1.0)
        if annot_type == "highlight":
            return (1.0, 1.0, 0.0, 0.4)
        return (1.0, 0.0, 0.0, 1.0)

    elif annot_type == "text":
        rgb = colors.get("fill") or colors.get("stroke")
        if rgb:
            return (rgb[0], rgb[1], rgb[2], 1.0)
        return (0.0, 0.0, 0.0, 1.0)

    return (0.0, 0.0, 0.0, 1.0)


def _quads_to_rects(quads) -> List[Tuple[float, float, float, float]]:
    """Convert PyMuPDF Quad objects to (x, y, w, h) tuples."""
    rects = []
    for q in quads:
        r = q.rect
        rects.append((r.x0, r.y0, r.width, r.height))
    return rects


def _rect_to_xywh(rect: fitz.Rect) -> Tuple[float, float, float, float]:
    """Convert fitz.Rect to (x, y, w, h)."""
    return (rect.x0, rect.y0, rect.width, rect.height)


def load_annotations_from_pdf(file_path: str) -> List[Annotation]:
    """
    Extract ALL supported annotations from a PDF file.

    Every supported annotation becomes fully editable in the store.
    Unsupported annotation types are left in the PDF untouched.

    Does NOT modify the PDF.
    """
    annotations = []

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        return annotations

    for page_index in range(len(doc)):
        page = doc[page_index]

        for annot in page.annots():
            annot_fitz_type = annot.type[0]

            if annot_fitz_type not in _SUPPORTED_TYPES:
                continue

            annot_type = _SUPPORTED_TYPES[annot_fitz_type]
            color = _color_from_annot(annot, annot_type)

            # Extract rects
            if annot_type in ("highlight", "underline"):
                quads = annot.vertices
                if quads:
                    quad_list = []
                    for i in range(0, len(quads), 4):
                        if i + 3 < len(quads):
                            quad_list.append(fitz.Quad(quads[i], quads[i+1], quads[i+2], quads[i+3]))
                    rects = _quads_to_rects(quad_list)
                else:
                    rects = [_rect_to_xywh(annot.rect)]
            else:
                rects = [_rect_to_xywh(annot.rect)]

            content = ""
            if annot_type == "text":
                content = annot.info.get("content", "") or annot.get_text() or ""

            ann = Annotation.create(
                type=annot_type,
                page_index=page_index,
                rects=rects,
                color=color,
                content=content,
            )

            annotations.append(ann)

    doc.close()
    return annotations


def save_annotations_to_pdf(
    source_path: str,
    output_path: str,
    annotations: List[Annotation],
) -> None:
    """
    Write annotations from the store into a PDF file.

    Process:
      1. Open source PDF.
      2. Remove ALL supported annotations from every page.
      3. Re-add all annotations from the store.
      4. Save to output_path.

    Unsupported annotation types are preserved untouched.
    """
    doc = fitz.open(source_path)

    # Phase 1: Remove ALL supported annotations
    for page_index in range(len(doc)):
        page = doc[page_index]
        annots_to_delete = []

        for annot in page.annots():
            if _is_supported(annot):
                annots_to_delete.append(annot)

        for annot in annots_to_delete:
            page.delete_annot(annot)

    # Phase 2: Re-add annotations from store
    for ann in annotations:
        if ann.page_index < 0 or ann.page_index >= len(doc):
            continue

        page = doc[ann.page_index]
        r, g, b, a = ann.color

        try:
            if ann.type == "highlight":
                _add_markup_annot(page, ann, fitz.PDF_ANNOT_HIGHLIGHT, (r, g, b))
            elif ann.type == "underline":
                _add_markup_annot(page, ann, fitz.PDF_ANNOT_UNDERLINE, (r, g, b))
            elif ann.type == "text":
                _add_freetext_annot(page, ann, (r, g, b))
        except Exception as e:
            print(f"WARNING: Failed to write annotation {ann.id}: {e}")
            import traceback
            traceback.print_exc()

    # Phase 3: Save
    if output_path == source_path:
        doc.save(doc.name, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    else:
        doc.save(output_path, garbage=4, deflate=True)

    doc.close()


def _add_markup_annot(page, ann: Annotation, fitz_type: int, rgb: tuple):
    """Add a highlight or underline annotation to a page."""
    quads = []
    for rect_tuple in ann.rects:
        x, y, w, h = rect_tuple
        r = fitz.Rect(x, y, x + w, y + h)
        quads.append(r)

    if not quads:
        return

    if fitz_type == fitz.PDF_ANNOT_HIGHLIGHT:
        annot = page.add_highlight_annot(quads)
    else:
        annot = page.add_underline_annot(quads)

    annot.set_colors(stroke=rgb)
    annot.set_info(title=APP_CREATOR)
    annot.update()


def _add_freetext_annot(page, ann: Annotation, rgb: tuple):
    """Add a FreeText annotation to a page."""
    if not ann.rects:
        return

    x, y, w, h = ann.rects[0]
    rect = fitz.Rect(x, y, x + w, y + h)

    text = ann.content or ""

    annot = page.add_freetext_annot(
        rect,
        text,
        fontsize=12,
        fontname="helv",
        text_color=rgb,
        fill_color=None,
    )

    annot.set_info(title=APP_CREATOR)
    annot.update()
