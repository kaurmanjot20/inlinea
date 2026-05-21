import re
from urllib.parse import urlparse
import gi
gi.require_version('Poppler', '0.18')
from gi.repository import Poppler

URL_REGEX = re.compile(r'https?://[^\s<>"]+|mailto:[^\s<>"]+')

def is_safe_url(uri: str) -> bool:
    if not uri:
        return False
    try:
        parsed = urlparse(uri)
        if parsed.scheme.lower() in ('http', 'https', 'mailto'):
            return True
        return False
    except Exception:
        return False

def extract_embedded_links(page: Poppler.Page) -> list:
    """Returns a list of dicts: [{'uri': '...', 'rects': [(x, y, w, h)]}]"""
    links = []
    try:
        page_w, page_h = page.get_size()
        mappings = page.get_link_mapping()
        for mapping in mappings:
            action = mapping.action
            if not action:
                continue
            
            # Poppler.ActionType.URI
            if action.type == Poppler.ActionType.URI:
                uri = action.uri.uri if hasattr(action.uri, 'uri') else None
                if not uri:
                    continue
                area = mapping.area
                # Poppler.LinkMapping uses bottom-left coordinates! Convert to top-left:
                x = area.x1
                y = page_h - area.y2
                w = area.x2 - area.x1
                h = area.y2 - area.y1
                # If negative heights or widths are given due to inversion, sanitize:
                if w < 0:
                    x += w
                    w = abs(w)
                if h < 0:
                    y += h
                    h = abs(h)
                rects = [(x, y, w, h)]
                links.append({"uri": uri, "rects": rects})
    except Exception:
        pass
    return links

def extract_text_links(page: Poppler.Page) -> list:
    """Extract URLs from text using regex and map them to text layout rectangles."""
    links = []
    try:
        text = page.get_text()
        if not text:
            return links
            
        success, layout = page.get_text_layout()
        if not success or not layout:
            return links
            
        for match in URL_REGEX.finditer(text):
            uri = match.group(0)
            start_idx = match.start()
            end_idx = match.end()
            
            if start_idx < 0 or end_idx > len(layout):
                continue
                
            # Aggregate rects by line to avoid a rect per character
            rects = []
            current_line_rect = None
            
            for i in range(start_idx, end_idx):
                rect = layout[i]
                if current_line_rect is None:
                    current_line_rect = [rect.x1, rect.y1, rect.x2, rect.y2]
                else:
                    # If roughly on the same line, merge horizontally
                    if abs(rect.y1 - current_line_rect[1]) < 5.0 and abs(rect.y2 - current_line_rect[3]) < 5.0:
                        current_line_rect[0] = min(current_line_rect[0], rect.x1)
                        current_line_rect[2] = max(current_line_rect[2], rect.x2)
                        current_line_rect[1] = min(current_line_rect[1], rect.y1)
                        current_line_rect[3] = max(current_line_rect[3], rect.y2)
                    else:
                        # New line
                        rects.append((
                            current_line_rect[0], 
                            current_line_rect[1], 
                            current_line_rect[2] - current_line_rect[0], 
                            current_line_rect[3] - current_line_rect[1]
                        ))
                        current_line_rect = [rect.x1, rect.y1, rect.x2, rect.y2]
                        
            if current_line_rect:
                rects.append((
                    current_line_rect[0], 
                    current_line_rect[1], 
                    current_line_rect[2] - current_line_rect[0], 
                    current_line_rect[3] - current_line_rect[1]
                ))
            
            links.append({"uri": uri, "rects": rects})
                
    except Exception:
        pass
    return links
