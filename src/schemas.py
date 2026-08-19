from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from uuid import uuid5, NAMESPACE_URL

class Source(BaseModel):
    name: str
    url: str

class Entity(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    entity_type: str
    name: str
    description: str = ""
    url: str = ""
    categories: list[str] = Field(default_factory=list)
    source: Source
    collected_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def stable_id(cls, entity_type: str, url: str = "", name: str = "") -> str:
        key = f"{entity_type.lower()}::{url.strip().lower() or name.strip().lower()}"
        return str(uuid5(NAMESPACE_URL, key))

class ModelEntity(Entity):
    entity_type: Literal["MODEL"] = "MODEL"
    license: str | None = None
    modalities: list[str] = Field(default_factory=list)
    provider: str | None = None

class RepositoryEntity(Entity):
    entity_type: Literal["REPOSITORY"] = "REPOSITORY"
    stars: int | None = None
    primary_language: str | None = None
    last_updated: datetime | None = None

class MCPServerEntity(Entity):
    entity_type: Literal["MCP"] = "MCP"
    installation_methods: list[str] = Field(default_factory=list)
    runtime_requirements: list[str] = Field(default_factory=list)

class CompanyEntity(Entity):
    entity_type: Literal["COMPANY"] = "COMPANY"
    founding_year: int | None = None
    industry_sector: str | None = None
    headquarters: str | None = None
    employee_count: int | None = None

class ProductEntity(Entity):
    entity_type: Literal["PRODUCT"] = "PRODUCT"
    startup_name: str | None = None
    pricing_model: Literal["FREE", "FREEMIUM", "PAID", "ENTERPRISE"] | None = None

class ResearchPaperEntity(Entity):
    entity_type: Literal["RESEARCH_PAPER"] = "RESEARCH_PAPER"
    title: str
    authors: list[str] = Field(default_factory=list)
    paper_url: str
    github_url: str | None = None
    github_stars: int | None = None
    published_date: datetime | None = None

class JobEntity(Entity):
    entity_type: Literal["JOB"] = "JOB"
    company: str
    date: datetime
    is_remote: bool = False
    role_family: str = "Other"

class NewsEntity(Entity):
    entity_type: Literal["NEWS"] = "NEWS"
    published_at: datetime
    content: str = ""

class Relationship(BaseModel):
    source_id: str
    source_name: str
    relation: str
    target_id: str
    target_name: str
    evidence_url: str
    confidence: float = 1.0
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
