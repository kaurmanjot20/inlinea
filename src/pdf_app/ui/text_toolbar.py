from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Pango', '1.0')


class TextFormattingToolbar(Gtk.Popover):
    def __init__(self, parent_widget, annotation, store, on_update):
        super().__init__()
        self.set_parent(parent_widget)
        self.annotation = annotation
        self.store = store
        self.on_update = on_update
        self.parent_widget = parent_widget

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(4)
        self.set_child(box)

        # Font Family
        font_list = self._get_system_fonts()
        self.font_model = Gtk.StringList.new(font_list)
        self.font_dropdown = Gtk.DropDown.new(self.font_model, None)
        self._select_font(self.annotation.font_family)
        self.font_dropdown.connect("notify::selected", self.on_font_changed)
        box.append(self.font_dropdown)

        # Font Size
        self.size_spin = Gtk.SpinButton.new_with_range(8, 72, 1)
        self.size_spin.set_value(self.annotation.font_size)
        self.size_spin.connect("value-changed", self.on_size_changed)
        box.append(self.size_spin)

        # Separator
        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Color
        self.color_button = Gtk.ColorDialogButton()
        color_dialog = Gtk.ColorDialog()
        self.color_button.set_dialog(color_dialog)
        rgba = Gdk.RGBA()
        r, g, b, a = self.annotation.color
        rgba.red, rgba.green, rgba.blue, rgba.alpha = r, g, b, 1.0
        self.color_button.set_rgba(rgba)
        self.color_button.connect("notify::rgba", self.on_color_changed)
        box.append(self.color_button)

        # Separator
        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Formatting toggles
        self.bold_btn = Gtk.ToggleButton(icon_name="format-text-bold-symbolic")
        self.bold_btn.set_active(self.annotation.bold)
        self.bold_btn.connect("toggled", self.on_style_toggled, 'bold')
        box.append(self.bold_btn)

        self.italic_btn = Gtk.ToggleButton(
            icon_name="format-text-italic-symbolic")
        self.italic_btn.set_active(self.annotation.italic)
        self.italic_btn.connect("toggled", self.on_style_toggled, 'italic')
        box.append(self.italic_btn)

        self.underline_btn = Gtk.ToggleButton(
            icon_name="format-text-underline-symbolic")
        self.underline_btn.set_active(self.annotation.underline)
        self.underline_btn.connect(
            "toggled", self.on_style_toggled, 'underline')
        box.append(self.underline_btn)

        # Separator
        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Delete
        self.delete_btn = Gtk.Button(icon_name="user-trash-symbolic")
        self.delete_btn.add_css_class("destructive-action")
        self.delete_btn.connect("clicked", self.on_delete_clicked)
        box.append(self.delete_btn)
        self.set_position(Gtk.PositionType.TOP)
        self.set_autohide(False)

    def _get_system_fonts(self):
        """Gets a list of all available fonts on the system"""
        try:
            font_map = PangoCairo.font_map_get_default()
            families = font_map.list_families()
            system_font_names = {f.get_name()
                                 for f in families if f.get_name()}
            fallback_fonts = {"Comfortaa", "cursive",
                              "Cantarell", "Sans", "Serif", "Monospace"}
            all_font_names = sorted(
                list(system_font_names.union(fallback_fonts)))
            return all_font_names if all_font_names else ["Sans"]
        except Exception as e:
            # Pango's default generic fallbacks
            return ["Comfortaa", "cursive", "Cantarell", "Sans", "Serif", "Monospace"]

    def _select_font(self, font_name):
        for i in range(self.font_model.get_n_items()):
            if self.font_model.get_string(i) == font_name:
                self.font_dropdown.set_selected(i)
                return
        # Default to 0 if not found
        self.font_dropdown.set_selected(0)

    def update_position(self, scale):
        if not self.annotation.rects:
            return
        x, y, w, h = self.annotation.rects[0]
        rect = Gdk.Rectangle()
        rect.x = int(x * scale)
        rect.y = int(y * scale)
        rect.width = int(w * scale)
        if rect.width < 10:
            rect.width = 10
        if rect.height < 10:
            rect.height = 10
        self.set_pointing_to(rect)

    def _record_style(self):
        return {
            'font_size': self.annotation.font_size,
            'font_family': self.annotation.font_family,
            'bold': self.annotation.bold,
            'italic': self.annotation.italic,
            'underline': self.annotation.underline
        }

    def on_font_changed(self, dropdown, pspec):
        idx = dropdown.get_selected()
        font_name = self.font_model.get_string(idx)
        if font_name != self.annotation.font_family:
            old_style = self._record_style()
            self.annotation.font_family = font_name
            self.store.record_style_change(self.annotation.id, old_style)
            self._notify_update()

    def on_size_changed(self, spin):
        size = int(spin.get_value())
        if size != self.annotation.font_size:
            old_style = self._record_style()
            self.annotation.font_size = size
            self.store.record_style_change(self.annotation.id, old_style)
            self._notify_update()

    def on_color_changed(self, button, pspec):
        rgba = button.get_rgba()
        new_color = (rgba.red, rgba.green, rgba.blue, 1.0)
        if new_color != self.annotation.color:
            self.store.record_color_change(
                self.annotation.id, self.annotation.color)
            self.annotation.color = new_color
            self._notify_update()

    def on_style_toggled(self, btn, style_name):
        active = btn.get_active()
        current_val = getattr(self.annotation, style_name)
        if current_val != active:
            old_style = self._record_style()
            setattr(self.annotation, style_name, active)
            self.store.record_style_change(self.annotation.id, old_style)
            self._notify_update()

    def on_delete_clicked(self, btn):
        self.store.remove(self.annotation.id)
        self.popdown()
        self._notify_update()

    def _notify_update(self):
        if self.on_update:
            self.on_update(self.annotation)
