from dataclasses import dataclass
from core import execution_config as _execution_config

from core import business as _business
BUSINESS_PROMPT = _business.BUSINESS_PROMPT
BusinessResult = _business.BusinessResult
extract_result = _business.extract_result
format_result = _business.format_result


@dataclass
class SplitRequest(BusinessResult):
    requests: list[str]
    order_id: list[str]
    account_id: list[str]
    constraints: list[str]


FIELD_CATEGORIES = {'requests': ['request', 'issue'], 'order_id': ['order_id'], 'account_id': ['account_id'], 'constraints': ['constraint']}
SYSTEM_PROMPT = BUSINESS_PROMPT


def from_extraction(extracted) -> SplitRequest:
    return format_result(extracted, result_type=SplitRequest, field_categories=FIELD_CATEGORIES, expected_intent='multi_intent')


def analyze_task(user_request: str, *, model=_execution_config.DEFAULT_DETAIL_MODEL, decision_model=_execution_config.DEFAULT_DECISION_MODEL, fallback_model=_execution_config.DEFAULT_FALLBACK_MODEL, confidence_threshold=_execution_config.DEFAULT_CONFIDENCE_THRESHOLD, cascade_enabled=True, base_url="http://127.0.0.1:11434", think=False) -> SplitRequest:
    return extract_result(user_request, result_type=SplitRequest, field_categories=FIELD_CATEGORIES, expected_intent='multi_intent',
                          model=model, decision_model=decision_model, base_url=base_url, think=think,
                          fallback_model=fallback_model, confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
