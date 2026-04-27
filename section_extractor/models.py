from typing import Literal
from pydantic import BaseModel


class SectionExtraction(BaseModel):
    section_id: str
    label: str
    section_enumeration: str
    section_type: Literal["Text", "Image"]
    confidence: float


class SectionExtractionResponse(BaseModel):
    sections: list[SectionExtraction]


class ExtractRequest(BaseModel):
    text: str