import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk

def check_icons():
    display = Gdk.Display.get_default()
    if not display:
        print("No display found, cannot check icons.")
        return

    theme = Gtk.IconTheme.get_for_display(display)
    icons_to_check = [
        "draw-square-symbolic",
        "draw-rectangle-symbolic",
        "draw-rectangle2-symbolic",
        "draw-text-symbolic",
        "insert-text-symbolic",
        "selection-mode-symbolic",
        "media-playback-stop-symbolic", # fallback square
        "non-existent-icon-123"
    ]

    print("Checking icons:")
    for icon_name in icons_to_check:
        if theme.has_icon(icon_name):
            print(f"[OK] {icon_name}")
        else:
            print(f"[MISSING] {icon_name}")

if __name__ == "__main__":
    check_icons()
