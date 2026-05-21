
import cairo
import gi
gi.require_version('Poppler', '0.18')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Poppler, Pango, PangoCairo

def export_flattened_pdf(original_pdf_path, annotation_store, output_path):
    try:
        if not original_pdf_path.startswith("file://"):
            uri = f"file://{original_pdf_path}"
        else:
            uri = original_pdf_path
            
        document = Poppler.Document.new_from_file(uri, None)
        n_pages = document.get_n_pages()
        
        surface = cairo.PDFSurface(output_path, 595, 842)
        context = cairo.Context(surface)
        
        for i in range(n_pages):
            page = document.get_page(i)
            w, h = page.get_size()
            
            surface.set_size(w, h)
            
            context.save()
            page.render_for_printing_with_options(context, Poppler.PrintFlags.DOCUMENT)
            context.restore()
            
            page_anns = annotation_store.get_for_page(i)
            
            if page_anns:
                draw_annotations(context, page_anns)
                
            surface.show_page()
            
        surface.finish()
        return True
        
    except Exception as e:
        return False

def draw_annotations(c, annotations):
    for ann in annotations:
        r, g, b, a = ann.color

        if ann.type == 'highlight':
            # Use MULTIPLY operator to match native PDF highlight appearance
            c.set_operator(cairo.OPERATOR_MULTIPLY)
            c.set_source_rgba(r, g, b, 0.5)
            for rect in ann.rects:
                x, y, w, h = rect
                c.rectangle(x, y, w, h)
                c.fill()
            c.set_operator(cairo.OPERATOR_OVER)

        elif ann.type == 'underline':
            c.set_source_rgba(r, g, b, 1.0)
            c.set_line_width(1.5)
            for rect in ann.rects:
                x, y, w, h = rect
                c.move_to(x, y + h)
                c.line_to(x + w, y + h)
                c.stroke()

        elif ann.type == 'text':
            if not ann.rects: continue
            x, y, w, h = ann.rects[0]

            layout = PangoCairo.create_layout(c)
            layout.set_text(ann.content, -1)

            font_desc = Pango.FontDescription("Sans 14")
            layout.set_font_description(font_desc)

            c.set_source_rgba(r, g, b, 1.0)
            c.move_to(x, y)
            PangoCairo.show_layout(c, layout)

        elif ann.type == 'square':
            c.set_operator(cairo.OPERATOR_MULTIPLY)
            c.set_source_rgba(r, g, b, 0.5)
            for rect in ann.rects:
                x, y, w, h = rect
                c.rectangle(x, y, w, h)
                c.fill()
            c.set_operator(cairo.OPERATOR_OVER)
