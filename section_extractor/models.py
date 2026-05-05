from typing import List
from pydantic import BaseModel


class Text(BaseModel):
    content: str


class Tag(BaseModel):
    label: str


class SectionExtraction(BaseModel):
    section_id: str
    label: str
    texts: List[Text]
    tags: List[Tag]


class SectionExtractionResponse(BaseModel):
    sections: List[SectionExtraction]


class ExtractRequest(BaseModel):
    text: str
