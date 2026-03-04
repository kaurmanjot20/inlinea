import cairo
import gi
gi.require_version('Poppler', '0.18')
from gi.repository import Poppler, Gdk

def render_page_to_surface(page: Poppler.Page, scale: float = 1.0) -> cairo.ImageSurface:
    width, height = page.get_size()
    scaled_width = int(width * scale)
    scaled_height = int(height * scale)
    
    # Cap resolution to prevent excessive memory usage on large zoom
    MAX_DIM = 2400
    if scaled_width > MAX_DIM:
        cap_scale = MAX_DIM / width
        scaled_width = MAX_DIM
        scaled_height = int(height * cap_scale)
        scale = cap_scale
    
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, scaled_width, scaled_height)
    context = cairo.Context(surface)
    
    context.set_source_rgb(1, 1, 1)
    context.paint()
    
    context.scale(scale, scale)
    
    page.render_for_printing_with_options(context, Poppler.PrintFlags.DOCUMENT)
    
    return surface

def get_page_size(page: Poppler.Page, scale: float = 1.0):
    w, h = page.get_size()
    return w * scale, h * scale
