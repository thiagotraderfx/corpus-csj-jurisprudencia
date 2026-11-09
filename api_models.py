"""Schemas Pydantic para la API."""
from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    checks: dict
    missing: list


class StatsResponse(BaseModel):
    version: str
    docs: int
    chunks: int
    tipos: dict
    salas: dict
    years: dict
    embeddings: dict
    benchmark: dict
    raw_bytes: int
    md_files: int
    duplicates_sha256: int = 0


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    k: int = Field(5, ge=1, le=50)
    sala: Optional[str] = None
    tipo: Optional[str] = None
    year: Optional[int] = None


class SearchResult(BaseModel):
    chunk_id: str
    providencia: str
    section: str
    score: float
    md_url: str
    raw_url: Optional[str] = None
    text: str
    radicado: Optional[str] = None
    fecha: Optional[str] = None
    sala: Optional[str] = None
    ponente: Optional[str] = None
    tipo: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    k: int
    total_candidates: int
    latency_ms: int
    results: list[SearchResult]


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    k: int = Field(6, ge=1, le=20)
    model: Optional[str] = None
    temperature: float = Field(0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(1024, ge=64, le=4096)


class AskResponse(BaseModel):
    query: str
    answer: str
    sources: list[SearchResult]
    model_used: str
    provider: str
    latency_ms: int
    tokens_used: Optional[int] = None
    # Fase A.3-bis: campos de seguridad (opcionales)
    verified: Optional[bool] = None
    refused: Optional[bool] = None
    confidence: Optional[float] = None
    citations: Optional[list] = None
    unverified: Optional[list] = None
    reason: Optional[str] = None
    coverage_gap: Optional[bool] = None



class DocumentResponse(BaseModel):
    providencia: str
    id: Optional[str] = None
    radicado: Optional[str] = None
    fecha: Optional[str] = None
    sala: Optional[str] = None
    ponente: Optional[str] = None
    tipo: Optional[str] = None
    clase: Optional[str] = None
    tema: Optional[str] = None
    fuente_formal: Optional[str] = None
    md_path: str
    raw_path: Optional[str] = None
    raw_sha256: Optional[str] = None
    source_url: Optional[str] = None
    md_content: Optional[str] = None


class ProvidenciaSummary(BaseModel):
    providencia: str
    radicado: Optional[str] = None
    fecha: Optional[str] = None
    sala: Optional[str] = None
    ponente: Optional[str] = None
    tipo: Optional[str] = None
    md_path: str


class ListResponse(BaseModel):
    total: int
    page: int
    limit: int
    results: list[ProvidenciaSummary]


class ChunkResponse(BaseModel):
    chunk_id: str
    providencia: str
    section: str
    text: str
    char_start: int
    char_end: int
    md_url: str
    raw_url: Optional[str] = None
