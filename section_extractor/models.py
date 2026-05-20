from typing import List
from pydantic import BaseModel


class Text(BaseModel):
    content: str


class Concept(BaseModel):
    label: str


class SectionExtraction(BaseModel):
    """Model for LLM output - does NOT include UUID to avoid confusion."""
    section_id: str
    label: str
    texts: List[Text]
    concepts: List[Concept]


class SectionExtractionWithUUID(BaseModel):
    """Internal model for storage - includes server-generated UUID."""
    section_id: str
    label: str
    texts: List[Text]
    concepts: List[Concept]
    uuid: str


class SectionExtractionResponse(BaseModel):
    sections: List[SectionExtractionWithUUID]


class ExtractRequest(BaseModel):
    text: str
