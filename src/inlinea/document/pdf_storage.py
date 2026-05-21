
import fitz  # PyMuPDF
from typing import List, Tuple
import json
from inlinea.document.store import Annotation

APP_CREATOR = "Inlinea"

_SUPPORTED_TYPES = {
    fitz.PDF_ANNOT_HIGHLIGHT: "highlight",
    fitz.PDF_ANNOT_UNDERLINE: "underline",
    fitz.PDF_ANNOT_SQUARE: "square",
    fitz.PDF_ANNOT_FREE_TEXT: "text",
}

_TYPE_TO_FITZ = {v: k for k, v in _SUPPORTED_TYPES.items()}


def _is_supported(annot) -> bool:
    return annot.type[0] in _SUPPORTED_TYPES




def _color_from_annot(annot, annot_type: str) -> Tuple[float, float, float, float]:
    colors = annot.colors

    if annot_type in ("highlight", "underline"):
        rgb = colors.get("stroke") or colors.get("fill")
        if rgb:
            return (rgb[0], rgb[1], rgb[2], 0.4 if annot_type == "highlight" else 1.0)
        if annot_type == "highlight":
            return (1.0, 1.0, 0.0, 0.4)
        return (1.0, 0.0, 0.0, 1.0)
    
    elif annot_type == "square":
        rgb = colors.get("fill") or colors.get("stroke")
        if rgb:
             return (rgb[0], rgb[1], rgb[2], 0.4)
        return (1.0, 1.0, 0.0, 0.4)

    elif annot_type == "text":
        rgb = colors.get("fill") or colors.get("stroke")
        if rgb:
            return (rgb[0], rgb[1], rgb[2], 1.0)
        return (0.0, 0.0, 0.0, 1.0)

    return (0.0, 0.0, 0.0, 1.0)


def _quads_to_rects(quads) -> List[Tuple[float, float, float, float]]:
    rects = []
    for q in quads:
        r = q.rect
        rects.append((r.x0, r.y0, r.width, r.height))
    return rects


def _rect_to_xywh(rect: fitz.Rect) -> Tuple[float, float, float, float]:
    return (rect.x0, rect.y0, rect.width, rect.height)


def load_annotations_from_pdf(file_path: str) -> List[Annotation]:
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
            font_size = 14
            font_family = "Sans"
            bold = False
            italic = False
            underline = False
            
            if annot_type == "text":
                content = annot.info.get("content", "") or annot.get_text() or ""
                subject = annot.info.get("subject", "")
                try:
                    if subject.startswith("{"):
                        meta = json.loads(subject)
                        font_size = meta.get("font_size", 14)
                        font_family = meta.get("font_family", "Sans")
                        bold = meta.get("bold", False)
                        italic = meta.get("italic", False)
                        underline = meta.get("underline", False)
                        if "color" in meta:
                            color = tuple(meta["color"])
                except Exception:
                    pass

            ann = Annotation.create(
                type=annot_type,
                page_index=page_index,
                rects=rects,
                color=color,
                content=content,
            )
            if annot_type == "text":
                ann.font_size = font_size
                ann.font_family = font_family
                ann.bold = bold
                ann.italic = italic
                ann.underline = underline

            annotations.append(ann)

    doc.close()
    return annotations


def save_annotations_to_pdf(
    source_path: str,
    output_path: str,
    annotations: List[Annotation],
) -> None:
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
            elif ann.type == "square":
                 _add_square_annot(page, ann, (r, g, b))
        except Exception:
            pass

    # Phase 3: Save
    if output_path == source_path:
        doc.save(doc.name, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    else:
        doc.save(output_path, garbage=4, deflate=True)

    doc.close()


def _add_markup_annot(page, ann: Annotation, fitz_type: int, rgb: tuple):
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
    if not ann.rects:
        return

    x, y, w, h = ann.rects[0]
    rect = fitz.Rect(x, y, x + w, y + h)

    text = ann.content or ""

    annot = page.add_freetext_annot(
        rect,
        text,
        fontsize=ann.font_size,
        fontname="helv", # PyMuPDF expects base 14 fonts here, better to leave helv and use JSON metadata for app rendering
        text_color=rgb,
        fill_color=None,
    )

    meta = {
        "font_size": ann.font_size,
        "font_family": ann.font_family,
        "bold": ann.bold,
        "italic": ann.italic,
        "underline": ann.underline,
        "color": list(ann.color)
    }

    annot.set_info(title=APP_CREATOR, subject=json.dumps(meta))
    annot.update()


def _add_square_annot(page, ann: Annotation, rgb: tuple):
    if not ann.rects: return
    
    x, y, w, h = ann.rects[0]
    rect = fitz.Rect(x, y, x + w, y + h) # x0, y0, x1, y1
    
    if hasattr(page, "add_square_annot"):
        annot = page.add_square_annot(rect)
    else:
        annot = page.add_rect_annot(rect)
        
    annot.set_colors(stroke=None, fill=rgb)
    annot.set_opacity(0.4)
    annot.set_info(title=APP_CREATOR)
    annot.update()
