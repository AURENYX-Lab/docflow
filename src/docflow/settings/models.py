from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# -----------------------
# SettingsPaths
# -----------------------


@dataclass(frozen=True)
class SettingsPaths:
    settings_dir: "Any"  # Path-like (keeps core decoupled from pathlib in typing)


# -----------------------
# Categories
# -----------------------


class AreaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    priority: int
    hard: bool
    keywords: List[str]
    tags: List[str]

    @field_validator("id")
    @classmethod
    def _id_nonempty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("area.id must be non-empty")
        return v

    @field_validator("keywords")
    @classmethod
    def _keywords_nonempty(cls, v: List[str]) -> List[str]:
        if not v or not all(isinstance(x, str) and x.strip() for x in v):
            raise ValueError("area.keywords must be a non-empty list of non-empty strings")
        return [x.strip() for x in v]

    @field_validator("tags")
    @classmethod
    def _tags_ok(cls, v: List[str]) -> List[str]:
        if v is None:
            return []
        if not all(isinstance(x, str) and x.strip() for x in v):
            raise ValueError("area.tags must be list of non-empty strings")
        return [x.strip() for x in v]


class CategoriesRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    never_default_correspondence: bool
    hard_overrides: List[str]


class CategoriesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    areas: List[AreaConfig]
    rules: CategoriesRules

    @model_validator(mode="after")
    def _unique_area_ids(self) -> "CategoriesConfig":
        ids = [a.id for a in self.areas]
        if len(ids) != len(set(ids)):
            raise ValueError("categories.areas contains duplicate ids")
        return self


# -----------------------
# Heuristics
# -----------------------


class ExtractConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_chars: int
    front_pages: int
    dist_pages: int


class DateDetectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_year: int
    max_year: int


class AktenzeichenConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_length: int
    ignore_numeric_only: bool


class FristConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    one_month_triggers: List[str]


class SourceGuessRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    keywords: List[str]


class SourceGuessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: List[SourceGuessRule]


class HeuristicsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extract: ExtractConfig
    date_detection: DateDetectionConfig
    aktenzeichen: AktenzeichenConfig
    frist: FristConfig
    source_guess: SourceGuessConfig


# -----------------------
# Filenames
# -----------------------


class FilenameLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_total: int
    short_desc: int
    source: int
    status: int


class FilenameFallbacks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    short: str
    source: str
    status: str


class FilenamesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: str
    limits: FilenameLimits
    fallbacks: FilenameFallbacks


# -----------------------
# Prompts
# -----------------------


class SuggestPromptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: str
    user: str


class PromptsConfig(BaseModel):
    """
    Prompt-Bucket: keep strict keys, but allow adding new prompt groups later
    via explicit model expansion, not silently.
    """

    model_config = ConfigDict(extra="forbid")

    suggest: SuggestPromptConfig


# -----------------------
# OCR
# -----------------------

OCR_OUTPUT_TYPE = Literal["pdfa", "pdf", "none"]


class OCRQualityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages_cap: int
    sample_pct: float
    sample_min_pages: int
    min_text_pages: float
    min_chars_per_page: int
    min_words_per_page: int

    @field_validator("sample_pct")
    @classmethod
    def _pct_range(cls, v: float) -> float:
        if not (0.0 < v <= 1.0):
            raise ValueError("ocr.quality.sample_pct must be within (0.0, 1.0]")
        return v

    @field_validator("min_text_pages")
    @classmethod
    def _cov_range(cls, v: float) -> float:
        if not (0.0 < v <= 1.0):
            raise ValueError("ocr.quality.min_text_pages must be within (0.0, 1.0]")
        return v


class OCRConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    inbox_dir: str
    log_dir: str
    quarantine_dir: str

    langs: str
    jobs: int

    output_type: OCR_OUTPUT_TYPE
    optimize: int
    clean: bool
    deskew: bool
    rotate_pages: bool

    # where we keep tmp output (same dir recommended for atomic replace)
    tmp_suffix: str

    quality: OCRQualityConfig

    @field_validator("optimize")
    @classmethod
    def _optimize_range(cls, v: int) -> int:
        if v < 0 or v > 3:
            raise ValueError("ocr.optimize must be 0..3")
        return v

    @field_validator("tmp_suffix")
    @classmethod
    def _tmp_suffix_ok(cls, v: str) -> str:
        v = (v or "").strip()
        if not v or not v.startswith("."):
            raise ValueError("ocr.tmp_suffix must start with '.' (e.g. '.ocr_tmp')")
        return v


# -----------------------
# Pipeline toggles
# -----------------------


class PipelineOCRConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class PipelineSuggestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_llm: bool


class PipelineApplyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require_human_verify: bool
    copy_instead_of_move: bool
    write_obsidian_note: bool


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ocr: PipelineOCRConfig
    suggest: PipelineSuggestConfig
    apply: PipelineApplyConfig


# -----------------------
# Root Settings
# -----------------------


class Settings(BaseModel):
    """
    The validated settings object.
    settings_sha256 is injected by loader (not from YAML).
    """

    model_config = ConfigDict(extra="forbid")

    categories: CategoriesConfig
    heuristics: HeuristicsConfig
    filenames: FilenamesConfig
    pipeline: PipelineConfig
    prompts: PromptsConfig
    ocr: OCRConfig

    settings_sha256: str = Field(...)

    def allowed_area_ids(self) -> List[str]:
        areas = list(self.categories.areas)
        areas.sort(key=lambda a: (a.priority, a.id))
        return [a.id for a in areas]
