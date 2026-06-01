import cairo
import logging
import threading
import queue
import time
import gi
gi.require_version('Poppler', '0.18')
from gi.repository import GLib, Poppler

from .job import RenderTextureJob
from .context import RenderContext

logger = logging.getLogger(__name__)

_render_queue = queue.PriorityQueue()
_thread_local = threading.local()

def _get_thread_local_page(uri: str, page_index: int) -> Poppler.Page:
    if not hasattr(_thread_local, 'documents'):
        _thread_local.documents = {}
    if uri not in _thread_local.documents:
        _thread_local.documents[uri] = Poppler.Document.new_from_file(uri, None)
    return _thread_local.documents[uri].get_page(page_index)

def _render_page_to_surface(page: Poppler.Page, context: RenderContext) -> cairo.ImageSurface:
    width, height = page.get_size()
    render_scale = context.scale
    scaled_width = int(width * render_scale)
    scaled_height = int(height * render_scale)
    
    # Cap resolution to prevent OOM
    MAX_DIM = 4000
    if scaled_width > MAX_DIM:
        render_scale = MAX_DIM / width
        scaled_width = MAX_DIM
        scaled_height = int(height * render_scale)
    
    # Create target surface
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, scaled_width, scaled_height)
    cairo_ctx = cairo.Context(surface)
    
    # Fill white background
    cairo_ctx.set_source_rgb(1, 1, 1)
    cairo_ctx.paint()
    
    # Apply context transformations
    if context.rotation != 0:
        cairo_ctx.translate(scaled_width / 2, scaled_height / 2)
        cairo_ctx.rotate(context.rotation * (3.14159 / 180.0))
        cairo_ctx.translate(-scaled_width / 2, -scaled_height / 2)
        
    cairo_ctx.scale(render_scale, render_scale)
        
    # Render via Poppler
    page.render_for_printing_with_options(cairo_ctx, Poppler.PrintFlags.DOCUMENT)
    
    return surface

def _worker_loop():
    while True:
        job: RenderTextureJob = _render_queue.get()
        try:
            # Cancellation check before heavy work
            if job.token and job.token[0]:
                continue
                
            page = _get_thread_local_page(job.uri, job.page_index)
            # Poppler GIL release point:
            surface = _render_page_to_surface(page, job.context)
            
            # Final cancellation check before UI Handoff
            if not (job.token and job.token[0]):
                GLib.idle_add(job.callback, surface, job.context)
        except Exception:
            logger.exception("Render failed for %s (page %d)", job.uri, job.page_index)
            if not (job.token and job.token[0]):
                GLib.idle_add(job.callback, None, job.context)
        finally:
             _render_queue.task_done()

# Start Fixed-Size Pool
_NUM_THREADS = 4
for _ in range(_NUM_THREADS):
    threading.Thread(target=_worker_loop, daemon=True).start()

def dispatch_render_job(uri: str, page_index: int, context: RenderContext, priority: int, callback, token: list):
    job = RenderTextureJob(priority, time.time(), uri, page_index, context, callback, token)
    _render_queue.put(job)
