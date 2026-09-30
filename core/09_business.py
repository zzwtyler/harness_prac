"""Deterministic formatting of user-source keywords, never a second model answer."""
from dataclasses import dataclass, field

from core import models as _models
from core import extraction as _extraction
EXTRACTION_PROMPT = _extraction.EXTRACTION_PROMPT
ExtractedInput = _extraction.ExtractedInput
Keyword = _extraction.Keyword
extract_user_input = _extraction.extract_user_input
from core import execution_config as _execution_config
from core import intent_details as _intent_details
DEFAULT_DETAIL_MODEL = _execution_config.DEFAULT_DETAIL_MODEL
DEFAULT_DECISION_MODEL = _execution_config.DEFAULT_DECISION_MODEL


@dataclass
class BusinessResult:
    source_text: str
    keywords: list[Keyword]
    intents: list[_models.IntentUnit] = field(default_factory=list, kw_only=True)
    confidence: float | None = field(default=None, kw_only=True)
    confidence_details: _models.ConfidenceDetails | None = field(default=None, kw_only=True)
    cascade: _models.CascadeAudit | None = field(default=None, kw_only=True)
    manual_review_required: bool = field(default=True, kw_only=True)
    review_reasons: list[_models.ReviewReason] = field(default_factory=lambda: ['decision_confidence_metadata_unavailable'], kw_only=True)


BUSINESS_PROMPT = EXTRACTION_PROMPT


def format_result(extracted: ExtractedInput, *, result_type, field_categories, expected_intent):
    from core import verification as _verification
    verify_extraction = _verification.verify_extraction
    from core import permissions as _permissions
    require = _permissions.require
    require('format.intent')
    verify_extraction(extracted)
    if extracted.intent != expected_intent:
        raise ValueError(f'当前业务stage只消费{expected_intent}，不能消费{extracted.intent}')
    units = extracted.intents if expected_intent == 'multi_intent' else [
        unit for unit in extracted.intents if unit.intent == expected_intent]
    keywords = _intent_details.merge_keywords(units)
    values = {name: list(dict.fromkeys(k.text for k in keywords if k.category in categories))
              for name, categories in field_categories.items()}
    return result_type(source_text=extracted.source_text, keywords=extracted.keywords, intents=extracted.intents,
                       confidence=extracted.confidence, confidence_details=extracted.confidence_details,
                       cascade=extracted.cascade, manual_review_required=extracted.manual_review_required,
                       review_reasons=list(extracted.review_reasons), **values)


def extract_result(user_request, *, result_type, field_categories, expected_intent, model=DEFAULT_DETAIL_MODEL,
                   decision_model=DEFAULT_DECISION_MODEL,
                   fallback_model=_execution_config.DEFAULT_FALLBACK_MODEL,
                   confidence_threshold=_execution_config.DEFAULT_CONFIDENCE_THRESHOLD, cascade_enabled=True,
                   base_url='http://127.0.0.1:11434', think=False):
    extracted = extract_user_input(user_request, model=model, decision_model=decision_model, base_url=base_url, think=think,
        fallback_model=fallback_model, confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
    return format_result(extracted, result_type=result_type, field_categories=field_categories, expected_intent=expected_intent)
