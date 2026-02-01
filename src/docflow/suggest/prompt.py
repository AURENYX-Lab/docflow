# docflow/src/docflow/suggest/prompt.py
from dataclasses import dataclass
from typing import Dict, Any, Sequence
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docflow.settings import Settings


class PromptError(RuntimeError):
    pass


def _get(d: Dict[str, Any], key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        raise PromptError(f"prompts.yaml: missing/invalid key '{key}'")
    return v


@dataclass(frozen=True)
class SuggestPrompt:
    system: str
    schema_rules: str
    task: str

    @staticmethod
    def from_settings(settings: Settings) -> "SuggestPrompt":
        s = settings.prompts.suggest
        return SuggestPrompt(system=s.system, schema_rules=s.schema_rules, task=s.task)

    def render(
        self,
        *,
        input_pdf: str,
        extracted_text: str,
        allowed_areas: Sequence[str],
        allowed_doc_types: Sequence[str],
        schema: Dict[str, Any],
        heuristics_hint: Dict[str, Any],
    ) -> str:
        schema_min = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        hint_min = json.dumps(heuristics_hint, ensure_ascii=False, separators=(",", ":"))
        # Ein deterministischer User-Block (kein Template-Magie nötig)
        return (
            f"{self.schema_rules}\n\n"
            f"{self.task}\n\n"
            f"ALLOWED_AREAS: {', '.join(allowed_areas)}\n"
            f"ALLOWED_DOC_TYPES: {', '.join(allowed_doc_types)}\n"
            f"INPUT_PDF: {input_pdf}\n"
            f"JSON_SCHEMA: {schema_min}\n"
            f"HEURISTICS_HINT: {hint_min}\n"
            f"EXTRACTED_TEXT:\n{extracted_text}\n"
        )
