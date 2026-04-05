from dataclasses import dataclass

@dataclass
class RenderContext:
    scale: float
    rotation: int = 0
    dpi: float = 72.0
    
    def __eq__(self, other):
        if not isinstance(other, RenderContext):
            return False
        return self.scale == other.scale and self.rotation == other.rotation and self.dpi == other.dpi

    def __hash__(self):
        return hash((self.scale, self.rotation, self.dpi))
