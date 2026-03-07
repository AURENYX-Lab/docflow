# src/docflow/settings/models.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# -----------------------
# SettingsPaths
# -----------------------


@dataclass(frozen=True)
class SettingsPaths:
    settings_dir: Any  # Path-like


# -----------------------
# Categories
# -----------------------
class AreaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    priority: int
    hard: bool = False
    keywords: List[str]
    tags: List[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_nonempty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("areas[].id must be non-empty")
        return v

    @field_validator("keywords")
    @classmethod
    def _kw_nonempty(cls, v: List[str]) -> List[str]:
        if not v or not all(isinstance(x, str) and x.strip() for x in v):
            raise ValueError("areas[].keywords must be non-empty list of non-empty strings")
        return [x.strip() for x in v]


class CategoriesRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    never_default_correspondence: bool
    hard_overrides: List[str]


class CategoriesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    closed_world: bool
    areas: List[AreaConfig]

    @model_validator(mode="after")
    def _unique_ids(self) -> "CategoriesConfig":
        ids = [a.id for a in self.areas]
        if len(ids) != len(set(ids)):
            raise ValueError("categories.areas contains duplicate ids")
        if not self.areas:
            raise ValueError("categories.areas must not be empty")
        return self


# -----------------------
# DocTypes
# -----------------------
class DocTypeImplies(BaseModel):
    model_config = ConfigDict(extra="forbid")
    likely_area: Optional[str] = None
    status_default: Optional[str] = None
    expected_fields: List[str] = Field(default_factory=list)

    @field_validator("likely_area")
    @classmethod
    def _likely_area_strip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip()
        return v or None

    @field_validator("expected_fields")
    @classmethod
    def _expected_fields_clean(cls, v: List[str]) -> List[str]:
        # optional, aber wenn vorhanden: nur non-empty strings
        out: List[str] = []
        for x in v or []:
            s = str(x).strip()
            if s:
                out.append(s)
        return out


class DocTypeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    priority: int
    hard: bool = False
    keywords: List[str]
    tags: List[str] = Field(default_factory=list)
    implies: Optional[DocTypeImplies] = None

    @field_validator("id")
    @classmethod
    def _id_nonempty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("doctypes.types[].id must be non-empty")
        return v

    @field_validator("keywords")
    @classmethod
    def _kw_nonempty(cls, v: List[str]) -> List[str]:
        if not v or not all(isinstance(x, str) and x.strip() for x in v):
            raise ValueError(
                "doctypes.types[].keywords must be non-empty list of non-empty strings"
            )
        return [x.strip() for x in v]


class DocTypesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    closed_world: bool
    types: List[DocTypeConfig]

    @model_validator(mode="after")
    def _unique_ids(self) -> "DocTypesConfig":
        ids = [t.id for t in self.types]
        if len(ids) != len(set(ids)):
            raise ValueError("doctypes.types contains duplicate ids")
        if not self.types:
            raise ValueError("doctypes.types must not be empty")
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
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    extract: ExtractConfig = Field(alias="extraction")
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


class FilenameDatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prefer: str
    fallback: str


class FilenamesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: str = Field(alias="schema")
    limits: FilenameLimits
    fallbacks: FilenameFallbacks


# -----------------------
# Pipeline toggles
# -----------------------
class PipelineOCRConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool
    skip_if_text_quality_ok: bool = False


class PipelineSuggestConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    use_llm: bool
    llm_fallback_only: bool = False
    ollama_timeout_s: int


class ApprovalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["json_flag", "sidecar_file"]
    json_flag_field: Optional[str] = None
    json_flag_value: Optional[bool] = None
    sidecar_suffix: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "ApprovalConfig":
        if self.mode == "json_flag":
            if not self.json_flag_field or self.json_flag_value is None:
                raise ValueError(
                    "apply.approval json_flag requires json_flag_field + json_flag_value"
                )
        if self.mode == "sidecar_file":
            if not self.sidecar_suffix:
                raise ValueError("apply.approval sidecar_file requires sidecar_suffix")
        return self


class ObsidianConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vault_root: str
    notes_dir: str
    include_frontmatter: bool = True
    link_style: Literal["relative", "absolute"] = "relative"
    file_name_mode: Literal["pdf_name", "title"] = "pdf_name"


CollisionPolicy = Literal["fail", "suffix", "skip_if_same"]


class PipelineApplyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    require_human_verify: bool
    copy_instead_of_move: bool
    write_obsidian_note: bool
    collision_policy: CollisionPolicy
    audit_manifest: str
    obsidian: Optional[ObsidianConfig] = None
    approval: ApprovalConfig  # bewusst required, weil du "kein Autopilot" willst


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ocr: PipelineOCRConfig
    suggest: PipelineSuggestConfig
    apply: PipelineApplyConfig


# -----------------------
# Prompts
# -----------------------
class PromptSuggestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: str
    schema_rules: str
    task: str


class PromptJsonFixConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repair_instructions: str


class PromptsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suggest: PromptSuggestConfig
    jsonfix: PromptJsonFixConfig


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


class OcrmypdfConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    langs: str
    jobs: int
    output_type: OCR_OUTPUT_TYPE
    optimize: int
    clean: bool
    deskew: bool
    rotate_pages: bool
    extra_args: List[str] = Field(default_factory=list)


class OCRConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quality: OCRQualityConfig
    ocrmypdf: OcrmypdfConfig


# -----------------------
# Root Settings
# -----------------------


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    settings_dir: str
    paths: SettingsPaths
    categories: CategoriesConfig
    doctypes: DocTypesConfig
    heuristics: HeuristicsConfig
    filenames: FilenamesConfig
    pipeline: PipelineConfig
    prompts: PromptsConfig
    ocr: OCRConfig
    settings_sha256: str

    def allowed_area_ids(self) -> List[str]:
        areas = sorted(self.categories.areas, key=lambda a: (a.priority, a.id))
        return [a.id for a in areas]

    def allowed_doc_type_ids(self) -> List[str]:
        types_ = sorted(self.doctypes.types, key=lambda t: (t.priority, t.id))
        return [t.id for t in types_]

    @model_validator(mode="after")
    def _check_doctype_implies(self) -> "Settings":
        allowed_areas = set(self.allowed_area_ids())
        for dt in self.doctypes.types:
            if dt.implies and dt.implies.likely_area:
                la = dt.implies.likely_area
                if la not in allowed_areas:
                    raise ValueError(
                        f"doctypes.types[].implies.likely_area '{la}' is not a valid area id"
                    )
        return self
