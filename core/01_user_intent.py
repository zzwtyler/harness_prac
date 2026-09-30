"""Stage 01: classify the request and copy source spans into its intent type."""
from core import extraction as _extraction
EXTRACTION_PROMPT = _extraction.EXTRACTION_PROMPT
extract_user_input = _extraction.extract_user_input
from core import intent_registry as _intent_registry
classify_extraction = _intent_registry.classify_extraction
from core import models as _models
ExtractedInput = _models.ExtractedInput
from core import execution_config as _execution_config
DEFAULT_DETAIL_MODEL = _execution_config.DEFAULT_DETAIL_MODEL
DEFAULT_DECISION_MODEL = _execution_config.DEFAULT_DECISION_MODEL

UserIntentModel = ExtractedInput
SYSTEM_PROMPT = EXTRACTION_PROMPT


def normalize_task(user_request: str, *, model=DEFAULT_DETAIL_MODEL, decision_model=DEFAULT_DECISION_MODEL, base_url='http://127.0.0.1:11434',
                   think=False, max_attempts=2, timeout_seconds=60, on_attempt=None,
                   fallback_model=_execution_config.DEFAULT_FALLBACK_MODEL,
                   confidence_threshold=_execution_config.DEFAULT_CONFIDENCE_THRESHOLD, cascade_enabled=True) -> ExtractedInput:
    extracted = extract_user_input(user_request, model=model, decision_model=decision_model, base_url=base_url, think=think,
                                   max_attempts=max_attempts, timeout_seconds=timeout_seconds,
                                   on_attempt=on_attempt, fallback_model=fallback_model,
                                   confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
    return classify_extraction(extracted)
