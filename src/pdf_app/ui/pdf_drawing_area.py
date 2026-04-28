import cairo
import sys
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, Pango, PangoCairo

from pdf_app.document.engine import dispatch_render_job, RenderContext, RenderPriority

class PDFDrawingArea(Gtk.DrawingArea):
    def __init__(self, page, scale, store, uri: str, page_index: int):
        super().__init__()
        self.page = page
        self.context = RenderContext(scale=scale)
        self.store = store
        self.uri = uri
        self.page_index = page_index
        self.surface = None
        self._render_token = None
        
        self.set_focusable(True) 
        self.set_can_target(True) 
        self.set_draw_func(self.on_draw)
        
        # Selection State
        self.selection_start = None # (x, y) widget coords
        self.selection_end = None
        self.selected_region = None # Poppler.Region
        self.temp_rect = None # (x, y, w, h) for area creation
        
        self.selected_annotation = None # For Highlights/Underlines
        
        # Handle Resize State
        self._resizing_handle = None # 'start', 'end', 'move', 'nw', 'ne', 'sw', 'se'
        self._resize_start_pos = None  
        self.handle_radius = 12  
        self._old_rects = None  # Store original rects for undo
        
        # Text Editing State
        self.editing_mode = False
        self.cursor_position = 0
        self.caret_visible = True
        self._caret_timer = 0
        
        self.pdf_links = []
        self.hovered_link = None
        
        from gi.repository import GLib
        GLib.idle_add(self._extract_links)
        
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

        # Key controller for text input
        self.key_ctrl = Gtk.EventControllerKey()
        self.key_ctrl.connect("key-pressed", self.on_key_pressed)
        self.add_controller(self.key_ctrl)
        
        # IM Context for text input (handles Unicode etc.)
        self.im_context = Gtk.IMContextSimple()
        self.im_context.set_client_widget(self)
        self.im_context.connect("commit", self.on_im_commit)
        self.key_ctrl.set_im_context(self.im_context)
        
        self.queue_draw()
        
    def update_scale(self, scale):
        if self.context.scale != scale:
            if self._render_token:
                self._render_token[0] = True
                self._render_token = None
            
            # Temporary Upscaling During Zoom: Keep old surface but upgrade context
            self.context = RenderContext(scale=scale)
            # self.surface = None  <-- DO NOT set to None (Crucial for progressive zoom)
            self.queue_draw()

    def _extract_links(self):
        from pdf_app.utils.links import extract_embedded_links, extract_text_links
        self.pdf_links.extend(extract_embedded_links(self.page))
        self.pdf_links.extend(extract_text_links(self.page))
        if self.pdf_links:
            self.queue_draw()
        return False

    def _on_motion(self, controller, x, y):
        if self.pdf_links:
            pdf_x = x / self.context.scale
            pdf_y = y / self.context.scale
            
            new_hover = None
            for link in self.pdf_links:
                for r in link['rects']:
                    if r[0] <= pdf_x <= r[0] + r[2] and r[1] <= pdf_y <= r[1] + r[3]:
                        new_hover = link
                        break
                if new_hover:
                    break
                    
            if new_hover != self.hovered_link:
                self.hovered_link = new_hover
                if self.hovered_link:
                    self.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
                    self.set_tooltip_text(self.hovered_link['uri'])
                else:
                    self.set_cursor(None)
                    self.set_tooltip_text("")
                self.queue_draw()

    def _on_leave(self, controller):
        if self.hovered_link:
            self.hovered_link = None
            self.set_cursor(None)
            self.set_tooltip_text("")
            self.queue_draw()

    def get_handle_positions(self):
        ann = self.selected_annotation
        if not ann or not ann.rects:
            return None, None
            
        if ann.type == 'text':
            if not ann.rects: return None, None
            r = ann.rects[0]
            x, y, w, h = r
            start_x = x * self.context.scale
            start_y = y * self.context.scale
            end_x = (x + w) * self.context.scale
            end_y = (y + h) * self.context.scale
            return (start_x, start_y), (end_x, end_y)
            
        if ann.type == 'square':
            if not ann.rects: return None, None
            r = ann.rects[0]
            x, y, w, h = r
            
            # TL
            start_x = x * self.context.scale
            start_y = y * self.context.scale
            
            # BR
            end_x = (x + w) * self.context.scale
            end_y = (y + h) * self.context.scale
            
            return (start_x, start_y), (end_x, end_y)
        
        first_rect = ann.rects[0]
        last_rect = ann.rects[-1]
        
        # Start handle: Top-left of first rect (with offset for circle)
        start_x = first_rect[0] * self.context.scale
        start_y = first_rect[1] * self.context.scale - self.handle_radius
        
        # End handle: Bottom-right of last rect (with offset)
        end_x = (last_rect[0] + last_rect[2]) * self.context.scale
        end_y = (last_rect[1] + last_rect[3]) * self.context.scale + self.handle_radius
        
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
         rect_x = r[0] * self.context.scale
         rect_y = r[1] * self.context.scale
         rect_w = r[2] * self.context.scale
         rect_h = r[3] * self.context.scale
         
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

        if start_handle:
            dist_start = ((start_x - start_handle[0])**2 + (start_y - start_handle[1])**2)**0.5
            dist_end = ((start_x - end_handle[0])**2 + (start_y - end_handle[1])**2)**0.5
            
            if dist_start < threshold:
                self._resizing_handle = 'start'
                self._resize_start_pos = (start_x, start_y)
                self._old_rects = list(self.selected_annotation.rects) if self.selected_annotation.rects else []
                if self.selected_annotation.rects:
                    last_r = self.selected_annotation.rects[-1]
                    self._anchor_pdf = (last_r[0] + last_r[2], last_r[1] + last_r[3]/2.0)
                cursor = Gdk.Cursor.new_from_name("w-resize", None)
                self.set_cursor(cursor)
                return True
    
            elif dist_end < threshold:
                self._resizing_handle = 'end'
                self._resize_start_pos = (start_x, start_y)
                self._old_rects = list(self.selected_annotation.rects) if self.selected_annotation.rects else []
                if self.selected_annotation.rects:
                    # Anchor is the middle-left of the FIRST rectangle
                    first_r = self.selected_annotation.rects[0]
                    self._anchor_pdf = (first_r[0], first_r[1] + first_r[3]/2.0)
                cursor = Gdk.Cursor.new_from_name("e-resize", None)
                self.set_cursor(cursor)
                return True
            
            if ann.type == 'square':
                 # Recheck all 4 corners
                 r = ann.rects[0]
                 x = r[0] * self.context.scale
                 y = r[1] * self.context.scale
                 w = r[2] * self.context.scale
                 h = r[3] * self.context.scale
                 
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
            
            if ann.type == 'text':
                 # Same handles as square
                 r = ann.rects[0]
                 x = r[0] * self.context.scale
                 y = r[1] * self.context.scale
                 w = r[2] * self.context.scale
                 h = r[3] * self.context.scale
                 
                 handles = [
                     ('nw', x, y), ('ne', x + w, y),
                     ('sw', x, y + h), ('se', x + w, y + h),
                     ('n', x + w/2, y), ('s', x + w/2, y + h),
                     ('w', x, y + h/2), ('e', x + w, y + h/2)
                 ]
                 
                 for name, hx, hy in handles:
                     dist = ((start_x - hx)**2 + (start_y - hy)**2)**0.5
                     if dist < threshold:
                         self._resizing_handle = name
                         self._resize_start_pos = (start_x, start_y)
                         self._old_rects = list(ann.rects)
                         # Anchor mapping
                         if name == 'nw': self._anchor_pdf = (r[0]+r[2], r[1]+r[3])
                         elif name == 'ne': self._anchor_pdf = (r[0], r[1]+r[3])
                         elif name == 'sw': self._anchor_pdf = (r[0]+r[2], r[1])
                         elif name == 'se': self._anchor_pdf = (r[0], r[1])
                         elif name == 'n': self._anchor_pdf = (0, r[1]+r[3])
                         elif name == 's': self._anchor_pdf = (0, r[1])
                         elif name == 'w': self._anchor_pdf = (r[0]+r[2], 0)
                         elif name == 'e': self._anchor_pdf = (r[0], 0)
                         
                         cursor_name = f"{name}-resize"
                         # n, s, e, w needs mapping
                         if name in ['n', 's']: cursor_name = 'ns-resize'
                         elif name in ['e', 'w']: cursor_name = 'ew-resize'
                         
                         cursor = Gdk.Cursor.new_from_name(cursor_name, None)
                         self.set_cursor(cursor)
                         return True
            
        # Check for MOVE (drag body)
        pdf_x = start_x / self.context.scale
        pdf_y = start_y / self.context.scale
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
        pdf_x = cur_x / self.context.scale
        pdf_y = cur_y / self.context.scale

        # HANDLE MOVE
        if self._resizing_handle == 'move':
            drag_dist = (offset_x**2 + offset_y**2)**0.5
            if drag_dist < 5.0:
                 return

            dx = offset_x / self.context.scale
            dy = offset_y / self.context.scale

            new_rects = []
            for r in self._old_rects:
                new_rects.append((r[0] + dx, r[1] + dy, r[2], r[3]))

            self.selected_annotation.rects = new_rects
            self.queue_draw()
            return

        # HANDLE SQUARE OR TEXT RESIZE
        if self.selected_annotation.type in ('square', 'text'):
             r = self._old_rects[0]
             anchor_x, anchor_y = self._anchor_pdf
             
             if self._resizing_handle in ('nw', 'ne', 'sw', 'se'):
                 new_x = min(anchor_x, pdf_x)
                 new_y = min(anchor_y, pdf_y)
                 new_w = abs(anchor_x - pdf_x)
                 new_h = abs(anchor_y - pdf_y)
             elif self._resizing_handle in ('n', 's'):
                 new_x = r[0]
                 new_w = r[2]
                 new_y = min(anchor_y, pdf_y)
                 new_h = abs(anchor_y - pdf_y)
             elif self._resizing_handle in ('e', 'w'):
                 new_y = r[1]
                 new_h = r[3]
                 new_x = min(anchor_x, pdf_x)
                 new_w = abs(anchor_x - pdf_x)
             else:
                 new_x, new_y, new_w, new_h = r
                 
             # Enforce minimum size for text
             if self.selected_annotation.type == 'text':
                 if new_w < 20: new_w = 20
                 if new_h < 10: new_h = 10
                 # Recompute x/y if clamped and dragging left/top
                 if self._resizing_handle in ('nw', 'sw', 'w') and new_w == 20:
                     new_x = anchor_x - 20
                 if self._resizing_handle in ('nw', 'ne', 'n') and new_h == 10:
                     new_y = anchor_y - 10
                     
             self.selected_annotation.rects = [(new_x, new_y, new_w, new_h)]
             self.queue_draw()
             return

        anchor_x, anchor_y = self._anchor_pdf

        if self._resizing_handle == 'end':
            # End handle cannot move before the Start handle (anchor)
            if pdf_y < anchor_y - 5.0: # Prevent jumping to previous lines
                pdf_y = anchor_y
                pdf_x = anchor_x
            elif abs(pdf_y - anchor_y) <= 5.0 and pdf_x < anchor_x:
                pdf_x = anchor_x
                
        elif self._resizing_handle == 'start':
            # Start handle cannot move after the End handle (anchor)
            if pdf_y > anchor_y + 5.0: # Prevent jumping to next lines
                pdf_y = anchor_y
                pdf_x = anchor_x
            elif abs(pdf_y - anchor_y) <= 5.0 and pdf_x > anchor_x:
                pdf_x = anchor_x

        # Create geometric selection rectangle from anchor to clamped cursor
        from gi.repository import Poppler
        
        rect = Poppler.Rectangle()
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
            # Only record if something actually changed
            if self.selected_annotation.rects != self._old_rects:
                self.store.record_modify(self.selected_annotation.id, self._old_rects)
            
        self._resizing_handle = None
        self._resize_start_pos = None
        self._anchor_pdf = None
        self._old_rects = None
        # Reset cursor to default
        self.set_cursor(None)

    def _on_render_finished(self, surface, context: RenderContext):
        is_exact = (context == self.context)
        is_fast = (context.scale == self.context.scale * 0.5)

        if not (is_exact or is_fast):
            return
            
        # Prevent old fast render from wiping out the finished exact render if they return out of order
        if is_fast and hasattr(self, 'surface_context') and self.surface_context == self.context:
            return

        self.surface = surface
        self.surface_context = context
        if is_exact:
            self._render_token = None
            
        if self.surface:
            self.queue_draw()

    def on_draw(self, area, c, width, height):
        # 1. Draw Cached Surface (with temp scaling if outdated)
        if self.surface is not None:
            c.save()
            if hasattr(self, 'surface_context') and self.surface_context.scale != self.context.scale:
                ratio = self.context.scale / self.surface_context.scale
                c.scale(ratio, ratio)
            c.set_source_surface(self.surface, 0, 0)
            c.paint()
            c.restore()
        else:
            c.set_source_rgb(1.0, 1.0, 1.0)
            c.paint()
            
        # 2. Check if a high-res queue needs to be requested
        if self.surface is None or not hasattr(self, 'surface_context') or self.surface_context != self.context:
            if not self._render_token:
                self._render_token = [False]
                
                # Progressive Rendering Phase 1: Fast 0.5x Scale
                if self.surface is None:
                    fast_ctx = RenderContext(scale=self.context.scale * 0.5, rotation=self.context.rotation)
                    dispatch_render_job(
                        self.uri, self.page_index, fast_ctx, 
                        RenderPriority.PRELOAD, self._on_render_finished, self._render_token
                    )
                
                # Progressive Rendering Phase 2: High priority exact render
                dispatch_render_job(
                    self.uri, self.page_index, self.context, 
                    RenderPriority.VISIBLE, self._on_render_finished, self._render_token
                )
            return
            
        if self.store:
            try:
                page_idx = self.page.get_index()
            except Exception:
                page_idx = 0

            annotations = self.store.get_for_page(page_idx)


            highlight_anns = [a for a in annotations if a.type in ('highlight', 'square')]
            other_anns = [a for a in annotations if a.type not in ('highlight', 'square')]

            if highlight_anns:
                c.save()
                c.scale(self.context.scale, self.context.scale)
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
            c.scale(self.context.scale, self.context.scale) 
            
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

        #  Draw Selection Overlay (Text Selection)
        if self.selected_region:
            c.set_source_rgba(0.0, 0.4, 0.8, 0.4) # Blue, semi-transparent
            
            region = self.selected_region
            num_rects = region.num_rectangles()
            
            for i in range(num_rects):
                rect = region.get_rectangle(i)
                # Region rects are already in widget coordinates (if created with scale)
                c.rectangle(rect.x, rect.y, rect.width, rect.height)
                
            c.fill()

        # Draw Active Hovered Link
        if self.hovered_link:
            c.set_source_rgba(0.2, 0.5, 0.8, 0.15) # Faint blue highlight
            for r in self.hovered_link['rects']:
                c.rectangle(r[0] * self.context.scale, r[1] * self.context.scale, r[2] * self.context.scale, r[3] * self.context.scale)
            c.fill()
            c.set_source_rgba(0.2, 0.5, 0.8, 0.5)
            c.set_line_width(1.0)
            for r in self.hovered_link['rects']:
                c.move_to(r[0] * self.context.scale, (r[1] + r[3]) * self.context.scale)
                c.line_to((r[0] + r[2]) * self.context.scale, (r[1] + r[3]) * self.context.scale)
                c.stroke()

        #  Draw Annotation Selection (Active)
        if self.selected_annotation:
            self.draw_annotation_selection(c, self.selected_annotation)
            
        #  Draw Temp Rect (Area Creation)
        if self.temp_rect:
            x, y, w, h = self.temp_rect
            c.set_source_rgba(1.0, 1.0, 0.0, 0.4) # Yellow guide
            c.rectangle(x, y, w, h)
            c.fill()

    def draw_text_annotation(self, c, ann):
        if not ann.rects:
            return
            
        x, y, w, h = ann.rects[0]
        
        layout = PangoCairo.create_layout(c)
        layout.set_text(ann.content, -1)
        
        # Configure layout
        layout.set_width(int(w * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        
        # Build Font Description
        font_desc_str = ann.font_family
        if ann.bold: font_desc_str += " Bold"
        if ann.italic: font_desc_str += " Italic"
        font_desc_str += f" {ann.font_size}"
        
        font_desc = Pango.FontDescription(font_desc_str)
        layout.set_font_description(font_desc)
        
        # Position
        c.move_to(x, y)
        
        # Set text color
        if ann.color:
            r, g, b, a = ann.color
            c.set_source_rgba(r, g, b, a)
        else:
            c.set_source_rgba(0, 0, 0, 1)
        
        # Draw Text
        PangoCairo.show_layout(c, layout)
        
        # Underline (Manual since Pango underline can be tricky with scaling)
        if ann.underline:
            _ink, logical = layout.get_extents()
            text_h = logical.height / Pango.SCALE
            lines = layout.get_lines()
            line_y = y
            for line in lines:
                ext = line.get_extents()[1]
                lw = ext.width / Pango.SCALE
                lh = ext.height / Pango.SCALE
                c.set_line_width(ann.font_size / 15.0)
                c.move_to(x, line_y + lh * 0.9) # Slightly below baseline
                c.line_to(x + lw, line_y + lh * 0.9)
                c.stroke()
                line_y += lh
        
        # Draw Caret if in editing mode and selected
        if self.editing_mode and self.selected_annotation == ann and self.caret_visible:
            self.cursor_position = max(0, min(self.cursor_position, len(ann.content)))
            byte_index = len(ann.content[:self.cursor_position].encode('utf-8'))
            strong_pos, weak_pos = layout.get_cursor_pos(byte_index)
            cx = x + strong_pos.x / Pango.SCALE
            cy = y + strong_pos.y / Pango.SCALE
            ch = strong_pos.height / Pango.SCALE
            
            c.set_source_rgba(0, 0, 0, 1)
            c.set_line_width(1.5 / self.context.scale)
            c.move_to(cx, cy)
            c.line_to(cx, cy + ch)
            c.stroke()
        
        _ink, logical = layout.get_extents()
        pixel_w = logical.width / Pango.SCALE
        pixel_h = logical.height / Pango.SCALE
        
        # Smart resize: tightly snap the height to the text height.
        if getattr(ann, '_auto_shrink', False):
            new_w = pixel_w
            ann._auto_shrink = False
        elif self._resizing_handle:
            new_w = w
        else:
            new_w = max(w, pixel_w) if ann.content else w
            
        ann.rects[0] = (x, y, new_w, pixel_h)

    def set_editing_mode(self, enabled):
        if self.editing_mode == enabled:
            return
            
        self.editing_mode = enabled
        if enabled:
            if self.selected_annotation and self.selected_annotation.type == 'text':
                self.cursor_position = len(self.selected_annotation.content)
            self.caret_visible = True
            from gi.repository import GLib
            if self._caret_timer:
                GLib.source_remove(self._caret_timer)
            self._caret_timer = GLib.timeout_add(500, self._toggle_caret)
            self.im_context.focus_in()
            self.grab_focus()
            self.queue_draw()
        else:
            if self._caret_timer:
                from gi.repository import GLib
                GLib.source_remove(self._caret_timer)
                self._caret_timer = 0
            self.caret_visible = False
            self.im_context.focus_out()
            self.queue_draw()
            
    def _toggle_caret(self):
        self.caret_visible = not self.caret_visible
        self.queue_draw()
        return True

    def on_im_commit(self, im_context, text):
        if not self.editing_mode or not self.selected_annotation: return
        ann = self.selected_annotation
        if ann.type != 'text': return
        
        # Record undo
        self.store.record_text_change(ann.id, ann.content)
        
        # Insert text
        left = ann.content[:self.cursor_position]
        right = ann.content[self.cursor_position:]
        ann.content = left + text + right
        self.cursor_position += len(text)
        self.queue_draw()

    def on_key_pressed(self, controller, keyval, keycode, state):
        if not self.editing_mode or not self.selected_annotation:
            return False
            
        ann = self.selected_annotation
        if ann.type != 'text': return False
        
        if keyval == Gdk.KEY_Escape:
            self.set_editing_mode(False)
            return True
            
        if keyval == Gdk.KEY_BackSpace:
            if self.cursor_position > 0:
                ann._auto_shrink = True
                self.store.record_text_change(ann.id, ann.content)
                left = ann.content[:self.cursor_position - 1]
                right = ann.content[self.cursor_position:]
                ann.content = left + right
                self.cursor_position -= 1
                self.queue_draw()
            return True
            
        if keyval == Gdk.KEY_Delete:
            if self.cursor_position < len(ann.content):
                ann._auto_shrink = True
                self.store.record_text_change(ann.id, ann.content)
                left = ann.content[:self.cursor_position]
                right = ann.content[self.cursor_position + 1:]
                ann.content = left + right
                self.queue_draw()
            return True
            
        if keyval == Gdk.KEY_Left:
            if self.cursor_position > 0:
                self.cursor_position -= 1
                self.caret_visible = True
                self.queue_draw()
            return True
            
        if keyval == Gdk.KEY_Right:
            if self.cursor_position < len(ann.content):
                self.cursor_position += 1
                self.caret_visible = True
                self.queue_draw()
            return True
            
        if keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
            ann._auto_shrink = True
            self.store.record_text_change(ann.id, ann.content)
            left = ann.content[:self.cursor_position]
            right = ann.content[self.cursor_position:]
            ann.content = left + "\n" + right
            self.cursor_position += 1
            self.queue_draw()
            return True
            
        # Fallback for printable characters if IMContext didn't consume it
        char = Gdk.keyval_to_unicode(keyval)
        if char >= 32 and char != 127:
            text = chr(char)
            self.store.record_text_change(ann.id, ann.content)
            left = ann.content[:self.cursor_position]
            right = ann.content[self.cursor_position:]
            ann.content = left + text + right
            self.cursor_position += 1
            self.queue_draw()
            return True
            
        return False

    def draw_annotation_selection(self, c, ann):
        # Draw Start and End Handles for the annotation
        if not ann.rects:
            return

        if ann.type == 'text':
             if not ann.rects: return
             r = ann.rects[0]
             x = r[0] * self.context.scale
             y = r[1] * self.context.scale
             w = r[2] * self.context.scale
             h = r[3] * self.context.scale
             
             # Draw Box
             c.set_line_width(1)
             if self.editing_mode:
                 c.set_source_rgba(0.2, 0.6, 1.0, 0.8) # Solid blue when editing
             else:
                 c.set_dash([4.0, 4.0], 0) # Dashed line
                 c.set_source_rgba(0.2, 0.6, 1.0, 0.8)
             c.rectangle(x, y, w, h)
             c.stroke()
             c.set_dash([], 0) # Reset dash
             
             # Draw 8 handles
             c.set_source_rgba(1, 1, 1, 1) # White fill
             handle_r = 4
             
             handles_pos = [
                 (x, y), (x + w, y), (x, y + h), (x + w, y + h), # Corners
                 (x + w/2, y), (x + w/2, y + h), (x, y + h/2), (x + w, y + h/2) # Edges
             ]
             
             for hx, hy in handles_pos:
                 c.rectangle(hx - handle_r, hy - handle_r, handle_r*2, handle_r*2)
                 c.fill_preserve()
                 c.set_source_rgba(0.2, 0.6, 1.0, 1.0) # Blue border
                 c.stroke()
                 c.set_source_rgba(1, 1, 1, 1) # Reset fill color for next
             
             return

        if ann.type == 'square':
             if not ann.rects: return
             r = ann.rects[0]
             x = r[0] * self.context.scale
             y = r[1] * self.context.scale
             w = r[2] * self.context.scale
             h = r[3] * self.context.scale
             
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
        x1 = first_rect[0] * self.context.scale
        y1 = first_rect[1] * self.context.scale
        h1 = first_rect[3] * self.context.scale
        
        # End Handle: Bottom-Right of Last Rect
        x2 = (last_rect[0] + last_rect[2]) * self.context.scale
        y2 = (last_rect[1] + last_rect[3]) * self.context.scale
        h2 = last_rect[3] * self.context.scale
        
        handle_radius = 10  
        
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

        
        c.set_source_rgba(0.2, 0.6, 1.0, 0.3) # Faint blue
        for r in ann.rects:
             c.rectangle(r[0]*self.context.scale, r[1]*self.context.scale, r[2]*self.context.scale, r[3]*self.context.scale)
             c.fill()


