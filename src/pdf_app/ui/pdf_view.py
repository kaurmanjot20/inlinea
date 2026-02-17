import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Adw, GLib, Gdk, GObject, Gio

from pdf_app.document.loading import load_document
from pdf_app.ui.page_view import PDFPageView
from pdf_app.document.store import AnnotationStore

class PDFView(Gtk.ScrolledWindow):
    """
    Main PDF viewer widget. Scrollable container for pages.
    Implements proper focal-point anchored zoom.
    """
    __gsignals__ = {
        'page-changed': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        'zoom-changed': (GObject.SignalFlags.RUN_FIRST, None, (float,)) 
    }

    def __init__(self, file):
        super().__init__()
        self.file = file
        self.document = None
        self.store = AnnotationStore()
        self.scale = 1.0  # Zoom level: 1.0 = 100%
        self.min_scale = 0.1 # Lower limit to fit dual pages
        self.max_scale = 4.0
        
        # Gesture state
        self._gesture_start_scale = 1.0
        self._focal_point = (0, 0)  # Focal point in viewport coords
        
        # UI Setup
        self.set_vexpand(True)
        self.set_hexpand(True)
        self.set_focusable(True) # Enable keyboard focus
        self.set_can_focus(True)
        
        # Container for pages (vertical stack)
        # Container for pages (vertical stack)
        self.page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.page_box.set_halign(Gtk.Align.CENTER)
        self.page_box.set_margin_top(20)
        self.page_box.set_margin_bottom(20)
        
        # Explicit Viewport to disable auto-scroll on focus
        self.viewport = Gtk.Viewport()
        self.viewport.set_scroll_to_focus(False) # FIX: Prevents jumping to top on click
        self.viewport.set_child(self.page_box)
        
        self.viewport.set_child(self.page_box)
        
        # Connect scroll event for tracking
        # Connect scroll event for tracking
        self.vadjustment = self.get_vadjustment() # Use ScrolledWindow's adjustment
        self.vadjustment.connect("value-changed", self.on_scroll_changed)
        
        self.set_child(self.viewport)
        self.set_child(self.viewport)
        self.pages = [] # Track page instances
        self.current_page_index = 0
        
        # Per-tab Sidebar instance
        self.sidebar = None # Will be created by window or here?
        # Let's create it later or allow window to assign it.
        # Actually safer to let Window manage it or create it on demand.
        
        # View Mode State
        self.is_dual_mode = False
        self.is_continuous = True
        
        # Key Controller for Navigation
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_ctrl)
        
        # Pinch-to-Zoom Gesture
        zoom_gesture = Gtk.GestureZoom()
        zoom_gesture.connect("begin", self.on_zoom_begin)
        zoom_gesture.connect("scale-changed", self.on_zoom_scale_changed)
        zoom_gesture.connect("end", self.on_zoom_end)
        self.add_controller(zoom_gesture)
        
        # Scroll event for Ctrl+Scroll zoom
        scroll_controller = Gtk.EventControllerScroll()
        scroll_controller.set_flags(Gtk.EventControllerScrollFlags.VERTICAL)
        # scroll_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE) # Reverted
        scroll_controller.connect("scroll", self.on_scroll)
        self.add_controller(scroll_controller)
        
        # Click to focus
        click_gesture = Gtk.GestureClick()
        click_gesture.connect("pressed", self.on_click_focus)
        self.add_controller(click_gesture)

        # Load document
        self.load_pdf()

    def load_pdf(self):
        try:
            file_path = self.file.get_path()
            
            # 1. Load annotations from original PDF into store
            self.store.load_from_pdf(file_path)
            
            # 2. Create a temp copy with our annotations stripped
            #    so Poppler doesn't render them (our overlay draws them)
            from pdf_app.document.pdf_storage import create_render_copy
            self._render_copy_path = create_render_copy(file_path)
            
            # 3. Load the clean temp copy into Poppler for rendering
            render_file = Gio.File.new_for_path(self._render_copy_path)
            self.document = load_document(render_file)
            if not self.document:
                self.show_error("Failed to load PDF.")
                return
            
            n_pages = self.document.get_n_pages()
            print(f"Loaded PDF with {n_pages} pages.")

            # Render pages
            for i in range(n_pages):
                page = self.document.get_page(i)
                page_view = PDFPageView(page, i, self.store)
                self.pages.append(page_view)
                self.page_box.append(page_view)

            # Set initial zoom to fit-to-width after layout
            GLib.idle_add(self._fit_to_width)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.show_error(str(e))

    def _fit_to_width(self):
        """Set initial scale to fit page width in viewport."""
        viewport_width = self.get_allocated_width()
        if viewport_width <= 1 or not self.document:
            return False  # Not ready yet
        
        # Get first page width
        first_page = self.document.get_page(0)
        page_width, _ = first_page.get_size()
        
        # Calculate fit-to-width scale (with small margin)
        fit_scale = (viewport_width - 40) / page_width  # 20px margin each side
        fit_scale = max(self.min_scale, min(self.max_scale, fit_scale))
        
        target_index = self.current_page_index
        
        self.scale = fit_scale
        self._gesture_start_scale = fit_scale
        self._apply_zoom()
        
        # Keep focus
        GLib.idle_add(self.scroll_to_page, target_index)
        
        return False

    def set_tool(self, tool_name):
        """Propagate tool selection to all pages."""
        self.tool_name = tool_name
        for page in self.pages:
            page.activate_tool(tool_name)

    def handle_escape(self):
        """Global Escape Logic."""
        # 1. Reset Tool
        self.set_tool(None)
        
        # 2. Clear Selection & Close Popovers
        for page in self.pages:
            if page.drawing_area.selected_annotation:
                 page.drawing_area.selected_annotation = None
                 page.drawing_area.queue_draw()
            if hasattr(page, 'editor_popover') and page.editor_popover:
                 page.editor_popover.popdown()

    def set_text_mode(self, enabled):
        child = self.page_box.get_first_child()
        while child:
            if isinstance(child, PDFPageView):
                child.set_text_mode(enabled)
            child = child.get_next_sibling()
            
        if enabled:
            self.page_box.grab_focus()

    def reload_page(self, page_index: int):
        """Reloads widgets for a specific page after undo."""
        child = self.page_box.get_first_child()
        while child:
            if isinstance(child, PDFPageView) and child.page_number == page_index:
                # child.load_widgets() # REMOVED: Legacy
                child.drawing_area.queue_draw()
                break
            child = child.get_next_sibling()

    def show_error(self, message):
        label = Gtk.Label(label=f"Error: {message}")
        self.page_box.append(label)

    # ========== ZOOM HANDLERS ==========

    def on_click_focus(self, gesture, n_press, x, y):
        self.grab_focus()

    def on_zoom_begin(self, gesture, sequence):
        """Store starting state for pinch gesture."""
        self._gesture_start_scale = self.scale
        # Get gesture center point as focal point
        _, x, y = gesture.get_bounding_box_center()
        self._focal_point = (x, y)

    def on_zoom_scale_changed(self, gesture, scale):
        """Handle pinch-to-zoom gesture - continuous, proportional."""
        new_scale = self._gesture_start_scale * scale
        new_scale = max(self.min_scale, min(self.max_scale, new_scale))
        
        if abs(new_scale - self.scale) < 0.001:
            return
        
        self._zoom_around_focal(new_scale, self._focal_point)

    def on_zoom_end(self, gesture, sequence):
        """Pinch gesture ended."""
        self._gesture_start_scale = self.scale

    def on_scroll(self, controller, dx, dy):
        """Handle Ctrl+Scroll for zoom."""
        state = controller.get_current_event_state()
        if state & Gdk.ModifierType.CONTROL_MASK:
            # Get cursor position as focal point
            event = controller.get_current_event()
            if event:
                x, y = event.get_position()
                focal = (x, y)
            else:
                # Fallback to viewport center
                focal = (self.get_allocated_width() / 2, self.get_allocated_height() / 2)
            
            # Proportional zoom (10% per scroll tick)
            factor = 1.1 if dy < 0 else 1 / 1.1
            new_scale = self.scale * factor
            new_scale = max(self.min_scale, min(self.max_scale, new_scale))
            
            self._zoom_around_focal(new_scale, focal)
            return True  # Event handled
        return False  # Let scrolling happen normally

    def _zoom_around_focal(self, new_scale, focal):
        """Zoom around a focal point, adjusting scroll to keep it fixed."""
        if abs(new_scale - self.scale) < 0.001:
            return
        
        # Get current scroll position
        hadj = self.get_hadjustment()
        vadj = self.get_vadjustment()
        old_scroll_x = hadj.get_value()
        old_scroll_y = vadj.get_value()
        
        # Calculate the document position of the focal point
        doc_x = old_scroll_x + focal[0]
        doc_y = old_scroll_y + focal[1]
        
        # Calculate scale ratio
        ratio = new_scale / self.scale
        
        # Apply new scale
        old_scale = self.scale
        self.scale = new_scale
        self._apply_zoom()
        
        # Calculate new document position of focal point
        new_doc_x = doc_x * ratio
        new_doc_y = doc_y * ratio
        
        # Adjust scroll to keep focal point stationary
        new_scroll_x = new_doc_x - focal[0]
        new_scroll_y = new_doc_y - focal[1]
        
        # Apply new scroll (clamp to valid range)
        hadj.set_value(max(0, new_scroll_x))
        vadj.set_value(max(0, new_scroll_y))

    def _apply_zoom(self):
        """Apply current scale to all page views, traversing rows if needed."""
        child = self.page_box.get_first_child()
        while child:
            if isinstance(child, PDFPageView):
                child.update_scale(self.scale)
            elif isinstance(child, Gtk.Box):
                # This affects Layout Rows in Dual Mode
                row_child = child.get_first_child()
                while row_child:
                    if isinstance(row_child, PDFPageView):
                        row_child.update_scale(self.scale)
                    row_child = row_child.get_next_sibling()
            child = child.get_next_sibling()
            
        self.emit('zoom-changed', self.scale)

    def on_scroll_changed(self, adjustment):
        """Track current page based on scroll position."""
        vp_h = self.viewport.get_allocated_height()
        scroll_y = adjustment.get_value()
        center_y = scroll_y + (vp_h / 2)
        
        found_index = -1
        min_dist = float('inf')
        
        for i, page_view in enumerate(self.pages):
           target_widget = page_view
           parent = page_view.get_parent()
           
           # In Dual Mode, the direct child of page_box is the Row Box
           if self.is_dual_mode and isinstance(parent, Gtk.Box) and parent != self.page_box:
               target_widget = parent
               
           # Use translate_coordinates for absolute position relative to page_box
           try:
               res = target_widget.translate_coordinates(self.page_box, 0, 0)
               if res:
                   tx, ty = res
                   theight = target_widget.get_allocated_height()
                   
                   widget_center_y = ty + (theight / 2)
                   dist = abs(center_y - widget_center_y)
                   
                   if dist < min_dist:
                       min_dist = dist
                       found_index = i
           except Exception:
               continue
               
        if found_index != -1 and found_index != self.current_page_index:
            self.current_page_index = found_index
            self.emit('page-changed', found_index)

    def scroll_to_page(self, index):
        """Scroll viewport to specific page index."""
        if index < 0 or index >= len(self.pages):
            return
            
        target_page = self.pages[index]
        parent = target_page.get_parent()
        
        # If dual mode, scroll to row (parent Box), not page directly
        target_widget = parent if self.is_dual_mode and isinstance(parent, Gtk.Box) and parent != self.page_box else target_page
        
        # We need the y-coordinate relative to the page_box (scrolled content)
        # origin_y = target_widget.get_allocation().y 
        # Better: Translate coordinates to be sure
        
        try:
             # Translate (0,0) of target_widget to page_box
             _, y = target_widget.translate_coordinates(self.page_box, 0, 0)
             alloc = target_widget.get_allocation() # Still need for check
             alloc.y = y 
        except:
             alloc = target_widget.get_allocation()
        
        # If not allocated yet (e.g. initial load), try idle
        if alloc.height == 0:
            GLib.idle_add(self.scroll_to_page, index)
            return

        self.vadjustment.set_value(alloc.y)
        self.current_page_index = index

    # ========== PUBLIC ZOOM METHODS ==========

    def zoom_in(self):
        """Zoom in by 10%, centered on viewport."""
        focal = (self.get_allocated_width() / 2, self.get_allocated_height() / 2)
        new_scale = min(self.max_scale, self.scale * 1.1)
        self._zoom_around_focal(new_scale, focal)

    def zoom_out(self):
        """Zoom out by 10%, centered on viewport."""
        focal = (self.get_allocated_width() / 2, self.get_allocated_height() / 2)
        new_scale = max(self.min_scale, self.scale / 1.1)
        self._zoom_around_focal(new_scale, focal)

    def zoom_reset(self):
        """Reset to fit-to-width."""
        if self.is_dual_mode:
            self._fit_two_pages()
        else:
            self._fit_to_width()

    def _fit_two_pages(self):
        """Fit two pages side-by-side in viewport (Contain)."""
        viewport_width = self.get_allocated_width()
        viewport_height = self.get_allocated_height()
        if viewport_width <= 1 or not self.document: return False
        
        # Get dimensions of one page (assuming uniform)
        first_page = self.document.get_page(0)
        page_width, page_height = first_page.get_size()
        
        # Target Content Width = 2*page_width + spacing + margins
        # Target Content Height = page_height + margins
        
        target_w = (2 * page_width) + 20 
        target_h = page_height + 20
        
        scale_x = (viewport_width - 40) / target_w
        scale_y = (viewport_height - 40) / target_h
        
        fit_scale = min(scale_x, scale_y)
        fit_scale = max(self.min_scale, min(self.max_scale, fit_scale))
        
        # Capture current page index BEFORE applying zoom/layout changes
        # This prevents scroll events during resize from updating it to the wrong value (e.g. last page)
        target_index = self.current_page_index
        
        self.scale = fit_scale
        self._apply_zoom()
        
        # Restore focus to current page (async to allow layout update)
        GLib.idle_add(self.scroll_to_page, target_index)
        
        return False





    # ========== VIEW MODES & LAYOUT ==========
    
    def set_dual_page_mode(self, enabled):
        if self.is_dual_mode == enabled:
            return
        self.is_dual_mode = enabled
        self.relayout_pages()
        
        if enabled:
            # Auto-fit two pages - Use timeout to allow layout to settle
            GLib.timeout_add(100, self._fit_two_pages)
        
    def set_continuous_scroll(self, enabled):
        if self.is_continuous == enabled:
            return
        self.is_continuous = enabled
        # self.relayout_pages() # REMOVED: No layout change needed
        
        # If switching to Paged, snap to current
        if not enabled:
            self.scroll_to_page(self.current_page_index)

    def relayout_pages(self):
        """Rebuilds the page_box layout based on current modes."""
        # 1. Safely detach all pages first to prevent destruction
        for page in self.pages:
            parent = page.get_parent()
            if parent:
                parent.remove(page)
                
        # 2. Clear container (now contains only empty rows if any)
        child = self.page_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.page_box.remove(child)
            child = next_child
            
        # 3. Re-add pages based on mode
        if self.is_dual_mode:
            # Group items: (0,1), (2,3), ...
            for i in range(0, len(self.pages), 2):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20) # Increased spacing
                row.set_halign(Gtk.Align.CENTER)
                
                row.set_visible(True) # Always visible
                
                # Add pages to row
                p1 = self.pages[i]
                row.append(p1)
                
                if i + 1 < len(self.pages):
                    p2 = self.pages[i+1]
                    row.append(p2)
                    
                self.page_box.append(row)
        else:
            # Single Mode
            for i, page in enumerate(self.pages):
                page.set_visible(True) # Always visible
                self.page_box.append(page)

    # ========== KEYBOARD & SCROLL ==========

    def on_key_pressed(self, controller, keyval, keycode, state):
        # Handle Arrows, PageUp, PageDown
        # Logic depends on mode
        is_ctrl = state & Gdk.ModifierType.CONTROL_MASK
        
        if keyval in [Gdk.KEY_Up, Gdk.KEY_Left]:
            self.navigate_page(-1)
            return True
        elif keyval in [Gdk.KEY_Down, Gdk.KEY_Right]:
            self.navigate_page(1)
            return True
        elif keyval == Gdk.KEY_Page_Up:
            self.navigate_page(-1 if not self.is_dual_mode else -2)
            return True
        elif keyval == Gdk.KEY_Page_Down:
            self.navigate_page(1 if not self.is_dual_mode else 2)
            return True
        return False

    def navigate_page(self, delta):
        new_index = self.current_page_index + delta
        new_index = max(0, min(len(self.pages) - 1, new_index))
        
        # Always scroll, even if index is same (to snap back if user manual scrolled)
        self.scroll_to_page(new_index)

    def on_scroll(self, controller, dx, dy):
        """Handle Ctrl+Scroll for zoom AND Paged Mode navigation."""
        state = controller.get_current_event_state()
        
        # 1. Zoom Logic (Ctrl+Scroll)
        if state & Gdk.ModifierType.CONTROL_MASK:
            # Get cursor position as focal point
            event = controller.get_current_event()
            if event:
                x, y = event.get_position()
                focal = (x, y)
            else:
                focal = (self.get_allocated_width() / 2, self.get_allocated_height() / 2)
            
            # Proportional zoom (10% per scroll tick)
            factor = 1.1 if dy < 0 else 1 / 1.1
            new_scale = self.scale * factor
            new_scale = max(self.min_scale, min(self.max_scale, new_scale))
            
            self._zoom_around_focal(new_scale, focal)
            return True  # Event handled

        return False

