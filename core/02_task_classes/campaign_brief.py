from dataclasses import dataclass
from core import execution_config as _execution_config

from core import business as _business
BUSINESS_PROMPT = _business.BUSINESS_PROMPT
BusinessResult = _business.BusinessResult
extract_result = _business.extract_result
format_result = _business.format_result


@dataclass
class CampaignBrief(BusinessResult):
    objective: list[str]
    period: list[str]
    audience: list[str]
    offer: list[str]
    channels: list[str]
    assets: list[str]
    budget: list[str]


FIELD_CATEGORIES = {'objective': ['objective'], 'period': ['period', 'date', 'time'], 'audience': ['audience'], 'offer': ['offer'], 'channels': ['channel'], 'assets': ['asset'], 'budget': ['budget']}
SYSTEM_PROMPT = BUSINESS_PROMPT


def from_extraction(extracted) -> CampaignBrief:
    return format_result(extracted, result_type=CampaignBrief, field_categories=FIELD_CATEGORIES, expected_intent='campaign_brief')


def analyze_task(user_request: str, *, model=_execution_config.DEFAULT_DETAIL_MODEL, decision_model=_execution_config.DEFAULT_DECISION_MODEL, fallback_model=_execution_config.DEFAULT_FALLBACK_MODEL, confidence_threshold=_execution_config.DEFAULT_CONFIDENCE_THRESHOLD, cascade_enabled=True, base_url="http://127.0.0.1:11434", think=False) -> CampaignBrief:
    return extract_result(user_request, result_type=CampaignBrief, field_categories=FIELD_CATEGORIES, expected_intent='campaign_brief',
                          model=model, decision_model=decision_model, base_url=base_url, think=think,
                          fallback_model=fallback_model, confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
