import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Annotation:
    id: str
    type: str  
    page_index: int
    rects: List[Tuple[float, float, float, float]]  
    color: Tuple[float, float, float, float] = (1.0, 1.0, 0.0, 0.4)  
    content: str = ""
    style: str = "standard"
    created_at: str = ""

    @classmethod
    def create(cls, type: str, page_index: int, rects: List[Tuple[float, float, float, float]],
               color: Tuple[float, float, float, float] = None, content: str = ""):

        # Default Colors
        if color is None:
            if type == 'highlight':
                color = (1.0, 1.0, 0.0, 1.0)  # Yellow
            elif type == 'underline':
                color = (1.0, 0.0, 0.0, 1.0)  # Red
            else:
                color = (0.0, 0.0, 0.0, 1.0)  # Black text

        return cls(
            id=str(uuid.uuid4()),
            type=type,
            page_index=page_index,
            rects=rects,
            color=color,
            content=content,
        )


class AnnotationStore:

    def __init__(self):
        self.annotations: List[Annotation] = []
        self._is_dirty: bool = False
        self.on_dirty_changed = None  # Callback function(is_dirty: bool)

        # Shared Default Colors for new annotations
        self.default_highlight_color = (1.0, 1.0, 0.0) # Yellow
        self.default_underline_color = (1.0, 0.0, 0.0) # Red
        self.default_area_color = (1.0, 1.0, 0.0)      # Yellow

        # Undo/Redo stacks store tuples: (operation, annotation)
        self._undo_stack: List[tuple] = []
        self._redo_stack: List[tuple] = []

    @property
    def is_dirty(self):
        return self._is_dirty

    @is_dirty.setter
    def is_dirty(self, value: bool):
        self._is_dirty = value
        if self.on_dirty_changed:
            from gi.repository import GLib
            GLib.idle_add(self.on_dirty_changed, value)

    # ========== PDF I/O ==========

    def load_from_pdf(self, file_path: str):
        from pdf_app.document.pdf_storage import load_annotations_from_pdf

        self.annotations = load_annotations_from_pdf(file_path)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.is_dirty = False

    def save_to_pdf(self, source_path: str, output_path: str):
        from pdf_app.document.pdf_storage import save_annotations_to_pdf

        save_annotations_to_pdf(source_path, output_path, self.annotations)
        self.is_dirty = False

    # ========== CRUD ==========

    def add(self, annotation: Annotation):
        self.annotations.append(annotation)
        self.is_dirty = True
        self._undo_stack.append(('add', annotation))
        self._redo_stack.clear()

    def get_for_page(self, page_index: int) -> List[Annotation]:
        return [a for a in self.annotations if a.page_index == page_index]

    def remove(self, annotation_id: str):
        removed = None
        new_list = []
        for a in self.annotations:
            if a.id == annotation_id:
                removed = a
            else:
                new_list.append(a)

        if removed:
            self._undo_stack.append(('remove', removed))
            self._redo_stack.clear()
            self.annotations = new_list
            self.is_dirty = True

    def record_modify(self, annotation_id: str, old_rects: list):
        self._undo_stack.append(('modify', annotation_id, old_rects))
        self._redo_stack.clear()
        self.is_dirty = True

    def record_color_change(self, annotation_id: str, old_color: tuple):
        self._undo_stack.append(('color', annotation_id, old_color))
        self._redo_stack.clear()
        self.is_dirty = True

    # ========== UNDO / REDO ==========

    def undo(self) -> Optional[tuple]:
        if not self._undo_stack:
            return None

        entry = self._undo_stack.pop()
        op = entry[0]

        if op == 'add':
            ann = entry[1]
            self.annotations = [a for a in self.annotations if a.id != ann.id]
            self._redo_stack.append(entry)
            self.is_dirty = True
            return (op, ann)
        elif op == 'remove':
            ann = entry[1]
            self.annotations.append(ann)
            self._redo_stack.append(entry)
            self.is_dirty = True
            return (op, ann)
        elif op == 'modify':
            annotation_id, old_rects = entry[1], entry[2]
            for ann in self.annotations:
                if ann.id == annotation_id:
                    current_rects = list(ann.rects) if ann.rects else []
                    ann.rects = old_rects
                    self._redo_stack.append(('modify', annotation_id, current_rects))
                    self.is_dirty = True
                    return (op, ann)
        elif op == 'color':
            annotation_id, old_color = entry[1], entry[2]
            for ann in self.annotations:
                if ann.id == annotation_id:
                    current_color = ann.color
                    ann.color = old_color
                    self._redo_stack.append(('color', annotation_id, current_color))
                    self.is_dirty = True
                    return (op, ann)
        return None

    def redo(self) -> Optional[tuple]:
        if not self._redo_stack:
            return None

        entry = self._redo_stack.pop()
        op = entry[0]

        if op == 'add':
            ann = entry[1]
            self.annotations.append(ann)
            self._undo_stack.append(entry)
            self.is_dirty = True
            return (op, ann)
        elif op == 'remove':
            ann = entry[1]
            self.annotations = [a for a in self.annotations if a.id != ann.id]
            self._undo_stack.append(entry)
            self.is_dirty = True
            return (op, ann)
        elif op == 'modify':
            annotation_id, new_rects = entry[1], entry[2]
            for ann in self.annotations:
                if ann.id == annotation_id:
                    current_rects = list(ann.rects) if ann.rects else []
                    ann.rects = new_rects
                    self._undo_stack.append(('modify', annotation_id, current_rects))
                    self.is_dirty = True
                    return (op, ann)
        elif op == 'color':
            annotation_id, new_color = entry[1], entry[2]
            for ann in self.annotations:
                if ann.id == annotation_id:
                    current_color = ann.color
                    ann.color = new_color
                    self._undo_stack.append(('color', annotation_id, current_color))
                    self.is_dirty = True
                    return (op, ann)
        return None

    # ========== QUERY ==========

    def find_annotation_at(self, page_index: int, x: float, y: float, tolerance: float = 5.0) -> Optional[Annotation]:
        for ann in reversed(self.annotations):
            if ann.page_index != page_index:
                continue

            if not ann.rects:
                continue
            for r in ann.rects:
                rx, ry, rw, rh = r
                if (rx - tolerance) <= x <= (rx + rw + tolerance) and \
                   (ry - tolerance) <= y <= (ry + rh + tolerance):
                    return ann
        return None
