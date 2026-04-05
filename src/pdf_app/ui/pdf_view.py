import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Graphene', '1.0')
from gi.repository import Gtk, Adw, GLib, Gdk, GObject, Gio, Graphene
import threading
import bisect

from pdf_app.document.loading import load_document
from pdf_app.ui.page_view import PDFPageView
from pdf_app.document.store import AnnotationStore


class PageSlot:
    __slots__ = ['page_number', 'base_w', 'base_h']

    def __init__(self, page_index, base_w, base_h):
        self.page_number = page_index
        self.base_w = base_w
        self.base_h = base_h


class LazyPageContainer(Gtk.Box):

    def __init__(self, document, page_index, store, scale, base_w, base_h, uri):
        super().__init__()
        self.document = document
        self.page_number = page_index
        self.store = store
        self.scale = scale
        self.uri = uri

        self.page_view = None
        self.is_loaded = False
        self.is_loading = False

        class DummyDA:
            selected_annotation = None
            def queue_draw(self): pass
        self.dummy_da = DummyDA()

        self.base_w = base_w
        self.base_h = base_h

        self.placeholder = Gtk.Box()
        self.placeholder.set_size_request(int(self.base_w * scale), int(self.base_h * scale))
        self.placeholder.add_css_class('page-placeholder')
        self.append(self.placeholder)

    def update_scale(self, scale):
        self.scale = scale
        if self.page_view:
            self.page_view.update_scale(scale)
        else:
            self.placeholder.set_size_request(int(self.base_w * scale), int(self.base_h * scale))

    def load_async(self, tool_name=None):
        if self.is_loaded or self.is_loading: return
        self.is_loading = True
        GLib.idle_add(self._do_load, tool_name)

    def _do_load(self, tool_name):
        if not self.is_loading: return  
        if self.is_loaded: return
        self.is_loaded = True
        self.is_loading = False

        page = self.document.get_page(self.page_number)
        self.base_w, self.base_h = page.get_size()

        self.page_view = PDFPageView(page, self.page_number, self.store, self.uri)
        self.page_view.update_scale(self.scale)
        if tool_name:
            self.page_view.activate_tool(tool_name)

        self.remove(self.placeholder)
        self.append(self.page_view)


    def unload(self):
        if self.is_loading:
            self.is_loading = False
            return

        if not self.is_loaded or not self.page_view:
            return
        if hasattr(self.page_view, 'drawing_area') and self.page_view.drawing_area:
            self.page_view.drawing_area.set_draw_func(None)
            self.page_view.drawing_area.surface = None
        self.remove(self.page_view)
        self.page_view = None
        self.is_loaded = False
        self.is_loading = False
        self.placeholder.set_size_request(int(self.base_w * self.scale), int(self.base_h * self.scale))
        self.append(self.placeholder)

    def prepare_for_removal(self):
        self.unset_state_flags(Gtk.StateFlags.ACTIVE)
        if self.page_view:
            self.page_view.unset_state_flags(Gtk.StateFlags.ACTIVE)
            if hasattr(self.page_view, 'drawing_area') and self.page_view.drawing_area:
                self.page_view.drawing_area.unset_state_flags(Gtk.StateFlags.ACTIVE)

    @property
    def drawing_area(self):
        return self.page_view.drawing_area if self.page_view else self.dummy_da

    @property
    def editor_popover(self):
        return self.page_view.editor_popover if self.page_view else None

    def set_tool(self, tool_name):
        if self.page_view:
            self.page_view.activate_tool(tool_name)

    def set_text_mode(self, enabled):
        if self.page_view:
            self.page_view.set_text_mode(enabled)

    def activate_tool(self, tool_name):
        if self.page_view:
            self.page_view.activate_tool(tool_name)


