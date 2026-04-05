import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib

from pdf_app.ui.pdf_view import PDFView
from pdf_app.ui.empty_view import EmptyView
from pdf_app.ui.thumbnail_sidebar import ThumbnailSidebar

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.set_title("Inlinea")
        self.set_default_size(1200, 800)
        
        self.connect("close-request", self.on_close_request)

        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)
        
        self.toolbar_view = Adw.ToolbarView()
        self.toast_overlay.set_child(self.toolbar_view)

        self.header_bar = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(self.header_bar)
        
        self.file_box = self.build_filebox()
        self.tool_box = self.build_toolbox()
        
        self.header_left_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10
        )
        self.header_left_box.append(self.file_box)
        self.header_left_box.append(self.tool_box)
        self.header_bar.pack_start(self.header_left_box)

        self.view_box = self.build_viewbox()
        self.zoom_box = self.build_zoombox()
        self.header_right_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10
        )
        self.header_right_box.append(self.view_box)
        self.header_right_box.append(self.zoom_box)
        self.header_bar.pack_end(self.header_right_box)


        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        self.page_label = Gtk.Label(label="Page 0 / 0")
        self.page_label.set_css_classes(["numeric"])
        
        self.zoom_label = Gtk.Label(label="100%")
        self.zoom_label.set_css_classes(["numeric"])
        
        title_box.append(self.page_label)
        self.header_separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        title_box.append(self.header_separator)
        title_box.append(self.zoom_label)

        self.header_bar.set_title_widget(title_box)
        
        # 3. Ribbon (Top Bar)
        self.active_tool_name = None

        self.tab_bar = Adw.TabBar()
        self.toolbar_view.add_top_bar(self.tab_bar)
        
        self.split_view = Adw.OverlaySplitView()
        self.split_view.set_vexpand(True)
        self.split_view.set_sidebar_width_fraction(0.15)
        self.split_view.set_min_sidebar_width(150)
        self.split_view.set_max_sidebar_width(400)
        self.split_view.set_enable_show_gesture(True)
        self.split_view.set_enable_hide_gesture(True)
        self.split_view.set_show_sidebar(False)
        
        self.toolbar_view.set_content(self.split_view)
        
        self.sidebar_placeholder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        lbl = Gtk.Label(label="No Pages")
        lbl.set_vexpand(True)
        lbl.set_valign(Gtk.Align.CENTER)
        self.sidebar_placeholder.append(lbl)
        self.sidebar_placeholder.set_size_request(200, -1)
        
        self.split_view.set_sidebar(self.sidebar_placeholder)
        
        self.tab_view = Adw.TabView()
        self.tab_view.connect('notify::selected-page', self.on_tab_changed)
        self.tab_view.connect("close-page", self.on_close_page)
        self.tab_bar.set_view(self.tab_view)

        self.split_view.set_content(self.tab_view)

        self.setup_actions()
        self.add_empty_tab()

    def setup_actions(self):
        action_open = Gio.SimpleAction.new("open_document", None)
        action_open.connect("activate", self.on_open_document)
        self.add_action(action_open)

        action_new_tab = Gio.SimpleAction.new("new_tab", None)
        action_new_tab.connect("activate", self.on_new_tab)
        self.add_action(action_new_tab)
        
        action_text_mode = Gio.SimpleAction.new_stateful(
            "insert_text_mode",
            None,
            GLib.Variant.new_boolean(False)
        )

        action_undo = Gio.SimpleAction.new("undo", None)
        action_undo.connect("activate", self.on_undo)
        self.add_action(action_undo)

        action_redo = Gio.SimpleAction.new("redo", None)
        action_redo.connect("activate", self.on_redo)
        self.add_action(action_redo)
        
        app = self.get_application()
        if app:
            app.set_accels_for_action("win.open_document", ["<Ctrl>o"])
            app.set_accels_for_action("win.undo", ["<Ctrl>z"])
            app.set_accels_for_action("win.redo", ["<Ctrl>y"])
            app.set_accels_for_action("win.zoom_in", ["<Ctrl>plus", "<Ctrl>equal", "<Ctrl>KP_Add"])
            app.set_accels_for_action("win.zoom_out", ["<Ctrl>minus", "<Ctrl>KP_Subtract"])
            app.set_accels_for_action("win.zoom_reset", ["<Ctrl>0", "<Ctrl>KP_0"])

        action_zoom_in = Gio.SimpleAction.new("zoom_in", None)
        action_zoom_in.connect("activate", self.on_zoom_in)
        self.add_action(action_zoom_in)

        action_zoom_out = Gio.SimpleAction.new("zoom_out", None)
        action_zoom_out.connect("activate", self.on_zoom_out)
        self.add_action(action_zoom_out)

        action_zoom_reset = Gio.SimpleAction.new("zoom_reset", None)
        action_zoom_reset.connect("activate", self.on_zoom_reset)
        self.add_action(action_zoom_reset)

        action_save = Gio.SimpleAction.new("save", None)
        action_save.connect("activate", self.on_save)
        self.add_action(action_save)

        action_save_as = Gio.SimpleAction.new("save_as", None)
        action_save_as.connect("activate", self.on_save_as)
        self.add_action(action_save_as)

        action_export = Gio.SimpleAction.new("export", None)
        action_export.connect("activate", self.on_export_pdf)
        self.add_action(action_export)

        app.set_accels_for_action("win.save", ["<Ctrl>s"])
        app.set_accels_for_action("win.save_as", ["<Ctrl><Shift>s"])
        app.set_accels_for_action("win.deselect", ["Escape"])

        action_deselect = Gio.SimpleAction.new("deselect", None)
        action_deselect.connect("activate", self.on_deselect)
        self.add_action(action_deselect)

        action_toggle_sidebar = Gio.SimpleAction.new_stateful(
            "toggle_sidebar",
            None,
            GLib.Variant.new_boolean(False)
        )
        action_toggle_sidebar.connect("change-state", self.on_toggle_sidebar)
        self.add_action(action_toggle_sidebar)
        self.action_toggle_sidebar = action_toggle_sidebar
        
        if app:
            app.set_accels_for_action("win.toggle_sidebar", ["<Ctrl><Alt>m"])

        action_view_dual = Gio.SimpleAction.new_stateful(
            "view_dual", None, GLib.Variant.new_boolean(False)
        )
        action_view_dual.connect("change-state", self.on_view_dual_toggled)
        self.add_action(action_view_dual)
        
        action_view_continuous = Gio.SimpleAction.new_stateful(
            "view_continuous", None, GLib.Variant.new_boolean(True)
        )
        action_view_continuous.connect("change-state", self.on_view_continuous_toggled)
        self.add_action(action_view_continuous)

    def on_deselect(self, action, param):
        page = self.get_active_page()
        if page:
            if hasattr(page, 'handle_escape'):
                page.handle_escape()
        
        # Always sync UI (Reset to Select Mode)
        self.update_ribbon_tool_state(None)

    def on_open_document(self, action, param):
        dialog = Gtk.FileChooserNative(
            title="Open PDF",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN
        )
        
        filter_pdf = Gtk.FileFilter()
        filter_pdf.set_name("PDF Documents")
        filter_pdf.add_mime_type("application/pdf")
        dialog.add_filter(filter_pdf)
        
        dialog.set_select_multiple(True)
        dialog.connect("response", self.on_open_response)
        dialog.show()

    def on_open_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            files = dialog.get_files()
            # method get_files() returns a GListModel (Gtk.Bitset? No, Gio.ListModel of Gio.File)
            # We need to iterate it. 
            # Actually, Gtk.FileChooser.get_files() returns a Gio.ListModel.
            
            n_files = files.get_n_items()
            for i in range(n_files):
                file = files.get_item(i)
                self.open_pdf_tab(file)
        dialog.destroy()

    def build_toolbox(self):
        box_tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box_tools.add_css_class("linked")
        
        btn_select = Gtk.ToggleButton(icon_name="tool-pointer-symbolic")
        btn_select.set_tooltip_text("Select / Move")
        btn_select.set_active(True)
        btn_select.connect("toggled", self.on_tool_toggled, None)
        self.btn_select = btn_select
        
        btn_highlight = Gtk.ToggleButton(icon_name="document-edit-symbolic")
        btn_highlight.set_tooltip_text("Highlight")
        btn_highlight.set_group(btn_select)
        btn_highlight.connect("toggled", self.on_tool_toggled, "highlight")
        self.btn_highlight = btn_highlight
        
        btn_underline = Gtk.ToggleButton(icon_name="format-text-underline-symbolic")
        btn_underline.set_tooltip_text("Underline")
        btn_underline.set_group(btn_select)
        btn_underline.connect("toggled", self.on_tool_toggled, "underline")
        self.btn_underline = btn_underline
        
        btn_text = Gtk.ToggleButton(icon_name="insert-text-symbolic") 
        btn_text.set_tooltip_text("Add Text")
        btn_text.set_group(btn_select)
        btn_text.connect("toggled", self.on_tool_toggled, "text")
        self.btn_text = btn_text
        
        btn_area = Gtk.ToggleButton(icon_name="shape-item-symbolic")
        btn_area.set_tooltip_text("Area Highlight")
        btn_area.set_group(btn_select)
        btn_area.connect("toggled", self.on_tool_toggled, "area")
        self.btn_area = btn_area

        box_tools.append(btn_select)
        box_tools.append(btn_highlight)
        box_tools.append(btn_underline)
        box_tools.append(btn_text)
        box_tools.append(btn_area)
        
        return box_tools

    def build_filebox(self):
        box_file = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box_file.add_css_class("linked")
        
        btn_open = Gtk.Button(icon_name="document-open-symbolic")
        btn_open.set_tooltip_text("Open PDF")
        btn_open.set_action_name("win.open_document")
        
        btn_save = Gtk.Button(icon_name="document-save-symbolic")
        btn_save.set_tooltip_text("Save (Ctrl+S)")
        btn_save.set_action_name("win.save")
        
        btn_save_as = Gtk.Button(icon_name="document-save-as-symbolic")
        btn_save_as.set_tooltip_text("Save As (Ctrl+Shift+S)")
        btn_save_as.set_action_name("win.save_as")
        
        btn_export = Gtk.Button(icon_name="export-symbolic")
        btn_export.set_tooltip_text("Export to PDF")
        btn_export.set_action_name("win.export")
        
        box_file.append(btn_open)
        box_file.append(btn_save)
        box_file.append(btn_save_as)
        box_file.append(btn_export)
        
        return box_file

    def build_viewbox(self):
        box_view = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box_view.add_css_class("linked")
        
        btn_sidebar = Gtk.ToggleButton(icon_name="sidebar-show-symbolic")
        btn_sidebar.set_tooltip_text("Toggle Sidebar")
        btn_sidebar.set_action_name("win.toggle_sidebar")
        
        btn_dual = Gtk.ToggleButton(icon_name="view-grid-symbolic")
        btn_dual.set_tooltip_text("Dual Page View")
        btn_dual.set_action_name("win.view_dual")
        
        btn_cont = Gtk.ToggleButton(icon_name="view-continuous-symbolic")
        btn_cont.set_tooltip_text("Continuous Scroll")
        btn_cont.set_action_name("win.view_continuous")
        
        box_view.append(btn_sidebar)
        box_view.append(btn_dual)
        box_view.append(btn_cont)
        
        return box_view

    def build_zoombox(self):
        box_zoom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box_zoom.add_css_class("linked")
        
        btn_zoom_out = Gtk.Button(icon_name="zoom-out-symbolic")
        btn_zoom_out.set_action_name("win.zoom_out")
        
        btn_zoom_fit = Gtk.Button(icon_name="zoom-fit-best-symbolic")
        btn_zoom_fit.set_tooltip_text("Fit Width")
        btn_zoom_fit.set_action_name("win.zoom_reset")
        
        btn_zoom_in = Gtk.Button(icon_name="zoom-in-symbolic")
        btn_zoom_in.set_action_name("win.zoom_in")
        
        box_zoom.append(btn_zoom_out)
        box_zoom.append(btn_zoom_fit)
        box_zoom.append(btn_zoom_in)
        
        return box_zoom

    def on_tool_toggled(self, btn, tool_name):
        if btn.get_active():
            self.activate_tool(tool_name)
    
    def get_active_page(self):
        """Get current PDFView."""
        page = self.tab_view.get_selected_page()
        if page:
            return page.get_child()
        return None
            
    def activate_tool(self, tool_name):
        self.active_tool_name = tool_name
        for i in range(self.tab_view.get_n_pages()):
            page_wrapper = self.tab_view.get_nth_page(i)
            view = page_wrapper.get_child()
            if hasattr(view, 'drawing_area') and view.drawing_area.selected_annotation:
                 view.drawing_area.selected_annotation = None
                 view.drawing_area.queue_draw()
            if hasattr(view, 'editor_popover') and view.editor_popover:
                 view.editor_popover.popdown()
            if hasattr(view, 'set_tool'):
                view.set_tool(tool_name)

    def grab_focus_on_click(self, gesture, n_press, x, y):
        self.grab_focus()
        
    def update_ribbon_tool_state(self, tool_name):
        self.btn_select.handler_block_by_func(self.on_tool_toggled)
        self.btn_highlight.handler_block_by_func(self.on_tool_toggled)
        self.btn_underline.handler_block_by_func(self.on_tool_toggled)
        self.btn_text.handler_block_by_func(self.on_tool_toggled)
        self.btn_area.handler_block_by_func(self.on_tool_toggled)
        
        try:
             if tool_name == 'highlight': self.btn_highlight.set_active(True)
             elif tool_name == 'underline': self.btn_underline.set_active(True)
             elif tool_name == 'text': self.btn_text.set_active(True)
             elif tool_name == 'area': self.btn_area.set_active(True)
             else: self.btn_select.set_active(True)
        finally:
             self.btn_select.handler_unblock_by_func(self.on_tool_toggled)
             self.btn_highlight.handler_unblock_by_func(self.on_tool_toggled)
             self.btn_underline.handler_unblock_by_func(self.on_tool_toggled)
             self.btn_text.handler_unblock_by_func(self.on_tool_toggled)
             self.btn_area.handler_unblock_by_func(self.on_tool_toggled)
             
        self.activate_tool(tool_name)

    def on_new_tab(self, action, param):
        self.add_empty_tab()

    def on_undo(self, action, param):
        selected = self.tab_view.get_selected_page()
        if not selected:
            return
        view = selected.get_child()
        if isinstance(view, PDFView):
            result = view.store.undo()
            if result:
                op, ann = result
                view.reload_page(ann.page_index)

    def on_redo(self, action, param):
        selected = self.tab_view.get_selected_page()
        if not selected:
            return
        view = selected.get_child()
        if isinstance(view, PDFView):
            result = view.store.redo()
            if result:
                op, ann = result
                view.reload_page(ann.page_index)



    def add_empty_tab(self):
        page = self.tab_view.append(EmptyView())
        page.set_title("New Tab")
        self.tab_view.set_selected_page(page)

    def open_pdf_tab(self, file):
        new_file_path = file.get_path()
        if new_file_path:
            for i in range(self.tab_view.get_n_pages()):
                page_wrapper = self.tab_view.get_nth_page(i)
                view = page_wrapper.get_child()
                if isinstance(view, PDFView) and hasattr(view, 'file') and view.file:
                    if view.file.get_path() == new_file_path:
                        self.tab_view.set_selected_page(page_wrapper)
                        return

        pdf_view = PDFView(file)
        
        if self.active_tool_name:
            pdf_view.set_tool(self.active_tool_name)
        
        page = self.tab_view.append(pdf_view)
        page.set_title(file.get_basename())
        page.set_icon(None)
        
        def on_dirty_changed(is_dirty):
            self.update_tab_status(page, is_dirty)
            
        pdf_view.store.on_dirty_changed = on_dirty_changed
        pdf_view.connect('document-loaded', self.on_pdf_document_loaded)
        
        self.tab_view.set_selected_page(page)

    def on_pdf_document_loaded(self, view):
        if not hasattr(view, 'sidebar') or not view.sidebar:
            view.sidebar = ThumbnailSidebar()
            view.sidebar.connect('page-selected', self.on_sidebar_page_selected)
            GLib.timeout_add(3000, self._deferred_sidebar_load, view)
            
        self.update_header_info(view)
        
        selected_page = self.tab_view.get_selected_page()
        if selected_page and selected_page.get_child() == view:
            self.action_toggle_sidebar.set_enabled(True)
            self.split_view.set_sidebar(view.sidebar)
            was_visible = getattr(view, 'sidebar_visible', False)
            self.split_view.set_show_sidebar(was_visible)

    def _deferred_sidebar_load(self, view):
        if view.get_parent() and hasattr(view, 'sidebar') and view.sidebar and view.document:
            view.sidebar.load_document(view.document, view.file.get_uri())
        return False

    def update_tab_status(self, page, is_dirty):
        title = page.get_title()
        if not title: return
        
        clean_title = title
        if title.startswith("* "):
            clean_title = title[2:]
            
        if is_dirty:
            page.set_title(f"* {clean_title}")
        else:
            page.set_title(clean_title)

    def on_zoom_in(self, action, param):
        selected = self.tab_view.get_selected_page()
        if selected:
            view = selected.get_child()
            if isinstance(view, PDFView):
                view.zoom_in()

    def on_zoom_out(self, action, param):
        selected = self.tab_view.get_selected_page()
        if selected:
            view = selected.get_child()
            if isinstance(view, PDFView):
                view.zoom_out()

    def on_zoom_reset(self, action, param):
        selected = self.tab_view.get_selected_page()
        if selected:
            view = selected.get_child()
            if isinstance(view, PDFView):
                view.zoom_reset()

    def on_save(self, action, param):
        selected_page = self.tab_view.get_selected_page()
        if not selected_page: return
        view = selected_page.get_child()
        if not hasattr(view, 'store') or not hasattr(view, 'file'): return
        
        src = view.file.get_path()
        try:
            view.store.save_to_pdf(src, src)
            toast = Adw.Toast.new(f"Saved {view.file.get_basename()}")
            self.toast_overlay.add_toast(toast)
        except Exception:
            toast = Adw.Toast.new("Save Failed")
            self.toast_overlay.add_toast(toast)

    def on_save_as(self, action, param):
        selected_page = self.tab_view.get_selected_page()
        if not selected_page: return
        view = selected_page.get_child()
        if not hasattr(view, 'store'): return
        
        dialog = Gtk.FileChooserNative(
            title="Save Annotated PDF As",
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE
        )
        
        filter_pdf = Gtk.FileFilter()
        filter_pdf.set_name("PDF Documents")
        filter_pdf.add_mime_type("application/pdf")
        dialog.add_filter(filter_pdf)
        
        try:
            orig_name = view.file.get_basename()
            suggested = orig_name.replace(".pdf", "") + "_annotated.pdf"
            dialog.set_current_name(suggested)
        except Exception:
            pass
        
        def on_response(d, response):
            if response == Gtk.ResponseType.ACCEPT:
                file = d.get_file()
                path = file.get_path()
                try:
                    view.store.save_to_pdf(view.file.get_path(), path)
                    toast = Adw.Toast.new(f"Saved to {file.get_basename()}")
                    self.toast_overlay.add_toast(toast)
                except Exception as e:
                    toast = Adw.Toast.new("Save Failed")
                    self.toast_overlay.add_toast(toast)
            d.destroy()
            
        dialog.connect("response", on_response)
        dialog.show()

    def on_export_pdf(self, action, param):
        selected_page = self.tab_view.get_selected_page()
        if not selected_page: return
        page = selected_page
        view = page.get_child()
        if not hasattr(view, 'store'): return
        
        dialog = Gtk.FileChooserNative(
            title="Export Flattened PDF",
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE
        )
        
        filter_pdf = Gtk.FileFilter()
        filter_pdf.set_name("PDF Documents")
        filter_pdf.add_mime_type("application/pdf")
        dialog.add_filter(filter_pdf)
        
        try:
            orig_name = view.file.get_basename()
            suggested = orig_name.replace(".pdf", "") + "_flattened.pdf"
            dialog.set_current_name(suggested)
        except Exception:
            pass
        
        def on_response(d, response):
            if response == Gtk.ResponseType.ACCEPT:
                file = d.get_file()
                path = file.get_path()
                
                from pdf_app.document.export import export_flattened_pdf
                success = export_flattened_pdf(view.file.get_path(), view.store, path)
                
                
                if success:
                    toast = Adw.Toast.new(f"Exported to {file.get_basename()}")
                    self.toast_overlay.add_toast(toast)
                else:
                    toast = Adw.Toast.new("Export Failed")
                    self.toast_overlay.add_toast(toast)
            d.destroy()
            
        dialog.connect("response", on_response)
        dialog.show()
        
    def on_sidebar_page_selected(self, sidebar, page_index):
        page = self.tab_view.get_selected_page()
        if page:
            view = page.get_child()
            if isinstance(view, PDFView):
                view.scroll_to_page(page_index)
                view.grab_focus()

    def on_toggle_sidebar(self, action, param):
        show = not self.split_view.get_show_sidebar()
        self.split_view.set_show_sidebar(show)
        action.set_state(GLib.Variant.new_boolean(show))

    def on_tab_changed(self, tab_view, param):
        page = self.tab_view.get_selected_page()
        
        if hasattr(self, 'current_view_signals') and self.current_view_signals:
            old_view, handler_ids = self.current_view_signals
            
            old_view.sidebar_visible = self.split_view.get_show_sidebar()
            
            for hid in handler_ids:
                try:
                    if old_view.handler_is_connected(hid):
                        old_view.disconnect(hid)
                except Exception:
                    pass
            self.current_view_signals = None

        if not page:
            self.split_view.set_sidebar(self.sidebar_placeholder)
            self.split_view.set_show_sidebar(False)
            
            self.action_toggle_sidebar.set_enabled(False)
                 
            self.page_label.set_text("")
            self.zoom_label.set_text("")
            self.header_separator.set_visible(False)
            return
            
        view = page.get_child()
        if isinstance(view, PDFView):
            if not getattr(view, 'sidebar', None) and view.document:
                view.sidebar = ThumbnailSidebar()
                view.sidebar.connect('page-selected', self.on_sidebar_page_selected)
                # Deferred: will be loaded later to avoid blocking the main loop
                GLib.timeout_add(3000, self._deferred_sidebar_load, view)
                
            if getattr(view, 'sidebar', None):
                self.action_toggle_sidebar.set_enabled(True)
                self.split_view.set_sidebar(view.sidebar)
                was_visible = getattr(view, 'sidebar_visible', False)
                self.split_view.set_show_sidebar(was_visible)
            else:
                self.action_toggle_sidebar.set_enabled(False)
                self.split_view.set_sidebar(self.sidebar_placeholder)
                self.split_view.set_show_sidebar(False)
            
            current_tool = getattr(view, 'tool_mode', 'select')
            self.update_ribbon_tool_state(current_tool)
            
            action_dual = self.lookup_action("view_dual")
            if action_dual:
                action_dual.set_state(GLib.Variant.new_boolean(getattr(view, 'is_dual_mode', False)))
                
            action_cont = self.lookup_action("view_continuous")
            if action_cont:
                action_cont.set_state(GLib.Variant.new_boolean(getattr(view, 'is_continuous', True)))
            
            h1 = view.connect('page-changed', self.on_view_page_changed)
            h2 = view.connect('zoom-changed', self.on_view_zoom_changed)
            self.current_view_signals = (view, [h1, h2])
            
            if view.document:
                self.update_header_info(view)
                
            self.header_separator.set_visible(True)
        else:
            self.split_view.set_sidebar(self.sidebar_placeholder)
            self.split_view.set_show_sidebar(False)
            self.action_toggle_sidebar.set_enabled(False)
            
            self.page_label.set_text("")
            self.zoom_label.set_text("")
            self.header_separator.set_visible(False)
            
            action_dual = self.lookup_action("view_dual")
            if action_dual:
                action_dual.set_state(GLib.Variant.new_boolean(False))
                
            action_cont = self.lookup_action("view_continuous")
            if action_cont:
                action_cont.set_state(GLib.Variant.new_boolean(True))

    def on_view_page_changed(self, view, page_index):
        active_page = self.tab_view.get_selected_page()
        if active_page and active_page.get_child() == view:
            if view.sidebar:
                 view.sidebar.select_page(page_index)
            self.update_header_info(view)

    def on_view_zoom_changed(self, view, scale):
        active_page = self.tab_view.get_selected_page()
        if active_page and active_page.get_child() == view:
            self.update_header_info(view)
            
    def update_header_info(self, view):
        n_pages = len(view.page_slots) if hasattr(view, 'page_slots') else 0
        if n_pages > 0:
            self.page_label.set_text(f"Page {view.current_page_index + 1} / {n_pages}")
            self.zoom_label.set_text(f"{int(view.scale * 100)}%")
        else:
            self.page_label.set_text("Loading...")
            self.zoom_label.set_text("")

    def on_view_dual_toggled(self, action, value):
        action.set_state(value)
        enabled = value.get_boolean()
        page = self.tab_view.get_selected_page()
        if page:
            view = page.get_child()
            if isinstance(view, PDFView):
                view.set_dual_page_mode(enabled)
                if view.sidebar:
                    view.sidebar.set_dual_mode(enabled)
                self.update_header_info(view)

    def on_view_continuous_toggled(self, action, value):
        action.set_state(value)
        enabled = value.get_boolean()
        page = self.tab_view.get_selected_page()
        if page:
            view = page.get_child()
            if isinstance(view, PDFView):
                view.set_continuous_scroll(enabled)
                self.update_header_info(view)
                
    def on_close_page(self, tab_view, page):
        view = page.get_child()
        if hasattr(view, 'store') and getattr(view.store, 'is_dirty', False):
            self.prompt_save_changes([page], close_app=False)
            return True
        return False
                
    def on_close_request(self, win):
        dirty_pages = []
        n = self.tab_view.get_n_pages()
        for i in range(n):
            page_wrapper = self.tab_view.get_nth_page(i)
            view = page_wrapper.get_child()
            if hasattr(view, 'store') and getattr(view.store, 'is_dirty', False):
                dirty_pages.append(page_wrapper)
        
        if not dirty_pages:
            return False 
        
        self.prompt_save_changes(dirty_pages, close_app=True)
        return True 

 

    def prompt_save_changes(self, dirty_pages, close_app=True):
        count = len(dirty_pages)
        
        if count == 1:
            page = dirty_pages[0]
            title = page.get_title()
            if title.startswith("* "): title = title[2:]
            
            msg = f"Save changes to '{title}' before closing?"
            heading = "Save Changes?"
        else:
            heading = "Unsaved Changes"
            msg = "The following documents have unsaved changes:"

        alert = Adw.MessageDialog(
            transient_for=self,
            heading=heading,
            body=msg
        )
        
        if count > 1:
            filenames = []
            for page in dirty_pages:
                t = page.get_title()
                if t.startswith("* "): t = t[2:]
                filenames.append(t)
            
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.set_margin_top(10)
            box.set_margin_bottom(10)
            
            list_text = "\n".join([f"• {name}" for name in filenames])
            lbl = Gtk.Label(label=list_text)
            lbl.set_xalign(0) # Left align
            lbl.add_css_class("body")
            
            box.append(lbl)
            alert.set_extra_child(box)
        
        alert.add_response("cancel", "Cancel")
        
        if count > 1:
            alert.add_response("discard", "Discard & Quit")
            alert.add_response("save", "Save All & Quit")
        else:
            alert.add_response("discard", "Discard")
            alert.add_response("save", "Save")
            
        alert.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        alert.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        
        def on_response(dlg, resp):
            if resp == "discard":
                if close_app:
                    try: self.disconnect_by_func(self.on_close_request)
                    except: pass
                    self.close()
                else:
                    page = dirty_pages[0] 
                    self.tab_view.close_page_finish(page, True)
                    
            elif resp == "save":
                for page in dirty_pages:
                    view = page.get_child()
                    if hasattr(view, 'store') and hasattr(view, 'file'):
                        try:
                            # Save annotations back into PDF (overwrite source)
                            src = view.file.get_path()
                            view.store.save_to_pdf(src, src)
                        except Exception:
                            pass
                
                if close_app:
                    try: self.disconnect_by_func(self.on_close_request)
                    except Exception: pass
                    self.close()
                else:
                    page = dirty_pages[0]
                    self.tab_view.close_page_finish(page, True)
            
            else: # Cancel
                 if not close_app:
                    # Explicitly reject the close request so AdwTabView resets state
                    page = dirty_pages[0]
                    self.tab_view.close_page_finish(page, False)
                    # Force update status to ensure * remains visible if needed
                    view = page.get_child()
                    if hasattr(view, 'store'):
                        self.update_tab_status(page, view.store.is_dirty)
            
            dlg.close()
                
        alert.connect("response", on_response)
        alert.present()

