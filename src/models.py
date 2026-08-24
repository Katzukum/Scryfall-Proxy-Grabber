"""Pydantic models shared across all modules."""

from enum import Enum
from pydantic import BaseModel, Field


class CardEntry(BaseModel):
    """A single parsed card line from a Moxfield-style deck export."""

    quantity: int = Field(ge=1, description="Number of copies")
    name: str = Field(description="Card name")
    set_code: str = Field(description="Set code (e.g., 'mh2')")
    collector_number: str = Field(description="Collector number within the set")
    raw_line: str = Field(default="", description="Original unparsed line")


class OutputFormat(str, Enum):
    """Output format for print setup."""

    PDF = "pdf"
    PNG = "png"


class PrintSettings(BaseModel):
    """Dimensions and layout settings for print output."""

    card_width_mm: float = Field(default=63.0, description="Card width in millimeters")
    card_height_mm: float = Field(default=88.0, description="Card height in millimeters")
    corner_radius_mm: float = Field(default=2.5, description="Corner radius in millimeters")
    padding_mm: float = Field(default=2.0, description="Padding between cards in millimeters")
    output_format: OutputFormat = Field(default=OutputFormat.PDF, description="Output file format")
    is_transformer: bool = Field(default=False, description="Whether to create two-sided transformer layout")


class CardSearchResult(BaseModel):
    """Result from a Scryfall card search."""

    name: str
    set_code: str
    collector_number: str
    image_url: str = Field(default="", description="Medium image URL")
    image_url_small: str = Field(default="", description="Small image URL")
    scryfall_uri: str = Field(default="", description="Link to Scryfall page")
    raw_json: dict = Field(default_factory=dict, description="Full Scryfall API response")


class LogMessage(BaseModel):
    """A log message to display in the UI console."""

    level: str = Field(default="INFO", description="Log level: INFO, WARN, ERROR")
    text: str = Field(description="Log message text")
