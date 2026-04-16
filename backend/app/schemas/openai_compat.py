"""Pydantic schemas for OpenAI-compatible /v1/audio/transcriptions responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WordItem(BaseModel):
    """A single word with timing in verbose_json output."""

    word: str
    start: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")


class SegmentItem(BaseModel):
    """A single segment with timing in verbose_json output."""

    id: int
    seek: float = 0.0
    start: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")
    text: str
    tokens: list[int] = Field(default_factory=list)
    temperature: float = 0.0
    avg_logprob: float = 0.0
    compression_ratio: float = 0.0
    no_speech_prob: float = 0.0


class VerboseJsonResponse(BaseModel):
    """OpenAI-compatible verbose_json response for /v1/audio/transcriptions."""

    task: str = "transcribe"
    language: str = "en"
    duration: float = Field(description="Duration in seconds")
    text: str
    words: list[WordItem] = Field(default_factory=list)
    segments: list[SegmentItem] = Field(default_factory=list)


class SimpleJsonResponse(BaseModel):
    """OpenAI-compatible json response for /v1/audio/transcriptions."""

    text: str


class ModelObject(BaseModel):
    """A single model object in the OpenAI /v1/models response."""

    id: str
    object: str = "model"
    created: int = Field(description="Unix timestamp of model creation")
    owned_by: str = "nanoscribe"


class ModelListResponse(BaseModel):
    """OpenAI-compatible response for GET /v1/models."""

    object: str = "list"
    data: list[ModelObject]