class PDFView(Gtk.ScrolledWindow):
    __gsignals__ = {
        'page-changed': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        'zoom-changed': (GObject.SignalFlags.RUN_FIRST, None, (float,)),
        'document-loaded': (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, file):
        super().__init__()
        self.file = file
        self.document = None
        self.store = AnnotationStore()
        self.scale = 1.0
        self.min_scale = 0.1
        self.max_scale = 4.0

        self._gesture_start_scale = 1.0
        self._focal_point = (0, 0)

        self.set_vexpand(True)
        self.set_hexpand(True)
        self.set_focusable(True)
        self.set_can_focus(True)

        self.page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.page_box.set_halign(Gtk.Align.CENTER)
        self.page_box.set_margin_top(20)
        self.page_box.set_margin_bottom(20)

        self.viewport = Gtk.Viewport()
        self.viewport.set_scroll_to_focus(False)
        self.viewport.set_child(self.page_box)

        self.vadjustment = self.get_vadjustment()
        self.vadjustment.connect("value-changed", self.on_scroll_changed)

        self.overlay = Gtk.Overlay()
        self.overlay.set_child(self.viewport)

        self.spinner = Gtk.Spinner()
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.spinner.set_valign(Gtk.Align.CENTER)
        self.spinner.set_size_request(48, 48)

        self.spinner_box = Gtk.Box()
        self.spinner_box.set_halign(Gtk.Align.CENTER)
        self.spinner_box.set_valign(Gtk.Align.CENTER)
        self.spinner_box.append(self.spinner)

        self.overlay.add_overlay(self.spinner_box)

        self.set_child(self.overlay)

        # Disable auto-scroll on the implicit Viewport created by ScrolledWindow
        implicit_viewport = self.get_child()
        if hasattr(implicit_viewport, 'set_scroll_to_focus'):
             implicit_viewport.set_scroll_to_focus(False)

        self.page_slots = []
        self._active_containers = {}
        self._visible_range = (0, 0)
        self._top_spacer = Gtk.Box()
        self._bottom_spacer = Gtk.Box()
        self._page_offsets = []
        self._total_content_height = 0
        self._in_rebuild = False
        self._suppress_scroll = False
        self._rebuild_count = 0

        self.current_page_index = 0

        self.sidebar = None
        self.is_dual_mode = False
        self.is_continuous = True

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_ctrl)

        zoom_gesture = Gtk.GestureZoom()
        zoom_gesture.connect("begin", self.on_zoom_begin)
        zoom_gesture.connect("scale-changed", self.on_zoom_scale_changed)
        zoom_gesture.connect("end", self.on_zoom_end)
        self.add_controller(zoom_gesture)

        scroll_controller = Gtk.EventControllerScroll()
        scroll_controller.set_flags(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_controller.connect("scroll", self.on_scroll)
        self.add_controller(scroll_controller)

        self.load_pdf()

    # ========== LOADING ==========

    def load_pdf(self):
        self.spinner.start()
        self.spinner_box.set_visible(True)

        try:
            file_path = self.file.get_path()
            render_file = Gio.File.new_for_path(file_path)
            self.document = load_document(render_file)


            if not self.document:
                raise Exception("Failed to load PDF via Poppler")

            self._n_pages = self.document.get_n_pages()

            if self._n_pages > 0:
                first_page = self.document.get_page(0)
                self._default_w, self._default_h = first_page.get_size()
            else:
                self._default_w, self._default_h = (600, 800)

            for i in range(self._n_pages):
                self.page_slots.append(PageSlot(i, self._default_w, self._default_h))



            self._recompute_page_offsets()
            self._setup_page_box()

            self.spinner.stop()
            self.spinner_box.set_visible(False)

            self.emit('document-loaded')

            GLib.idle_add(self._fit_to_width)

            GLib.timeout_add(500, self._start_annotation_load, file_path)

        except Exception as e:
            self.spinner.stop()
            self.spinner_box.set_visible(False)
            self.show_error(f"Failed to load PDF: {e}")

    def _setup_page_box(self):
        child = self.page_box.get_first_child()
        while child:
            nc = child.get_next_sibling()
            self.page_box.remove(child)
            child = nc

        self._active_containers = {}
        self._visible_range = (0, 0)

        # Pre-create ALL containers. Each starts as a lightweight placeholder.
        # This ensures the Box DOM never changes during scrolling, eliminating scroll jumps.
        for slot in self.page_slots:
            container = LazyPageContainer(
                self.document, slot.page_number, self.store, self.scale,
                slot.base_w, slot.base_h, self.file.get_uri()
            )
            self._active_containers[slot.page_number] = container

        self._rebuild_page_box_layout()

        # Eagerly load first few pages
        initial_count = min(6, len(self.page_slots))
        tool_name = getattr(self, 'tool_name', None)
        for i in range(initial_count):
            c = self._active_containers[i]
            c.is_loading = True
            c._do_load(tool_name)

        self._visible_range = (0, max(initial_count, 1))
        self._initial_load = True
        GLib.idle_add(self._process_lazy_load)
        GLib.timeout_add(1000, lambda: setattr(self, '_initial_load', False) or False)

    def _rebuild_page_box_layout(self):
        """Re-parent all containers into the page_box for current view mode.
        Called once at setup and whenever dual mode is toggled."""
        # Detach all containers from their current parents
        for container in self._active_containers.values():
            parent = container.get_parent()
            if parent:
                if parent == self.page_box:
                    self.page_box.remove(container)
                else:
                    parent.remove(container)
                    if parent.get_parent() == self.page_box:
                        self.page_box.remove(parent)

        # Clear any leftover children (old row boxes, spacers, etc)
        child = self.page_box.get_first_child()
        while child:
            nc = child.get_next_sibling()
            self.page_box.remove(child)
            child = nc

        # Rebuild layout
        if self.is_dual_mode:
            i = 0
            while i < len(self.page_slots):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
                row.set_halign(Gtk.Align.CENTER)
                row.append(self._active_containers[i])
                if i + 1 < len(self.page_slots):
                    row.append(self._active_containers[i + 1])
                self.page_box.append(row)
                i += 2
        else:
            for idx in sorted(self._active_containers.keys()):
                self.page_box.append(self._active_containers[idx])

    def _recompute_page_offsets(self):
        spacing = 10
        margin_top = 20
        offsets = []
        y = margin_top

        if self.is_dual_mode:
            for i in range(0, len(self.page_slots), 2):
                row_h = int(self.page_slots[i].base_h * self.scale)
                if i + 1 < len(self.page_slots):
                    row_h = max(row_h, int(self.page_slots[i + 1].base_h * self.scale))
                offsets.append(y)
                if i + 1 < len(self.page_slots):
                    offsets.append(y)
                y += row_h + spacing
        else:
            for slot in self.page_slots:
                offsets.append(y)
                page_h = int(slot.base_h * self.scale)
                y += page_h + spacing

        self._page_offsets = offsets
        self._total_content_height = y

    # ========== VIRTUAL SCROLL ==========

    def _rebuild_visible_range(self, start_idx, end_idx):
        if (start_idx, end_idx) == self._visible_range:
            return  # No change
        if self._in_rebuild:  # Prevent re-entry
            return

        self._in_rebuild = True
        try:
            self._do_rebuild_visible_range(start_idx, end_idx)
        finally:
            self._in_rebuild = False

    def _do_rebuild_visible_range(self, start_idx, end_idx):
        # No DOM changes needed — all containers are already in the Box.
        # Just control loading/unloading.
        self._suppress_scroll = True

        load_buffer = 2  # Extra pages to keep loaded beyond visible range
        unload_beyond = 10  # Unload pages this far from visible range

        for idx, container in self._active_containers.items():
            in_range = start_idx <= idx < end_idx
            in_buffer = (start_idx - load_buffer) <= idx < (end_idx + load_buffer)
            far_away = idx < (start_idx - unload_beyond) or idx >= (end_idx + unload_beyond)

            if in_range or in_buffer:
                # Update scale for visible/buffer pages
                container.update_scale(self.scale)
            elif far_away and container.is_loaded:
                # Unload distant pages to free memory
                container.unload()

        self._visible_range = (start_idx, end_idx)
        self._suppress_scroll = False

    # ========== ANNOTATION LOADING ==========

    def _start_annotation_load(self, file_path):
        if not self.get_parent(): return False
        thread = threading.Thread(target=self._load_annotations_thread, args=(file_path,), daemon=True)
        thread.start()
        return False

    def _load_annotations_thread(self, file_path):
        try:
            self.store.load_from_pdf(file_path)
            GLib.idle_add(self._on_annotations_loaded)
        except Exception:
            pass

    def _on_annotations_loaded(self):
        for container in self._active_containers.values():
            if container.is_loaded:
                container.drawing_area.queue_draw()

    # ========== FIT / ZOOM ==========

    def _fit_to_width(self):
        viewport_width = self.get_allocated_width()
        if viewport_width <= 1 or not self.document:
            return False

        first_page = self.document.get_page(0)
        page_width, _ = first_page.get_size()

        fit_scale = (viewport_width - 40) / page_width
        self._set_scale_and_scroll(self._clamp_scale(fit_scale))

        return False

    def _clamp_scale(self, scale):
        return max(self.min_scale, min(self.max_scale, scale))

    def _get_viewport_center_focal(self):
        return (self.get_allocated_width() / 2, self.get_allocated_height() / 2)

    def _set_scale_and_scroll(self, scale):
        target_index = self.current_page_index
        self.scale = scale
        self._gesture_start_scale = scale
        self._suppress_scroll = True
        self._apply_zoom()
        self._recompute_page_offsets()
        # Rebuild visible range with new scale
        self._visible_range = (0, 0)  # Force rebuild
        self._process_lazy_load()
        self._suppress_scroll = False
        GLib.idle_add(self.scroll_to_page, target_index)

    def _iter_all_page_views(self):
        return iter(self._active_containers.values())

    def set_tool(self, tool_name):
        self.tool_name = tool_name
        for container in self._active_containers.values():
            container.activate_tool(tool_name)

    def handle_escape(self):
        self.set_tool(None)
        for container in self._active_containers.values():
            if container.drawing_area.selected_annotation:
                container.drawing_area.selected_annotation = None
                container.drawing_area.queue_draw()
            if hasattr(container, 'editor_popover') and container.editor_popover:
                container.editor_popover.popdown()

    def set_text_mode(self, enabled):
        for container in self._active_containers.values():
            container.set_text_mode(enabled)
        if enabled:
            self.page_box.grab_focus()

    def reload_page(self, page_index: int):
        if page_index in self._active_containers:
            self._active_containers[page_index].drawing_area.queue_draw()

    def show_error(self, message):
        label = Gtk.Label(label=f"Error: {message}")
        self.page_box.append(label)

    # ========== ZOOM HANDLERS ==========

    def on_zoom_begin(self, gesture, sequence):
        self._gesture_start_scale = self.scale
        _, x, y = gesture.get_bounding_box_center()
        self._focal_point = (x, y)

    def on_zoom_scale_changed(self, gesture, scale):
        new_scale = self._clamp_scale(self._gesture_start_scale * scale)
        if abs(new_scale - self.scale) < 0.001:
            return
        self._zoom_around_focal(new_scale, self._focal_point)

    def on_zoom_end(self, gesture, sequence):
        self._gesture_start_scale = self.scale

    def _zoom_around_focal(self, new_scale, focal):
        if abs(new_scale - self.scale) < 0.001:
            return

        hadj = self.get_hadjustment()
        vadj = self.get_vadjustment()
        old_scroll_x = hadj.get_value()
        old_scroll_y = vadj.get_value()

        # Document coordinate under the cursor
        doc_x = old_scroll_x + focal[0]
        doc_y = old_scroll_y + focal[1]

        ratio = new_scale / self.scale

        self.scale = new_scale
        self._suppress_scroll = True
        self._apply_zoom()
        self._recompute_page_offsets()

        # Where that same document point ends up after zoom
        new_doc_x = doc_x * ratio
        new_doc_y = doc_y * ratio

        new_scroll_x = max(0, new_doc_x - focal[0])
        new_scroll_y = max(0, new_doc_y - focal[1])

        # With all containers in the Box, GTK knows the total height.
        # Ensure upper bounds are sufficient before setting value.
        vadj.set_upper(max(vadj.get_upper(), new_scroll_y + vadj.get_page_size() + 100))
        hadj.set_upper(max(hadj.get_upper(), new_scroll_x + hadj.get_page_size() + 100))

        hadj.set_value(new_scroll_x)
        vadj.set_value(new_scroll_y)
        self._suppress_scroll = False

    def _apply_zoom(self):
        """Apply current scale to all containers (updates placeholder sizes for layout)."""
        for container in self._active_containers.values():
            container.update_scale(self.scale)
        self.emit('zoom-changed', self.scale)

    # ========== SCROLL & LAZY LOAD ==========

    def on_scroll_changed(self, adjustment):
        if self._in_rebuild or self._suppress_scroll:
            return
        if not self._page_offsets:
            return

        vp_h = self.vadjustment.get_page_size()
        if vp_h <= 1:
            return

        scroll_y = adjustment.get_value()
        center_y = scroll_y + (vp_h / 2)

        idx = bisect.bisect_right(self._page_offsets, center_y) - 1
        found_index = max(0, min(idx, len(self.page_slots) - 1))

        if found_index != self.current_page_index:
            self.current_page_index = found_index
            self.emit('page-changed', found_index)

        if getattr(self, '_lazy_load_source', 0):
            GLib.source_remove(self._lazy_load_source)
        self._lazy_load_source = GLib.timeout_add(16, self._process_lazy_load)

    def _process_lazy_load(self):
        self._lazy_load_source = 0
        self._lazy_load_pending = False
        if self._in_rebuild:  
            return False
        if not self.get_parent() or not self.document: return False
        if not self._page_offsets: return False

        vp_y = self.vadjustment.get_value()
        vp_h = self.vadjustment.get_page_size()

        if vp_h <= 1:
            return False

        # Predictive scroll tracking
        if not hasattr(self, '_last_vp_y'):
            self._last_vp_y = vp_y
        scroll_down = vp_y >= self._last_vp_y
        self._last_vp_y = vp_y

        overscan_top = 4
        overscan_bot = 4
        if scroll_down:
            overscan_bot = 6
            overscan_top = 2
        else:
            overscan_top = 6
            overscan_bot = 2

        # 1 vp_h buffer is basically 1 screen up and down
        visible_start = max(0, vp_y)
        visible_end = vp_y + vp_h

        base_start_idx = bisect.bisect_right(self._page_offsets, visible_start) - 1
        base_start_idx = max(0, base_start_idx)

        base_end_idx = bisect.bisect_right(self._page_offsets, visible_end)
        base_end_idx = min(base_end_idx + 1, len(self.page_slots))

        start_idx = max(0, base_start_idx - overscan_top)
        end_idx = min(len(self.page_slots), base_end_idx + overscan_bot)

        # limit visible pages (must be high enough to cover overscan)
        max_pages = 24 if self.is_dual_mode else 20
        if end_idx - start_idx > max_pages:
            end_idx = start_idx + max_pages

        self._rebuild_visible_range(start_idx, end_idx)

        # Stagger page loading: load ONE page at a time 
        self._schedule_next_page_load()
        return False

    def _schedule_next_page_load(self):
        if not getattr(self, '_page_load_pending', False):
            self._page_load_pending = True
            # Fast initial load, staggered subsequent loads
            delay = 5 if getattr(self, '_initial_load', False) else 50
            GLib.timeout_add(delay, self._load_next_page)

    def _load_next_page(self):
        self._page_load_pending = False
        if not self.get_parent() or not self.document:
            return False

        tool_name = getattr(self, 'tool_name', None)
        start, end = self._visible_range

        # Find the first unloaded container in visible range
        for i in range(start, end):
            container = self._active_containers.get(i)
            if container and not container.is_loaded and not container.is_loading:
                container.load_async(tool_name)
                # Fast gap for initial batch, normal gap for scrolling
                gap = 10 if getattr(self, '_initial_load', False) else 50
                GLib.timeout_add(gap, self._load_next_page)
                return False

        # All visible pages loaded; clear initial flag
        self._initial_load = False
        return False

    def scroll_to_page(self, index):
        if index < 0 or index >= len(self.page_slots):
            return
        if index < len(self._page_offsets):
            target_y = self._page_offsets[index]
            self.vadjustment.set_value(target_y)
            self.current_page_index = index

    # ========== PUBLIC ZOOM METHODS ==========

    def zoom_in(self):
        self._zoom_around_focal(self._clamp_scale(self.scale * 1.1), self._get_viewport_center_focal())

    def zoom_out(self):
        self._zoom_around_focal(self._clamp_scale(self.scale / 1.1), self._get_viewport_center_focal())

    def zoom_reset(self):
        if self.is_dual_mode:
            self._fit_two_pages()
        else:
            self._fit_to_width()

    def _fit_two_pages(self):
        viewport_width = self.get_allocated_width()
        viewport_height = self.get_allocated_height()
        if viewport_width <= 1 or not self.document: return False

        first_page = self.document.get_page(0)
        page_width, page_height = first_page.get_size()

        target_w = (2 * page_width) + 20
        target_h = page_height + 20

        scale_x = (viewport_width - 40) / target_w
        scale_y = (viewport_height - 40) / target_h

        self._set_scale_and_scroll(self._clamp_scale(min(scale_x, scale_y)))
        return False

    # ========== VIEW MODES & LAYOUT ==========

    def set_dual_page_mode(self, enabled):
        if self.is_dual_mode == enabled:
            return
        self.is_dual_mode = enabled
        self._suppress_scroll = True
        self._rebuild_page_box_layout()
        self._recompute_page_offsets()
        # Force rebuild of visible range
        self._visible_range = (0, 0)
        self._process_lazy_load()
        self._suppress_scroll = False

        if enabled:
            GLib.timeout_add(100, self._fit_two_pages)

    def set_continuous_scroll(self, enabled):
        if self.is_continuous == enabled:
            return
        self.is_continuous = enabled
        if not enabled:
            self.scroll_to_page(self.current_page_index)



    # ========== KEYBOARD & SCROLL ==========

    def on_key_pressed(self, controller, keyval, keycode, state):
        is_ctrl = state & Gdk.ModifierType.CONTROL_MASK

        if keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace, Gdk.KEY_Escape):
            for container in self._active_containers.values():
                if container.page_view and container.page_view.on_key_pressed(controller, keyval, keycode, state):
                    return True

        if self.is_continuous:
            step = 50
            page_step = self.get_allocated_height() * 0.9

            vadj = self.get_vadjustment()
            hadj = self.get_hadjustment()

            if keyval == Gdk.KEY_Up:
                vadj.set_value(vadj.get_value() - step)
                return True
            elif keyval == Gdk.KEY_Down:
                vadj.set_value(vadj.get_value() + step)
                return True
            elif keyval == Gdk.KEY_Left:
                hadj.set_value(hadj.get_value() - step)
                return True
            elif keyval == Gdk.KEY_Right:
                hadj.set_value(hadj.get_value() + step)
                return True
            elif keyval == Gdk.KEY_Page_Up:
                vadj.set_value(vadj.get_value() - page_step)
                return True
            elif keyval == Gdk.KEY_Page_Down:
                vadj.set_value(vadj.get_value() + page_step)
                return True
            return False

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
        new_index = max(0, min(len(self.page_slots) - 1, new_index))
        self.scroll_to_page(new_index)
        return False

    def on_scroll(self, controller, dx, dy):
        state = controller.get_current_event_state()

        if state & Gdk.ModifierType.CONTROL_MASK:
            event = controller.get_current_event()
            focal = None
            if event:
                # event.get_position() returns surface-relative coords (includes header bar)
                # Translate to ScrolledWindow-local coords for correct focal math
                sx, sy = event.get_position()
                native = self.get_native()
                if native:
                    nx, ny = native.get_surface_transform()
                    p = Graphene.Point()
                    p.x = sx - nx
                    p.y = sy - ny
                    success, pt = native.compute_point(self, p)
                    if success:
                        focal = (pt.x, pt.y)
                if focal is None:
                    focal = self._get_viewport_center_focal()
            else:
                focal = self._get_viewport_center_focal()

            new_scale = self._clamp_scale(self.scale * (1.1 if dy < 0 else 1 / 1.1))
            self._zoom_around_focal(new_scale, focal)
            return True

        if not self.is_continuous:
            if dy > 0:
                self.navigate_page(1)
            elif dy < 0:
                self.navigate_page(-1)
            return True

        return False

    def clear_all_selections(self, except_page_index=None):
        for container in self._active_containers.values():
            if except_page_index is not None and container.page_number == except_page_index:
                continue
            if container.page_view:
                container.page_view.drawing_area.selected_region = None
                container.page_view.drawing_area.selected_annotation = None
                container.page_view.drawing_area.queue_draw()
                # Also popdown common popover
                if hasattr(container.page_view, 'popover'):
                    container.page_view.popover.popdown()
