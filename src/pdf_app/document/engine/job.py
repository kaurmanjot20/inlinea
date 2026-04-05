from dataclasses import dataclass, field
from typing import Any
from .context import RenderContext

class RenderPriority:
    VISIBLE = 0
    PRELOAD = 1
    THUMBNAIL = 2

@dataclass(order=True)
class RenderTextureJob:
    priority: int
    timestamp: float
    uri: str = field(compare=False)
    page_index: int = field(compare=False)
    context: RenderContext = field(compare=False)
    callback: Any = field(compare=False)
    token: list = field(compare=False)
