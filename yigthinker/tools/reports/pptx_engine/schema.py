"""
skill-pptx — Pydantic data models for Python engine.

All models use snake_case to match JSON protocol with TypeScript bridge.
"""

from typing import Optional, Union
from pydantic import BaseModel


# ─── Template Schema ───────────────────────────────────────────────────────────

class PlaceholderInfo(BaseModel):
    idx: int
    type: str  # "title", "body", "picture", "chart", "table", "subtitle", etc.
    name: str
    position: dict  # { left, top, width, height } in EMUs
    has_text: bool
    current_text: Optional[str] = None
    font_info: Optional[dict] = None  # { name, size, bold, color }


class SlideLayoutInfo(BaseModel):
    name: str
    index: int
    placeholders: list[PlaceholderInfo]
    master_name: str


class SlideInfo(BaseModel):
    index: int
    layout_name: str
    layout_index: int
    placeholders: list[PlaceholderInfo]
    shapes_count: int
    has_chart: bool
    has_table: bool
    has_notes: bool
    notes_text: Optional[str] = None


class ThemeInfo(BaseModel):
    colors: dict  # { dk1, dk2, lt1, lt2, accent1-6 }
    fonts: dict   # { major, minor }


class TemplateSchema(BaseModel):
    slide_count: int
    slide_width: int   # EMUs
    slide_height: int  # EMUs
    layouts: list[SlideLayoutInfo]
    slides: list[SlideInfo]
    theme: ThemeInfo
    warnings: list[str] = []


# ─── Slide Input (for createFromScratch / addSlide) ───────────────────────────

class SlideInput(BaseModel):
    layout: str  # "title", "title_content", "two_content", etc.
    title: Optional[str] = None
    subtitle: Optional[str] = None
    content: Optional[Union[str, list[str]]] = None
    notes: Optional[str] = None


class CreateFromScratchParams(BaseModel):
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    theme: str = "corporate"  # "dark", "light", "corporate", "minimal"
    slides: list[SlideInput]
    output_path: str


# ─── Content Update Plan (for pptx.updateSlides) ─────────────────────────────

class ChartSeries(BaseModel):
    name: str
    values: list[float]


class ChartData(BaseModel):
    categories: list[str]
    series: list[ChartSeries]


class TableData(BaseModel):
    headers: list[str]
    rows: list[list[Union[str, float, int, None]]]


class PlaceholderUpdate(BaseModel):
    placeholder_idx: int
    type: str  # "text", "chart_data", "image", "table"
    content: Union[str, dict, list]  # depends on type


class SlideUpdate(BaseModel):
    slide_index: int
    placeholder_updates: list[PlaceholderUpdate]


# ─── Comment ──────────────────────────────────────────────────────────────────

class CommentPosition(BaseModel):
    x: int = 100
    y: int = 100


class SlideComment(BaseModel):
    slide_index: int
    author: str
    text: str
    position: Optional[CommentPosition] = None


# ─── Note ─────────────────────────────────────────────────────────────────────

class SlideNote(BaseModel):
    slide_index: int
    text: str


# ─── Chart position ───────────────────────────────────────────────────────────

class ChartPosition(BaseModel):
    left: float = 1.0   # inches
    top: float = 1.5    # inches
    width: float = 8.0  # inches
    height: float = 4.5 # inches
