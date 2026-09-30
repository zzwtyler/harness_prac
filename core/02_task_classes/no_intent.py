from dataclasses import dataclass
from core import execution_config as _execution_config
from core import business

SYSTEM_PROMPT = business.BUSINESS_PROMPT

@dataclass
class NoIntentTask(business.BusinessResult):
    pass


def from_extraction(extracted):
    return business.format_result(extracted, result_type=NoIntentTask, field_categories={}, expected_intent='no_intent')


def analyze_task(user_request: str, *, model=_execution_config.DEFAULT_DETAIL_MODEL, decision_model=_execution_config.DEFAULT_DECISION_MODEL, fallback_model=_execution_config.DEFAULT_FALLBACK_MODEL, confidence_threshold=_execution_config.DEFAULT_CONFIDENCE_THRESHOLD, cascade_enabled=True, base_url="http://127.0.0.1:11434", think=False):
    return business.extract_result(user_request, result_type=NoIntentTask, field_categories={}, expected_intent='no_intent',
                                   model=model, decision_model=decision_model, base_url=base_url, think=think,
                          fallback_model=fallback_model, confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
