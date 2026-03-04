import cairo
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Poppler', '0.18')
from gi.repository import Gtk, Gdk, GLib, Poppler

from pdf_app.document.render import render_page_to_surface
from pdf_app.document.store import Annotation, AnnotationStore
from pdf_app.ui.text_dialog import TextAnnotationDialog

from pdf_app.ui.pdf_drawing_area import PDFDrawingArea
from pdf_app.ui.text_editor import TextEditorPopover

class PDFPageView(Gtk.Overlay):

    def __init__(self, page, page_number, store: AnnotationStore):
        super().__init__()
        self.page = page
        self.page_number = page_number
        self.store = store
        self.scale = 1.0
        self.text_mode = False 
        self.current_tool = None 
        
        self.drawing_area = PDFDrawingArea(page, self.scale, store)
        self.set_child(self.drawing_area)
        
        
        self.update_size()
        
        self.setup_gestures_on_drawing_area()
        
        self.resize_gesture = Gtk.GestureDrag()
        self.resize_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.resize_gesture.set_button(1) 
        self.resize_gesture.connect("drag-begin", self.on_resize_drag_begin)
        self.resize_gesture.connect("drag-update", self.on_resize_drag_update)
        self.resize_gesture.connect("drag-end", self.on_resize_drag_end)
        self.add_controller(self.resize_gesture)

        click_gesture = Gtk.GestureClick()
        click_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click_gesture.set_button(0)
        click_gesture.connect("pressed", self.on_click_pressed)
        self.add_controller(click_gesture)
        
        click_gesture.group(self.resize_gesture)

        self.setup_popover()
        self.color_popover = None
        self.editor_popover = None
        
        self.default_highlight_color = (1.0, 1.0, 0.0) # Yellow
        self.default_underline_color = (1.0, 0.0, 0.0) # Red
        self.default_area_color = (1.0, 1.0, 0.0) # Yellow (Area)
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)


    def set_text_mode(self, enabled):
        if enabled:
            self.activate_tool('text')
        else:
            self.activate_tool(None)

    def update_size(self):
        w, h = self.page.get_size()
        scaled_w = int(w * self.scale)
        scaled_h = int(h * self.scale)
        
        self.drawing_area.set_content_width(scaled_w)
        self.drawing_area.set_content_height(scaled_h)
        self.drawing_area.update_scale(self.scale)

    def update_scale(self, new_scale):
        self.scale = new_scale
        self.update_size()

    def preview_scale(self, new_scale):
        w, h = self.page.get_size()
        scaled_w = int(w * new_scale)
        scaled_h = int(h * new_scale)
        self.drawing_area.set_content_width(scaled_w)
        self.drawing_area.set_content_height(scaled_h)
        self.drawing_area.queue_draw()

    def on_annotation_update(self, ann):
        self.store.is_dirty = True

    def open_text_editor(self, ann):
        if self.editor_popover:
            self.editor_popover.popdown()
            self.editor_popover.unparent()
            self.editor_popover = None
            
        self.editor_popover = TextEditorPopover(self, ann, self.on_text_updated)
        self.editor_popover.update_position(self.scale)
        self.editor_popover.popup()
        
    def on_text_updated(self, ann):
        self.drawing_area.queue_draw()
        self.store.is_dirty = True

    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            if self.current_tool:
                self.activate_tool(None)
                root = self.get_native()
                if hasattr(root, 'update_ribbon_tool_state'):
                    root.update_ribbon_tool_state(None)
                return True
                
            if self.drawing_area.selected_annotation:
                self.drawing_area.selected_annotation = None
                self.drawing_area.queue_draw()
                return True
                
        if keyval == Gdk.KEY_Delete or keyval == Gdk.KEY_BackSpace:
            if self.drawing_area.selected_annotation:
                ann = self.drawing_area.selected_annotation
                self.store.remove(ann.id)
                self.drawing_area.selected_annotation = None
                self.drawing_area.queue_draw()
                return True
                
        return False

    def copy_selected_text(self):
        if not self.drawing_area.selection_start or not self.drawing_area.selection_end:
            return False

        x1, y1 = self.drawing_area.selection_start
        x2, y2 = self.drawing_area.selection_end

        pdf_scale = 1.0 / self.scale
        rect = Poppler.Rectangle()
        rect.x1 = min(x1, x2) * pdf_scale
        rect.y1 = min(y1, y2) * pdf_scale
        rect.x2 = max(x1, x2) * pdf_scale
        rect.y2 = max(y1, y2) * pdf_scale

        try:
            text = self.page.get_selected_text(Poppler.SelectionStyle.GLYPH, rect)
        except Exception:
            return False
        if not text or not text.strip():
            return False

        clipboard = self.get_clipboard()
        clipboard.set(text)
        return True

    def on_resize_drag_begin(self, gesture, start_x, start_y):
        handled = self.drawing_area.handle_drag_begin(start_x, start_y)
        if handled:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        else:
            self.handle_click_logic(start_x, start_y)
            gesture.set_state(Gtk.EventSequenceState.DENIED)

    def handle_click_logic(self, x, y):
        if self.current_tool == 'text':
            self.create_text_annotation_at_click(x, y)
            return

        self.popover.popdown()
        hit_ann = self.store.find_annotation_at(self.page_number, x/self.scale, y/self.scale)
        
        if hit_ann:
            self.drawing_area.selected_annotation = hit_ann
            self.drawing_area.selected_region = None
            self.drawing_area.queue_draw()
            self.drawing_area.grab_focus()
        else:
            if self.drawing_area.selected_annotation and not self.drawing_area.is_point_on_handle(x, y):
                 self.drawing_area.selected_annotation = None
                 self.drawing_area.queue_draw()
            self.drawing_area.grab_focus()

    def on_resize_drag_update(self, gesture, offset_x, offset_y):
        self.drawing_area.handle_drag_update(offset_x, offset_y)

    def on_resize_drag_end(self, gesture, offset_x, offset_y):
        self.drawing_area.handle_drag_end(offset_x, offset_y)

    def on_click_pressed(self, gesture, n_press, x, y):
        self.handle_click_logic(x, y)
        
        if n_press == 2:
             ann = self.drawing_area.selected_annotation
             if ann:
                 if ann.type == 'text':
                      self.open_text_editor(ann)
                 elif ann.type in ('highlight', 'underline', 'square'):
                      self._open_color_dialog()

    def create_text_annotation_at_point(self, x, y):
        pdf_x = x / self.scale
        pdf_y = y / self.scale
        
        rects = [(pdf_x, pdf_y, 150, 40)]
        
        ann = Annotation.create(type='text', page_index=self.page_number, rects=rects, color=(0,0,0,1))
        ann.content = "Type here..."
        ann.style = "standard"
        
        self.store.add(ann)
        
        self.drawing_area.selected_annotation = ann
        self.drawing_area.queue_draw()
        self.open_text_editor(ann)

    def setup_gestures_on_drawing_area(self):
        drag = Gtk.GestureDrag.new()
        drag.set_button(1)  
        drag.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)  
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        drag.connect("drag-end", self.on_drag_end)
        self.add_controller(drag) 

    def on_drag_begin(self, gesture, start_x, start_y):
        if self.drawing_area._resizing_handle:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return

        self.drawing_area.selection_start = (start_x, start_y)
        self.drawing_area.selection_end = (start_x, start_y)
        self.drawing_area.selected_region = None
        self.popover.popdown()
        
        if self.current_tool == 'area':
             self.drawing_area.temp_rect = (start_x, start_y, 0, 0)
             
        self.drawing_area.queue_draw()
        self.drawing_area.grab_focus()

    def on_drag_update(self, gesture, offset_x, offset_y):
        if not self.drawing_area.selection_start:
            return
        start_x, start_y = self.drawing_area.selection_start
        self.drawing_area.selection_end = (start_x + offset_x, start_y + offset_y)
        
        if self.current_tool == 'area':
             w = offset_x
             h = offset_y
             self.drawing_area.temp_rect = (start_x, start_y, w, h)
        else:
             self.update_selection_from_drag()
             
        self.drawing_area.queue_draw()

    def on_drag_end(self, gesture, offset_x, offset_y):
         if not self.drawing_area.selection_start:
            return
         self.on_drag_update(gesture, offset_x, offset_y)
         
         if self.current_tool in ['highlight', 'underline'] and self.drawing_area.selected_region:
             self.create_annotation_from_selection(self.current_tool)
             return
             
         if self.current_tool == 'area':
             self.create_area_annotation()
             self.drawing_area.temp_rect = None
             self.drawing_area.queue_draw()
             return

         if self.drawing_area.selected_region:
             self.show_popover_for_selection()

    def create_area_annotation(self):
        if not self.drawing_area.temp_rect: return
        
        x, y, w, h = self.drawing_area.temp_rect
        
        if w < 0:
            x += w
            w = -w
        if h < 0:
            y += h
            h = -h
            
        if w < 5 or h < 5: return 
        
        pdf_x = x / self.scale
        pdf_y = y / self.scale
        pdf_w = w / self.scale
        pdf_h = h / self.scale
        
        rects = [(pdf_x, pdf_y, pdf_w, pdf_h)]
        
        color = self.default_area_color + (0.4,)
        
        ann = Annotation.create(type='square', page_index=self.page_number, rects=rects, color=color)
        self.store.add(ann)
        
        self.drawing_area.selected_annotation = ann
        self.drawing_area.queue_draw()

    def update_selection_from_drag(self):
        if not self.drawing_area.selection_start: return
        
        x1, y1 = self.drawing_area.selection_start
        x2, y2 = self.drawing_area.selection_end
        
        rx, ry = min(x1, x2), min(y1, y2)
        rw, rh = abs(x1 - x2), abs(y1 - y2)
        
        pdf_scale = 1.0 / self.scale
        rect = Poppler.Rectangle()
        rect.x1, rect.y1 = rx * pdf_scale, ry * pdf_scale
        rect.x2, rect.y2 = (rx + rw) * pdf_scale, (ry + rh) * pdf_scale
        
        self.drawing_area.selected_region = self.page.get_selected_region(
            self.scale, Poppler.SelectionStyle.GLYPH, rect
        )

    def setup_popover(self):
        self.popover = Gtk.Popover()
        self.popover.set_parent(self.drawing_area) 
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box.set_margin_top(5)
        box.set_margin_bottom(5)
        box.set_margin_start(5)
        box.set_margin_end(5)
        
        btn_copy = Gtk.Button(icon_name="edit-copy-symbolic")
        btn_copy.set_tooltip_text("Copy Text")
        btn_copy.connect("clicked", self.on_copy_clicked)

        btn_highlight = Gtk.Button(icon_name="document-edit-symbolic") 
        btn_highlight.set_tooltip_text("Highlight")
        btn_highlight.connect("clicked", self.on_highlight_clicked)
        
        btn_underline = Gtk.Button(icon_name="format-text-underline-symbolic")
        btn_underline.set_tooltip_text("Underline")
        btn_underline.connect("clicked", self.on_underline_clicked)
        
        btn_text = Gtk.Button(icon_name="insert-text-symbolic")
        btn_text.connect("clicked", self.on_text_clicked)
        
        box.append(btn_copy)
        box.append(btn_highlight)
        box.append(btn_underline)
        box.append(btn_text)
        self.popover.set_child(box)

        popover_key = Gtk.EventControllerKey()
        popover_key.connect("key-pressed", self._on_popover_key_pressed)
        self.popover.add_controller(popover_key)

    def activate_tool(self, tool_name):
        self.current_tool = tool_name
        
        if tool_name == 'text':
            cursor = Gdk.Cursor.new_from_name("text", None)
            self.set_cursor(cursor)
        elif tool_name in ('highlight', 'underline'):
            cursor = Gdk.Cursor.new_from_name("text", None)
            self.set_cursor(cursor)
        elif tool_name == 'area':
            cursor = Gdk.Cursor.new_from_name("crosshair", None)
            self.set_cursor(cursor)
        else:
            self.set_cursor(None)

    def _open_color_dialog(self):
        ann = self.drawing_area.selected_annotation
        if not ann:
            return

        dialog = Gtk.ColorDialog()
        dialog.set_title("Pick a Color")
        dialog.set_with_alpha(False)

        r, g, b, a = ann.color
        initial = Gdk.RGBA()
        initial.red, initial.green, initial.blue, initial.alpha = r, g, b, 1.0

        window = self.get_root()
        dialog.choose_rgba(window, initial, None, self._on_color_dialog_finish)

    def _on_color_dialog_finish(self, dialog, result):
        try:
            rgba = dialog.choose_rgba_finish(result)
        except GLib.Error:
            return  

        ann = self.drawing_area.selected_annotation
        if not ann:
            return

        _, _, _, a = ann.color
        ann.color = (rgba.red, rgba.green, rgba.blue, a)

        if ann.type == 'highlight':
            self.default_highlight_color = (rgba.red, rgba.green, rgba.blue)
        elif ann.type == 'underline':
            self.default_underline_color = (rgba.red, rgba.green, rgba.blue)
        elif ann.type == 'square':
            self.default_area_color = (rgba.red, rgba.green, rgba.blue)

        self.store.is_dirty = True
        self.drawing_area.queue_draw()

    def on_copy_clicked(self, btn):
        self.copy_selected_text()
        self.popover.popdown()

    def _on_popover_key_pressed(self, controller, keyval, keycode, state):
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if ctrl and keyval == Gdk.KEY_c:
            self.copy_selected_text()
            self.popover.popdown()
            return True
        return False

    def on_highlight_clicked(self, btn):
        self.create_annotation_from_selection('highlight')
        self.popover.popdown()

    def on_underline_clicked(self, btn):
        self.create_annotation_from_selection('underline')
        self.popover.popdown()
        
    def on_text_clicked(self, btn):
        self.popover.popdown()
        self.create_text_annotation_at_selection()
        
    def create_text_annotation_at_click(self, x, y):
        pdf_x = x / self.scale
        pdf_y = y / self.scale
        
        rects = [(pdf_x, pdf_y, 100, 20)] 
        
        ann = Annotation.create(type='text', page_index=self.page_number, rects=rects)
        ann.content = "Text"
        ann.style = "standard"
        
        self.store.add(ann)
        
        self.drawing_area.selected_annotation = ann
        self.drawing_area.queue_draw()
        self.open_text_editor(ann)

    def create_text_annotation_at_selection(self):
        if not self.drawing_area.selected_region: return
        
        x, y = self.drawing_area.selection_start
        
        pdf_x = x / self.scale
        pdf_y = y / self.scale
        
        rects = [(pdf_x, pdf_y, 100, 20)] 
        
        ann = Annotation.create(type='text', page_index=self.page_number, rects=rects)
        ann.content = "New Text"
        ann.style = "standard"
        
        self.store.add(ann)
        
        # Clear selection
        self.drawing_area.selected_region = None
        self.drawing_area.queue_draw()
        self.open_text_editor(ann)

    def show_popover_for_selection(self):
        if not self.drawing_area.selected_region: return
        region = self.drawing_area.selected_region
        num_rects = region.num_rectangles()
        if num_rects == 0: return
        
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        for i in range(num_rects):
            r = region.get_rectangle(i)
            min_x = min(min_x, r.x)
            min_y = min(min_y, r.y)
            max_x = max(max_x, r.x + r.width)
            max_y = max(max_y, r.y + r.height)
            
        rect = Gdk.Rectangle()
        rect.x = int(min_x)
        rect.y = int(min_y)
        rect.width = int(max_x - min_x)
        rect.height = int(max_y - min_y)
        
        self.popover.set_pointing_to(rect)
        self.popover.popup()

    def create_annotation_from_selection(self, type):
        if not self.drawing_area.selected_region: return
        rects = []
        region = self.drawing_area.selected_region
        scale_factor = 1.0 / self.scale
        for i in range(region.num_rectangles()):
            r = region.get_rectangle(i)
            rects.append((r.x * scale_factor, r.y * scale_factor, r.width * scale_factor, r.height * scale_factor))
            
        # Use sticky defaults
        if type == 'highlight':
            color = self.default_highlight_color + (0.4,) 
        elif type == 'underline':
            color = self.default_underline_color + (1.0,) 
        else:
            color = (1, 0, 0, 1) 

        ann = Annotation.create(type=type, page_index=self.page_number, rects=rects, color=color)
        self.store.add(ann)
        
        self.drawing_area.selected_region = None
        self.drawing_area.queue_draw()
