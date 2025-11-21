from pydantic import BaseModel
from typing import List, Optional

class SubtitleSegment(BaseModel):
    start: float
    end: float
    text: str

class StyleConfig(BaseModel):
    font_size: int = 24
    font_color: str = "white"
    font_family: str = "Arial"
    bg_color: Optional[str] = None
    position: str = "bottom" 

class ChatRequest(BaseModel):
    session_id: str
    prompt: str

class VisualAsset(BaseModel):
    start: float
    end: float
    keyword: str 
    url: str   
