from dataclasses import dataclass
from core import execution_config as _execution_config

from core import business as _business
BUSINESS_PROMPT = _business.BUSINESS_PROMPT
BusinessResult = _business.BusinessResult
extract_result = _business.extract_result
format_result = _business.format_result


@dataclass
class MenuAdvice(BusinessResult):
    preferences: list[str]
    dietary_constraints: list[str]
    request: list[str]


FIELD_CATEGORIES = {'preferences': ['preference'], 'dietary_constraints': ['dietary_constraint'], 'request': ['request']}
SYSTEM_PROMPT = BUSINESS_PROMPT


def from_extraction(extracted) -> MenuAdvice:
    return format_result(extracted, result_type=MenuAdvice, field_categories=FIELD_CATEGORIES, expected_intent='menu_advice')


def analyze_task(user_request: str, *, model=_execution_config.DEFAULT_DETAIL_MODEL, decision_model=_execution_config.DEFAULT_DECISION_MODEL, fallback_model=_execution_config.DEFAULT_FALLBACK_MODEL, confidence_threshold=_execution_config.DEFAULT_CONFIDENCE_THRESHOLD, cascade_enabled=True, base_url="http://127.0.0.1:11434", think=False) -> MenuAdvice:
    return extract_result(user_request, result_type=MenuAdvice, field_categories=FIELD_CATEGORIES, expected_intent='menu_advice',
                          model=model, decision_model=decision_model, base_url=base_url, think=think,
                          fallback_model=fallback_model, confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
