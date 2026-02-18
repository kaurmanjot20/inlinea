import cairo
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, Pango, PangoCairo

from pdf_app.document.render import render_page_to_surface

class PDFDrawingArea(Gtk.DrawingArea):
    def __init__(self, page, scale, store):
        super().__init__()
        self.page = page
        self.scale = scale
        self.store = store
        self.surface = None
        
        self.set_focusable(True) # Allow focus to be grabbed
        self.set_can_target(True) # Allow events (focus)
        self.set_draw_func(self.on_draw)
        
        # Selection State
        self.selection_start = None # (x, y) widget coords
        self.selection_end = None
        self.selected_region = None # Poppler.Region
        self.temp_rect = None # (x, y, w, h) for area creation
        
        self.selected_annotation = None # For Highlights/Underlines
        
        # Handle Resize State
        self._resizing_handle = None # 'start', 'end', 'move', 'nw', 'ne', 'sw', 'se'
        self._resize_start_pos = None  # Initial drag position
        self.handle_radius = 12  # Larger radius for easier clicking
        self._old_rects = None  # Store original rects for undo
        
        self.queue_draw()
        
    def update_scale(self, scale):
        self.scale = scale
        self.surface = None
        self.queue_draw()

  
    def get_handle_positions(self):
        ann = self.selected_annotation
        if not ann or not ann.rects:
            return None, None
            
        if ann.type == 'text':
            return None, None
            
        if ann.type == 'square':
            if not ann.rects: return None, None
            r = ann.rects[0]
            x, y, w, h = r
            
            # TL
            start_x = x * self.scale
            start_y = y * self.scale
            
            # BR
            end_x = (x + w) * self.scale
            end_y = (y + h) * self.scale
            
            return (start_x, start_y), (end_x, end_y)
        
        first_rect = ann.rects[0]
        last_rect = ann.rects[-1]
        
        # Start handle: Top-left of first rect (with offset for circle)
        start_x = first_rect[0] * self.scale
        start_y = first_rect[1] * self.scale - self.handle_radius
        
        # End handle: Bottom-right of last rect (with offset)
        end_x = (last_rect[0] + last_rect[2]) * self.scale
        end_y = (last_rect[1] + last_rect[3]) * self.scale + self.handle_radius
        
        return (start_x, start_y), (end_x, end_y)

    def is_point_on_handle(self, x, y):
        start, end = self.get_handle_positions()
        if not start:
            return False
            
        threshold = self.handle_radius * 2
        dist_start = ((x - start[0])**2 + (y - start[1])**2)**0.5
        dist_end = ((x - end[0])**2 + (y - end[1])**2)**0.5
        
        return dist_start < threshold or dist_end < threshold

    def _is_point_on_square_handle(self, x, y):
         ann = self.selected_annotation
         if not ann or ann.type != 'square' or not ann.rects: return False
         
         r = ann.rects[0]
         rect_x = r[0] * self.scale
         rect_y = r[1] * self.scale
         rect_w = r[2] * self.scale
         rect_h = r[3] * self.scale
         
         threshold = 10 # 5 radius * 2
         
         # Check 4 corners
         corners = [
             (rect_x, rect_y),
             (rect_x + rect_w, rect_y),
             (rect_x, rect_y + rect_h),
             (rect_x + rect_w, rect_y + rect_h)
         ]
         
         for cx, cy in corners:
             if ((x - cx)**2 + (y - cy)**2)**0.5 < threshold:
                 return True
         return False



    def handle_drag_begin(self, start_x, start_y):
        if not self.selected_annotation:
            return False
        
        ann = self.selected_annotation
        start_handle, end_handle = self.get_handle_positions()
        threshold = self.handle_radius * 2

        # Check interaction with HANDLES
        if start_handle:
            dist_start = ((start_x - start_handle[0])**2 + (start_y - start_handle[1])**2)**0.5
            dist_end = ((start_x - end_handle[0])**2 + (start_y - end_handle[1])**2)**0.5
            
            if dist_start < threshold:
                self._resizing_handle = 'start'
                self._resize_start_pos = (start_x, start_y)
                self._old_rects = list(self.selected_annotation.rects) if self.selected_annotation.rects else []
                if self.selected_annotation.rects:
                    last_r = self.selected_annotation.rects[-1]
                    self._anchor_pdf = (last_r[0] + last_r[2], last_r[1] + last_r[3])
                cursor = Gdk.Cursor.new_from_name("w-resize", None)
                self.set_cursor(cursor)
                return True
    
            elif dist_end < threshold:
                self._resizing_handle = 'end'
                self._resize_start_pos = (start_x, start_y)
                self._old_rects = list(self.selected_annotation.rects) if self.selected_annotation.rects else []
                if self.selected_annotation.rects:
                    first_r = self.selected_annotation.rects[0]
                    self._anchor_pdf = (first_r[0], first_r[1])
                cursor = Gdk.Cursor.new_from_name("e-resize", None)
                self.set_cursor(cursor)
                return True
            
            # Check interaction with SQUARE HANDLES (4 corners)
            if ann.type == 'square':
                 # Recheck all 4 corners
                 r = ann.rects[0]
                 x = r[0] * self.scale
                 y = r[1] * self.scale
                 w = r[2] * self.scale
                 h = r[3] * self.scale
                 
                 # TL, TR, BL, BR
                 handles = [
                     ('nw', x, y),
                     ('ne', x + w, y),
                     ('sw', x, y + h),
                     ('se', x + w, y + h)
                 ]
                 
                 for name, hx, hy in handles:
                     dist = ((start_x - hx)**2 + (start_y - hy)**2)**0.5
                     if dist < threshold:
                         self._resizing_handle = name
                         self._resize_start_pos = (start_x, start_y)
                         self._old_rects = list(ann.rects)
                         # Anchor is OPPOSITE corner
                         if name == 'nw': self._anchor_pdf = (r[0]+r[2], r[1]+r[3])
                         elif name == 'ne': self._anchor_pdf = (r[0], r[1]+r[3])
                         elif name == 'sw': self._anchor_pdf = (r[0]+r[2], r[1])
                         elif name == 'se': self._anchor_pdf = (r[0], r[1])
                         
                         cursor_name = f"{name}-resize"
                         cursor = Gdk.Cursor.new_from_name(cursor_name, None)
                         self.set_cursor(cursor)
                         return True
            
        # Check for MOVE (drag body)
        pdf_x = start_x / self.scale
        pdf_y = start_y / self.scale
        # Check if point inside any rect
        for r in ann.rects:
            # r is (x, y, w, h)
            if r[0] <= pdf_x <= r[0] + r[2] and r[1] <= pdf_y <= r[1] + r[3]:
                self._resizing_handle = 'move'
                self._resize_start_pos = (start_x, start_y)
                self._old_rects = list(ann.rects) if ann.rects else []
                cursor = Gdk.Cursor.new_from_name("move", None)
                self.set_cursor(cursor)
                return True
                
        return False
            
    def handle_drag_update(self, offset_x, offset_y):
        if not self._resizing_handle or not self.selected_annotation:
            return
        
        # Current cursor position in widget coords
        start_x, start_y = self._resize_start_pos
        cur_x = start_x + offset_x
        cur_y = start_y + offset_y
        
        # Convert to PDF coords
        pdf_x = cur_x / self.scale
        pdf_y = cur_y / self.scale
        
        # HANDLE MOVE
        if self._resizing_handle == 'move':
            # Threshold check
            drag_dist = (offset_x**2 + offset_y**2)**0.5
            if drag_dist < 5.0: 
                 return

            # Calculate delta in pdf coords
            dx = offset_x / self.scale
            dy = offset_y / self.scale
            
            new_rects = []
            for r in self._old_rects:
                new_rects.append((r[0] + dx, r[1] + dy, r[2], r[3]))
            
            self.selected_annotation.rects = new_rects
            self.queue_draw()
            return

        # HANDLE SQUARE RESIZE
        if self.selected_annotation.type == 'square':
             anchor_x, anchor_y = self._anchor_pdf
             
             # Calculate new rect defined by anchor and current pdf point
             # Normalize
             new_x = min(anchor_x, pdf_x)
             new_y = min(anchor_y, pdf_y)
             new_w = abs(anchor_x - pdf_x)
             new_h = abs(anchor_y - pdf_y)
             
             self.selected_annotation.rects = [(new_x, new_y, new_w, new_h)]
             self.queue_draw()
             return

        anchor_x, anchor_y = self._anchor_pdf
        
        # Create selection rectangle from anchor to cursor
        import gi
        gi.require_version('Poppler', '0.18')
        from gi.repository import Poppler
        
        rect = Poppler.Rectangle()
        # Always ensure x1 < x2 and y1 < y2
        rect.x1 = min(pdf_x, anchor_x)
        rect.y1 = min(pdf_y, anchor_y)
        rect.x2 = max(pdf_x, anchor_x)
        rect.y2 = max(pdf_y, anchor_y)
        
        
        # Get text selection region from Poppler
        try:
            region = self.page.get_selected_region(
                1.0, Poppler.SelectionStyle.GLYPH, rect
            )
            
            # Convert region to rects for annotation
            if region and region.num_rectangles() > 0:
                new_rects = []
                for i in range(region.num_rectangles()):
                    r = region.get_rectangle(i)
                    # cairo.RectangleInt uses x, y, width, height
                    new_rects.append((
                        r.x, r.y, r.width, r.height
                    ))
                self.selected_annotation.rects = new_rects
            else:
                pass  # No selected text in region
        except Exception as e:
            pass  # Selection error
        self.queue_draw()

    def handle_drag_end(self, offset_x, offset_y):
        if self._resizing_handle and self.selected_annotation and self._old_rects:
            # Record the modification for undo (stores old rects)
            self.store.record_modify(self.selected_annotation.id, self._old_rects)
            
        self._resizing_handle = None
        self._resize_start_pos = None
        self._anchor_pdf = None
        self._old_rects = None
        # Reset cursor to default
        self.set_cursor(None)

    def on_draw(self, area, c, width, height):
        # 1. Render Surface (PDF + Background)
        if self.surface is None:
            self.surface = render_page_to_surface(self.page, self.scale)
        
        c.set_source_surface(self.surface, 0, 0)
        c.paint()
        
        
        if self.store:
            try:
                page_idx = self.page.get_index()
            except:
                page_idx = 0 # Fallback
                
            annotations = self.store.get_for_page(page_idx)
            


            highlight_anns = [a for a in annotations if a.type in ('highlight', 'square')]
            other_anns = [a for a in annotations if a.type not in ('highlight', 'square')]

            if highlight_anns:
                c.save()
                c.scale(self.scale, self.scale)
                c.set_operator(cairo.Operator.MULTIPLY)
                for ann in highlight_anns:
                    
                    r, g, b, _ = ann.color
                    c.set_source_rgba(r, g, b, 1.0)
                    
                    for rect in ann.rects:
                        x, y, w, h = rect
                        c.rectangle(x, y, w, h)
                        c.fill()
                c.restore()

            # Pass for others (Over)
            c.save()
            c.scale(self.scale, self.scale) 
            
            for ann in other_anns:
                r, g, b, a = ann.color
                c.set_source_rgba(r, g, b, a)
                
                if ann.type == 'underline':
                    c.set_line_width(2.5)
                    for rect in ann.rects:
                        x, y, w, h = rect
                        c.move_to(x, y + h)
                        c.line_to(x + w, y + h)
                        c.stroke()
                
                elif ann.type == 'text':
                    self.draw_text_annotation(c, ann)

                elif ann.type == 'square':
                     # Moved to highlight_anns for MULTIPLY blend mode
                     pass
    
            c.restore()

        # 3. Draw Selection Overlay (Text Selection)
        if self.selected_region:
            c.set_source_rgba(0.0, 0.4, 0.8, 0.4) # Blue, semi-transparent
            
            region = self.selected_region
            num_rects = region.num_rectangles()
            
            for i in range(num_rects):
                rect = region.get_rectangle(i)
                # Region rects are already in widget coordinates (if created with scale)
                c.rectangle(rect.x, rect.y, rect.width, rect.height)
                
            c.fill()

        # 4. Draw Annotation Selection (Active)
        if self.selected_annotation:
            self.draw_annotation_selection(c, self.selected_annotation)
            
        # 5. Draw Temp Rect (Area Creation)
        if self.temp_rect:
            x, y, w, h = self.temp_rect
            c.set_source_rgba(1.0, 1.0, 0.0, 0.4) # Yellow guide
            c.rectangle(x, y, w, h)
            c.fill()

    def draw_text_annotation(self, c, ann):
        if not ann.rects:
            return
            
        x, y, w, h = ann.rects[0]
        
        # Create Layout
        layout = PangoCairo.create_layout(c)
        layout.set_text(ann.content, -1)
        
        # Font Style (Naive parsing for now)
        font_desc = Pango.FontDescription("Sans 12")
        # Scale handling: font size 12 matches 12 points in PDF if scale is handled by cairo
        layout.set_font_description(font_desc)
        
        # Position
        c.move_to(x, y)
        
        # Draw
        PangoCairo.show_layout(c, layout)
        
       
        _ink, logical = layout.get_extents()
        
        pixel_w = logical.width / Pango.SCALE
        pixel_h = logical.height / Pango.SCALE
        
        current_w = w
        current_h = h
        
        
        if abs(pixel_w - current_w) > 1.0 or abs(pixel_h - current_h) > 1.0:

            ann.rects[0] = (x, y, pixel_w, pixel_h)

    def draw_annotation_selection(self, c, ann):
        # Draw Start and End Handles for the annotation
        if not ann.rects:
            return

        if ann.type == 'text':
            # Draw Bounding Box only
            c.save()
            c.set_line_width(1.0)
            c.set_dash([4.0, 4.0], 0) # Dashed line
            c.set_source_rgba(0.2, 0.6, 1.0, 0.8) # Blue
            
            for r in ann.rects:
                x, y, w, h = r
                # Convert to widget coords
                wx = x * self.scale
                wy = y * self.scale
                ww = w * self.scale
                wh = h * self.scale
                c.rectangle(wx, wy, ww, wh)
                c.stroke()
            c.restore()
            return

        if ann.type == 'square':
             if not ann.rects: return
             r = ann.rects[0]
             x = r[0] * self.scale
             y = r[1] * self.scale
             w = r[2] * self.scale
             h = r[3] * self.scale
             
             # Draw Box
             c.set_line_width(1)
             c.set_source_rgba(0.2, 0.6, 1.0, 0.8)
             c.rectangle(x, y, w, h)
             c.stroke()
             
             # Draw 4 corner handles
             c.set_source_rgba(1, 1, 1, 1) # White fill
             handle_r = 5
             
             # TL
             c.rectangle(x - handle_r, y - handle_r, handle_r*2, handle_r*2)
             c.fill_preserve()
             c.set_source_rgba(0.2, 0.6, 1.0, 1.0) # Blue border
             c.stroke()
             
             # TR
             c.set_source_rgba(1, 1, 1, 1)
             c.rectangle(x + w - handle_r, y - handle_r, handle_r*2, handle_r*2)
             c.fill_preserve()
             c.set_source_rgba(0.2, 0.6, 1.0, 1.0)
             c.stroke()
             
             # BL
             c.set_source_rgba(1, 1, 1, 1)
             c.rectangle(x - handle_r, y + h - handle_r, handle_r*2, handle_r*2)
             c.fill_preserve()
             c.set_source_rgba(0.2, 0.6, 1.0, 1.0)
             c.stroke()
             
             # BR
             c.set_source_rgba(1, 1, 1, 1)
             c.rectangle(x + w - handle_r, y + h - handle_r, handle_r*2, handle_r*2)
             c.fill_preserve()
             c.set_source_rgba(0.2, 0.6, 1.0, 1.0)
             c.stroke()
             
             return


        
        start_handle, end_handle = self.get_handle_positions()
        
        
        first_rect = ann.rects[0]
        last_rect = ann.rects[-1]
        
        # Start Handle: Top-Left of First Rect
        x1 = first_rect[0] * self.scale
        y1 = first_rect[1] * self.scale
        h1 = first_rect[3] * self.scale
        
        # End Handle: Bottom-Right of Last Rect
        x2 = (last_rect[0] + last_rect[2]) * self.scale
        y2 = (last_rect[1] + last_rect[3]) * self.scale
        h2 = last_rect[3] * self.scale
        
        handle_radius = 10  # Larger for easier clicking
        
        # Start Handle
        c.set_line_width(3)
        c.set_source_rgba(0.2, 0.6, 1.0, 1.0)  # Blue
        c.move_to(x1, y1)
        c.line_to(x1, y1 + h1)
        c.stroke()
        
        # Circle with white border at Top-Left
        c.set_source_rgba(1, 1, 1, 1)  # White border
        c.arc(x1, y1 - handle_radius, handle_radius + 2, 0, 6.28)
        c.fill()
        c.set_source_rgba(0.2, 0.6, 1.0, 1.0)  # Blue fill
        c.arc(x1, y1 - handle_radius, handle_radius, 0, 6.28)
        c.fill()
        
        # End Handle
        c.set_source_rgba(0.2, 0.6, 1.0, 1.0)  # Blue
        c.move_to(x2, y2 - h2)
        c.line_to(x2, y2)
        c.stroke()
        
        # Circle with white border at Bottom-Right
        c.set_source_rgba(1, 1, 1, 1)  # White border
        c.arc(x2, y2 + handle_radius, handle_radius + 2, 0, 6.28)
        c.fill()
        c.set_source_rgba(0.2, 0.6, 1.0, 1.0)  # Blue fill
        c.arc(x2, y2 + handle_radius, handle_radius, 0, 6.28)
        c.fill()

        # Also outline the rects slightly?
        c.set_source_rgba(0.2, 0.6, 1.0, 0.3) # Faint blue
        for r in ann.rects:
             c.rectangle(r[0]*self.scale, r[1]*self.scale, r[2]*self.scale, r[3]*self.scale)
             c.fill()


