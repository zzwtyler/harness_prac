"""Routing protocol, scoped detail selection, and source-grounded intent units."""
from dataclasses import dataclass, field
from typing import Literal
from types import MappingProxyType

BusinessIntent = Literal['store_info', 'menu_advice', 'order_support', 'group_order', 'complaint',
                         'membership_help', 'campaign_brief', 'sales_analysis', 'other_request']
Intent = Literal['store_info', 'menu_advice', 'order_support', 'group_order', 'complaint',
                 'membership_help', 'campaign_brief', 'sales_analysis', 'multi_intent', 'other_request', 'no_intent']
InputKind = Literal['request', 'social', 'background', 'unclear']
Category = Literal['date', 'time', 'quantity', 'budget', 'location', 'pickup_or_delivery',
                   'order_id', 'current_status', 'preference', 'dietary_constraint', 'issue',
                   'impact', 'account_id', 'policy', 'period', 'metric', 'comparison',
                   'objective', 'audience', 'offer', 'channel', 'asset', 'constraint', 'request']
ReviewReason = Literal['decision_confidence_low', 'decision_confidence_metadata_unavailable']


@dataclass(frozen=True)
class Decision:
    option: Literal['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']
    input_kind: InputKind
    mode: Literal['infer', 'ask']
    routing: Intent


DECISIONS = MappingProxyType({
    'A': Decision('A', 'request', 'infer', 'store_info'),
    'B': Decision('B', 'request', 'infer', 'menu_advice'),
    'C': Decision('C', 'request', 'infer', 'order_support'),
    'D': Decision('D', 'request', 'infer', 'group_order'),
    'E': Decision('E', 'request', 'infer', 'complaint'),
    'F': Decision('F', 'request', 'infer', 'membership_help'),
    'G': Decision('G', 'request', 'infer', 'campaign_brief'),
    'H': Decision('H', 'request', 'infer', 'sales_analysis'),
    'I': Decision('I', 'request', 'infer', 'other_request'),
    'J': Decision('J', 'request', 'infer', 'multi_intent'),
    'K': Decision('K', 'social', 'infer', 'no_intent'),
    'L': Decision('L', 'background', 'infer', 'no_intent'),
    'M': Decision('M', 'unclear', 'ask', 'no_intent'),
})


def decision_from_letter(content):
    if not isinstance(content, str) or content.strip() not in DECISIONS:
        raise ValueError('决策模型必须只返回一个合法选项字母A至M')
    return DECISIONS[content.strip()]


def verify_decision(decision):
    if not isinstance(decision, Decision) or DECISIONS.get(decision.option) != decision:
        raise ValueError('Decision必须与Python固定选项映射一致')


CONFIDENCE_MEANING = 'Decision token probability or explicit gate default; uncalibrated, not semantic correctness or field accuracy.'


@dataclass(frozen=True)
class ConfidenceDetails:
    method: Literal['selected_option_token_probability', 'gate_default']
    model: str
    metadata_status: Literal['available', 'missing', 'invalid', 'ambiguous']
    selected_logprob: float | None
    calibrated: bool = False
    meaning: str = CONFIDENCE_MEANING


@dataclass(frozen=True)
class DecisionAssessment:
    decision: Decision
    confidence: float
    confidence_details: ConfidenceDetails


@dataclass(frozen=True)
class CascadeAudit:
    enabled: bool
    used: bool
    reason: Literal['none', 'low_confidence', 'metadata_unavailable', 'decision_invalid', 'annotation_invalid']
    threshold: float
    fallback_model: str
    initial_decision: Decision | None
    initial_confidence: float
    initial_confidence_details: ConfidenceDetails


def manual_review_policy(confidence, details, audit):
    """Handoff policy only; generic semantic diagnostics do not mandate a human."""
    reasons = []
    if confidence is not None and audit is not None and confidence < audit.threshold:
        reasons.append('decision_confidence_low')
    if details is None or details.metadata_status != 'available':
        reasons.append('decision_confidence_metadata_unavailable')
    return bool(reasons), reasons


@dataclass
class RoutedIntent:
    intent: BusinessIntent
    clause_indices: list[int]


@dataclass
class RoutingPlan:
    input_kind: InputKind
    intents: list[RoutedIntent]


@dataclass
class Selection:
    category: Category
    clause_index: int

    def __post_init__(self):
        if type(self.clause_index) is not int or self.clause_index < 0:
            raise ValueError('原文索引必须是非负整数，不能为布尔值')


@dataclass
class SourceSpan:
    text: str
    start: int
    end: int


@dataclass
class Keyword:
    category: Category
    text: str
    start: int
    end: int


@dataclass
class Information:
    common: list[Keyword]
    business: list[Keyword]
    operation: list[Keyword]


@dataclass
class IntentUnit:
    intent: BusinessIntent
    subtype: str
    evidence: list[SourceSpan]
    keywords: list[Keyword]
    information: Information
    not_observed: list[Category]
    verification_needed: list[str]


@dataclass
class ExtractedInput:
    source_text: str
    intent: Intent  # Derived routing summary; never chosen by the model.
    keywords: list[Keyword]  # Compatibility projection of all intent units.
    input_kind: InputKind = field(default='request', kw_only=True)
    intents: list[IntentUnit] = field(default_factory=list, kw_only=True)
    decision: Decision | None = field(default=None, kw_only=True)
    confidence: float | None = field(default=None, kw_only=True)
    confidence_details: ConfidenceDetails | None = field(default=None, kw_only=True)
    cascade: CascadeAudit | None = field(default=None, kw_only=True)
    manual_review_required: bool = field(default=True, kw_only=True)
    review_reasons: list[ReviewReason] = field(default_factory=lambda: ['decision_confidence_metadata_unavailable'], kw_only=True)
