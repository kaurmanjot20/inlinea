import cairo
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Poppler', '0.18')
from gi.repository import Gtk, Gdk, Poppler

from pdf_app.document.render import render_page_to_surface
from pdf_app.document.store import Annotation, AnnotationStore
from pdf_app.ui.text_dialog import TextAnnotationDialog

from pdf_app.ui.pdf_drawing_area import PDFDrawingArea
from pdf_app.ui.text_editor import TextEditorPopover

class PDFPageView(Gtk.Overlay):
    """
    Composite Widget:
    - Base: PDFDrawingArea (PDF + Highlights + Text)
    """


    def __init__(self, page, page_number, store: AnnotationStore):
        super().__init__()
        self.page = page
        self.page_number = page_number
        self.store = store
        self.scale = 1.0
        self.text_mode = False # Legacy flag, check if needed
        self.current_tool = None # 'highlight', 'underline', 'text'
        
        # 1. Background (PDF Render)
        self.drawing_area = PDFDrawingArea(page, self.scale, store)
        # self.drawing_area.set_hexpand(True) # REMOVED: Fix zoom/fit issues
        # self.drawing_area.set_vexpand(True)
        self.set_child(self.drawing_area)
        
        
        # Initial sizing
        self.update_size()
        
        # Setup Gestures (Drag for text selection)
        self.setup_gestures_on_drawing_area()
        
        # 1. Resize/Drag gesture (Must be first)
        self.resize_gesture = Gtk.GestureDrag()
        self.resize_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.resize_gesture.set_button(1) # Left click only for resize
        self.resize_gesture.connect("drag-begin", self.on_resize_drag_begin)
        self.resize_gesture.connect("drag-update", self.on_resize_drag_update)
        self.resize_gesture.connect("drag-end", self.on_resize_drag_end)
        self.add_controller(self.resize_gesture)

        # 2. Click gesture
        click_gesture = Gtk.GestureClick()
        click_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click_gesture.set_button(0)
        click_gesture.connect("pressed", self.on_click_pressed)
        self.add_controller(click_gesture)
        
        # Group gestures (Allow simultaneous recognition)
        click_gesture.group(self.resize_gesture)

        # Context Menu

        # Context Menu
        self.setup_popover()
        self.editor_popover = None

        # Key Controller (Escape to exit text mode)
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)


    def set_text_mode(self, enabled):
        # Legacy: mapped to 'text' tool now
        if enabled:
            self.activate_tool('text')
        else:
            self.activate_tool(None)

    def activate_tool(self, tool_name):
        """Available tools: 'highlight', 'underline', 'text', None"""
        self.current_tool = tool_name
        
        if tool_name == 'text':
            cursor = Gdk.Cursor.new_from_name("text", None)
            self.set_cursor(cursor)
            # Clear selection
            self.drawing_area.selected_region = None
            self.popover.popdown()
            self.drawing_area.queue_draw()
            
        elif tool_name in ['highlight', 'underline']:
            cursor = Gdk.Cursor.new_from_name("text", None) # Text selection cursor
            self.set_cursor(cursor)
            
        else:
            self.set_cursor(None)

    def update_size(self):
        w, h = self.page.get_size()
        scaled_w = int(w * self.scale)
        scaled_h = int(h * self.scale)
        
        # Resize DrawingArea (it handles its own content size request)
        self.drawing_area.set_content_width(scaled_w)
        self.drawing_area.set_content_height(scaled_h)
        self.drawing_area.update_scale(self.scale)

    def update_scale(self, new_scale):
        """Update zoom scale and refresh the view."""
        self.scale = new_scale
        self.update_size()

    def preview_scale(self, new_scale):
        """Quick preview during zoom gesture - resize container without re-rendering surfaces."""
        w, h = self.page.get_size()
        scaled_w = int(w * new_scale)
        scaled_h = int(h * new_scale)
        self.drawing_area.set_content_width(scaled_w)
        self.drawing_area.set_content_height(scaled_h)
        # Don't invalidate surface - just queue redraw with existing surface scaled
        self.drawing_area.queue_draw()

    def on_annotation_update(self, ann):
        # Mark dirty (save is explicit via Save As)
        self.store.is_dirty = True

    def on_click_pressed(self, gesture, n_press, x, y):
        # Tool-First: Add Text
        if self.current_tool == 'text':
            self.create_text_annotation_at_click(x, y)
            # self.activate_tool(None) # REMOVED: Keep tool active (Sticky)
            return

        # We clicked background or annotation area.
        self.drawing_area.grab_focus()
        self.popover.popdown()
        
        # Hit Test for Existing Annotations (Highlights/Underlines/Text)
        # Convert click to PDF coordinates
        pdf_x = x / self.scale
        pdf_y = y / self.scale
        # print(f"DEBUG: Click at widget ({x:.2f}, {y:.2f}) -> PDF ({pdf_x:.2f}, {pdf_y:.2f})")
        
        hit_ann = self.store.find_annotation_at(self.page_number, pdf_x, pdf_y)
        
        if hit_ann:
            self.drawing_area.selected_annotation = hit_ann
            self.drawing_area.selected_region = None # Clear text selection
            self.drawing_area.queue_draw()
            
            # If Double Click and it's TEXT, open editor
            if n_press == 2 and hit_ann.type == 'text':
                self.open_text_editor(hit_ann)
                
        else:
            # Deselect if clicked empty space... UNLESS we clicked a handle!
            if self.drawing_area.selected_annotation:
                if self.drawing_area.is_point_on_handle(x, y):
                    return
                
                self.drawing_area.selected_annotation = None
                self.drawing_area.queue_draw()

    def open_text_editor(self, ann):
        # Close existing if open
        if self.editor_popover:
            self.editor_popover.popdown()
            # self.editor_popover.unparent() # Gtk4 popover lifecycle management
            # Actually just creating a new one might leave the old one floating if not destroyed?
            # Assigning new variable releases Python ref, but Gtk widget hierarchy?
            # set_parent was used.
            self.editor_popover.unparent()
            self.editor_popover = None
            
        # Attach to SELF (Overlay) for correct parenting
        self.editor_popover = TextEditorPopover(self, ann, self.on_text_updated)
        self.editor_popover.update_position(self.scale)
        self.editor_popover.popup()
        
    def on_text_updated(self, ann):
        self.drawing_area.queue_draw()
        self.store.is_dirty = True

    def on_key_pressed(self, controller, keyval, keycode, state):
        # Handle Escape to exit text mode
        if keyval == Gdk.KEY_Escape:
            # 1. Reset Tool if active
            if self.current_tool:
                self.activate_tool(None)
                # SYNC UI
                root = self.get_native()
                if hasattr(root, 'update_ribbon_tool_state'):
                    root.update_ribbon_tool_state(None)
                return True
                
            # 2. Clear Selection if exists
            if self.drawing_area.selected_annotation:
                self.drawing_area.selected_annotation = None
                self.drawing_area.queue_draw()
                return True
                
        # Handle Delete for selected annotation
        if keyval == Gdk.KEY_Delete or keyval == Gdk.KEY_BackSpace:
            if self.drawing_area.selected_annotation:
                ann = self.drawing_area.selected_annotation
                self.store.remove(ann.id)
                self.drawing_area.selected_annotation = None
                self.drawing_area.queue_draw()
                return True
                
        return False
    def reposition_widgets(self):
        # We need to iterate children of Fixed and update positions if Scale changed
        self.load_widgets() # Simplify by just reloading

    def on_annotation_update(self, ann):
        # Mark dirty (save is explicit via Save As)
        self.store.is_dirty = True

    def on_resize_drag_begin(self, gesture, start_x, start_y):
        """Handle highlight resize drag (intercepted from Overlay)."""
        # Delegate to DrawingArea
        handled = self.drawing_area.handle_drag_begin(start_x, start_y)
        if handled:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        else:
            self.handle_click_logic(start_x, start_y)
            gesture.set_state(Gtk.EventSequenceState.DENIED)

    def handle_click_logic(self, x, y):
        """Unified click logic."""
        
        # 1. Tool Creation (Text)
        if self.current_tool == 'text':
            self.create_text_annotation_at_click(x, y)
            return

        # 2. Hit Test
        self.popover.popdown()
        hit_ann = self.store.find_annotation_at(self.page_number, x/self.scale, y/self.scale)
        
        if hit_ann:
            self.drawing_area.selected_annotation = hit_ann
            self.drawing_area.selected_region = None
            self.drawing_area.queue_draw()
        else:
            # Deselect unless on handle
            if self.drawing_area.selected_annotation and not self.drawing_area.is_point_on_handle(x, y):
                 self.drawing_area.selected_annotation = None
                 self.drawing_area.queue_draw()

    def on_resize_drag_update(self, gesture, offset_x, offset_y):
        self.drawing_area.handle_drag_update(offset_x, offset_y)

    def on_resize_drag_end(self, gesture, offset_x, offset_y):
        self.drawing_area.handle_drag_end(offset_x, offset_y)

    def on_click_pressed(self, gesture, n_press, x, y):
        # Only grab focus if we clicked the background
        picked = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        if picked == self.drawing_area:
             self.drawing_area.grab_focus()
        
        self.handle_click_logic(x, y)
        
        # Double Click
        if n_press == 2:
             ann = self.drawing_area.selected_annotation
             if ann and ann.type == 'text':
                  self.open_text_editor(ann)

    def on_click_released(self, gesture, n_press, x, y):
        if self.text_mode:
            self.create_text_annotation_at_point(x, y)

    def create_text_annotation_at_point(self, x, y):
        # Convert to PDF
        pdf_x = x / self.scale
        pdf_y = y / self.scale
        
        rects = [(pdf_x, pdf_y, 150, 40)]
        
        ann = Annotation.create(type='text', page_index=self.page_number, rects=rects, color=(0,0,0,1))
        ann.content = "Type here..."
        ann.style = "standard"
        
        self.store.add(ann)
        widget = self.add_text_widget(ann)
        
        # Focus and Select All
        widget.text_view.grab_focus()
        buffer = widget.text_view.get_buffer()
        start, end = buffer.get_bounds()
        buffer.select_range(start, end)

    # ... Forwarding Selection logic to DrawingArea ...
    def setup_gestures_on_drawing_area(self):
        # Drag for selection
        drag = Gtk.GestureDrag.new()
        drag.set_button(1)  # Left mouse button only
        drag.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)  # Let clicks fire first
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        drag.connect("drag-end", self.on_drag_end)
        self.add_controller(drag) # Attach to Overlay (self), NOT drawing_area!

    # ... gestures handlers need to update drawing_area.selection states ...
    def on_drag_begin(self, gesture, start_x, start_y):
        if self.text_mode:
            return
            
        self.drawing_area.grab_focus() # Ensure focus is on drawing area for selection

    def on_drag_begin(self, gesture, start_x, start_y):
        # Check if we are already handling a move/resize in DrawingArea (priority)
        if self.drawing_area._resizing_handle:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return

        self.drawing_area.selection_start = (start_x, start_y)
        self.drawing_area.selection_end = (start_x, start_y)
        self.drawing_area.selected_region = None
        self.popover.popdown()
        self.drawing_area.queue_draw()

    def on_drag_update(self, gesture, offset_x, offset_y):
        if not self.drawing_area.selection_start:
            return
        start_x, start_y = self.drawing_area.selection_start
        self.drawing_area.selection_end = (start_x + offset_x, start_y + offset_y)
        self.update_selection_from_drag()
        self.drawing_area.queue_draw()

    def on_drag_end(self, gesture, offset_x, offset_y):
         if not self.drawing_area.selection_start:
            return
         self.on_drag_update(gesture, offset_x, offset_y)
         
         # Tool-First: Create Annotation immediately
         if self.current_tool in ['highlight', 'underline'] and self.drawing_area.selected_region:
             self.create_annotation_from_selection(self.current_tool)
             # self.activate_tool(None) # Remvoved: Sticky Tools
             return
             
         if self.drawing_area.selected_region:
             self.show_popover_for_selection()

    def update_selection_from_drag(self):
        # Needs logic moved here or in DrawingArea. 
        # Let's keep logic here but access drawing_area state.
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

    # Popover needs modification to use self.drawing_area as pointing target or similar
    def setup_popover(self):
        self.popover = Gtk.Popover()
        self.popover.set_parent(self.drawing_area) # Attach to DrawingArea
        # ... buttons setup ...
        # (Same as before)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box.set_margin_top(5)
        box.set_margin_bottom(5)
        box.set_margin_start(5)
        box.set_margin_end(5)
        
        btn_highlight = Gtk.Button(icon_name="format-text-bold-symbolic") 
        btn_highlight.set_tooltip_text("Highlight")
        btn_highlight.connect("clicked", self.on_highlight_clicked)
        
        btn_underline = Gtk.Button(icon_name="format-text-underline-symbolic")
        btn_underline.set_tooltip_text("Underline")
        btn_underline.connect("clicked", self.on_underline_clicked)
        
        # Keeping context menu insert text optional
        btn_text = Gtk.Button(icon_name="document-edit-symbolic")
        btn_text.connect("clicked", self.on_text_clicked)
        
        box.append(btn_highlight)
        box.append(btn_underline)
        box.append(btn_text)
        self.popover.set_child(box)

    def activate_tool(self, tool_name):
        """Set the active tool (text, highlight, underline)."""
        self.current_tool = tool_name
        
        # Update cursor
        if tool_name == 'text':
            cursor = Gdk.Cursor.new_from_name("text", None)
            self.set_cursor(cursor)
        elif tool_name in ('highlight', 'underline'):
            cursor = Gdk.Cursor.new_from_name("crosshair", None)
            self.set_cursor(cursor)
        else:
            self.set_cursor(None)

    def on_highlight_clicked(self, btn):
        self.create_annotation_from_selection('highlight')
        self.popover.popdown()

    def on_underline_clicked(self, btn):
        self.create_annotation_from_selection('underline')
        self.popover.popdown()
        
    def on_text_clicked(self, btn):
        # Convert selection to text box
        self.popover.popdown()
        self.create_text_annotation_at_selection()
        
    def create_text_annotation_at_click(self, x, y):
        # Convert to PDF
        pdf_x = x / self.scale
        pdf_y = y / self.scale
        
        # Default size
        rects = [(pdf_x, pdf_y, 100, 20)] 
        
        ann = Annotation.create(type='text', page_index=self.page_number, rects=rects)
        ann.content = "Text"
        ann.style = "standard"
        
        self.store.add(ann)
        
        # Select and edit
        self.drawing_area.selected_annotation = ann
        self.drawing_area.queue_draw()
        self.open_text_editor(ann)

    def create_text_annotation_at_selection(self):
        if not self.drawing_area.selected_region: return
        
        # Get position of selection start
        x, y = self.drawing_area.selection_start
        
        # Convert to PDF
        pdf_x = x / self.scale
        pdf_y = y / self.scale
        
        rects = [(pdf_x, pdf_y, 100, 20)] # Default size, will resize
        
        ann = Annotation.create(type='text', page_index=self.page_number, rects=rects)
        ann.content = "New Text"
        ann.style = "standard"
        
        self.store.add(ann)
        # self.add_text_widget(ann) # REMOVED
        
        # Clear selection
        self.drawing_area.selected_region = None
        self.drawing_area.queue_draw()
        self.open_text_editor(ann)

    def show_popover_for_selection(self):
        # ... implementation adapting to drawing_area ...
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
        # ... similar to before but updating drawing_area ...
        if not self.drawing_area.selected_region: return
        rects = []
        region = self.drawing_area.selected_region
        scale_factor = 1.0 / self.scale
        for i in range(region.num_rectangles()):
            r = region.get_rectangle(i)
            rects.append((r.x * scale_factor, r.y * scale_factor, r.width * scale_factor, r.height * scale_factor))
            
        color = (1, 1, 0, 0.4) if type == 'highlight' else (1, 0, 0, 1)
        ann = Annotation.create(type=type, page_index=self.page_number, rects=rects, color=color)
        self.store.add(ann)
        
        self.drawing_area.selected_region = None
        self.drawing_area.queue_draw()
