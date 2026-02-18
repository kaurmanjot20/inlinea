import cairo
import gi
gi.require_version('Poppler', '0.18')
from gi.repository import Poppler, Gdk

def render_page_to_surface(page: Poppler.Page, scale: float = 1.0) -> cairo.ImageSurface:
    width, height = page.get_size()
    scaled_width = int(width * scale)
    scaled_height = int(height * scale)
    
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, scaled_width, scaled_height)
    context = cairo.Context(surface)
    
    context.set_source_rgb(1, 1, 1)
    context.paint()
    
    context.scale(scale, scale)
    
    page.render(context)
    
    return surface

def get_page_size(page: Poppler.Page, scale: float = 1.0):
    w, h = page.get_size()
    return w * scale, h * scale
