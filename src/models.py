"""Pydantic data models matching the exact output schemas required."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class PricingModel(str, Enum):
    FREE = "FREE"
    FREEMIUM = "FREEMIUM"
    PAID = "PAID"
    ENTERPRISE = "ENTERPRISE"


class Source(BaseModel):
    name: str
    url: str


class StartupContent(BaseModel):
    entityName: str
    employeeCount: Optional[int] = None
    description: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    founded_year: Optional[int] = None


class StartupRecord(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "STARTUP"
    source: Source
    content: StartupContent
    collectedAt: datetime = Field(default_factory=datetime.utcnow)


class ProductContent(BaseModel):
    startupName: str
    productName: Optional[str] = None
    pricingModel: Optional[PricingModel] = None
    description: Optional[str] = None
    website: Optional[str] = None
    category: Optional[str] = None


class ProductRecord(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "PRODUCT"
    source: Source
    content: ProductContent
    collectedAt: datetime = Field(default_factory=datetime.utcnow)


class PaperContent(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    paper_url: str
    github_url: Optional[str] = None
    github_stars: Optional[int] = None
    published_date: Optional[datetime] = None
    abstract: Optional[str] = None


class PaperRecord(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "RESEARCH_PAPER"
    source: Source
    content: PaperContent
    collectedAt: datetime = Field(default_factory=datetime.utcnow)


class JobContent(BaseModel):
    company: str
    title: Optional[str] = None
    date: Optional[datetime] = None
    is_remote: bool = False
    role_family: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None


class JobRecord(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "JOB"
    source: Source
    content: JobContent
    collectedAt: datetime = Field(default_factory=datetime.utcnow)


class NewsContent(BaseModel):
    title: str
    author: Optional[str] = None
    date: Optional[datetime] = None
    full_text: Optional[str] = None
    summary: Optional[str] = None
    category: Optional[str] = None


class NewsRecord(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "NEWS"
    source: Source
    content: NewsContent
    collectedAt: datetime = Field(default_factory=datetime.utcnow)


class EntityMapping(BaseModel):
    raw_name: str
    canonical_name: str
    confidence: float
    source: str
    record_type: str
