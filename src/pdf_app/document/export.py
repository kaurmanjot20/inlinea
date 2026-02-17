
import cairo
import gi
gi.require_version('Poppler', '0.18')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Poppler, Pango, PangoCairo

def export_flattened_pdf(original_pdf_path, annotation_store, output_path):
    try:
         # 1. Open Original PDF
        # Poppler.Document.new_from_file expects URI
        if not original_pdf_path.startswith("file://"):
            uri = f"file://{original_pdf_path}"
        else:
            uri = original_pdf_path
            
        document = Poppler.Document.new_from_file(uri, None)
        n_pages = document.get_n_pages()
        
        # 2. Create Surface - Dummy size initially
        surface = cairo.PDFSurface(output_path, 595, 842) # A4
        context = cairo.Context(surface)
        
        for i in range(n_pages):
            page = document.get_page(i)
            w, h = page.get_size()
            
            # Set size for THIS page
            surface.set_size(w, h)
            
            # Render PDF Page
            context.save()
            # Poppler renders 1:1 by default
            page.render(context)
            context.restore()
            
            # Draw Annotations
            # We need to filter annotations for this page index
            # Store logic: store.get_for_page(i)
            page_anns = annotation_store.get_for_page(i)
            
            if page_anns:
                draw_annotations(context, page_anns)
                
            surface.show_page()
            
        surface.finish()
        doc.save(output_path, garbage=4, deflate=True)
        return True
        
    except Exception as e:
        print(f"Error exporting PDF: {e}")
        import traceback
        traceback.print_exc()
        return False

def draw_annotations(c, annotations):
    for ann in annotations:
        r, g, b, a = ann.color
        c.set_source_rgba(r, g, b, a)
        
        if ann.type == 'highlight':
            for rect in ann.rects:
                x, y, w, h = rect
                c.rectangle(x, y, w, h)
                c.fill()
                
        elif ann.type == 'underline':
            c.set_line_width(1.0)
            for rect in ann.rects:
                x, y, w, h = rect
                # Bottom of rect
                c.move_to(x, y + h)
                c.line_to(x + w, y + h)
                c.stroke()
        
        elif ann.type == 'text':
            if not ann.rects: continue
            x, y, w, h = ann.rects[0]
            
            # Text rendering
            layout = PangoCairo.create_layout(c)
            layout.set_text(ann.content, -1)
            
            font_desc = Pango.FontDescription("Sans 14")
            layout.set_font_description(font_desc)
            
            c.move_to(x, y)
            PangoCairo.show_layout(c, layout)
