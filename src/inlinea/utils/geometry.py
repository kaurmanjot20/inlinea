import gi
gi.require_version('Poppler', '0.18')
from gi.repository import Poppler, Gdk

class Rect:
    def __init__(self, x1, y1, x2, y2):
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)
    
    @property
    def width(self):
        return self.x2 - self.x1
    
    @property
    def height(self):
        return self.y2 - self.y1

    def to_poppler(self):
        r = Poppler.Rectangle()
        r.x1, r.y1, r.x2, r.y2 = self.x1, self.y1, self.x2, self.y2
        return r

    @staticmethod
    def from_poppler(r):
        return Rect(r.x1, r.y1, r.x2, r.y2)

    def contains(self, x, y):
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2
