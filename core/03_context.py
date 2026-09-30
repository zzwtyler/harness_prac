"""Bounded model input and source-isolated post-extraction context; no history."""
import hashlib
import json
import re
from dataclasses import dataclass, asdict

MAX_SOURCE_CHARS = 20_000
MAX_CLAUSES = 512
MAX_CONTEXT_BYTES = 16_000


def source_clauses(source: str) -> list[dict]:
    clauses = []
    cursor = 0
    # Keep ASCII commas surrounded by digits: 1,500 must not become 1 + 500.
    separators = re.finditer(r'[，。；;！？!?\n]|(?<!\d),|,(?!\d)', source)
    bounds = [match.span() for match in separators] + [(len(source), len(source))]
    for boundary_start, boundary_end in bounds:
        raw = source[cursor:boundary_start]
        text = raw.strip()
        if text:
            start = cursor + raw.index(text)
            clauses.append({'text': text, 'start': start, 'end': start + len(text)})
        cursor = boundary_end
    if not clauses:
        raise ValueError('请输入包含文字的当前请求')
    return clauses


@dataclass(frozen=True)
class PreparedContext:
    source_text: str
    clauses: list[dict]
    model_input: str
    source_hash: str


def prepare_context(source: str) -> PreparedContext:
    if not isinstance(source, str) or not source.strip():
        raise ValueError('当前用户输入不能为空')
    if len(source) > MAX_SOURCE_CHARS:
        raise ValueError('当前输入超过20,000字符；请分成独立请求，不进行静默截断或摘要')
    clauses = source_clauses(source)
    if len(clauses) > MAX_CLAUSES:
        raise ValueError('当前输入片段超过512个；请拆分请求')
    content = json.dumps({'source_text': source, 'clauses': [
        {'index': i, 'text': clause['text']} for i, clause in enumerate(clauses)]}, ensure_ascii=False)
    if len(content.encode('utf-8')) > MAX_CONTEXT_BYTES:
        raise ValueError('序列化后的输入超过16,000 UTF-8字节预算；请拆分请求，不自动截断')
    return PreparedContext(source, clauses, content, hashlib.sha256(source.encode()).hexdigest())


def build_intent_context(extracted):
    """Ready means verified structure/source, never verified facts or tool consent."""
    from core import verification, models
    models.verify_decision(extracted.decision)
    verification.verify_extraction(extracted)
    decision = asdict(extracted.decision) if extracted.decision is not None else None
    is_ask = decision is not None and decision['mode'] == 'ask'
    audit = asdict(extracted.cascade) if extracted.cascade is not None else None
    confidence_flags = list(extracted.review_reasons)
    units = []
    for index, unit in enumerate(extracted.intents):
        needs_review = ['semantic_verification_not_performed', *confidence_flags]
        if unit.not_observed:
            needs_review.append('not_observed_requires_review')
        if unit.verification_needed:
            needs_review.append('business_verification_pending')
        units.append({'id': f'intent_{index}', 'intent': unit.intent, 'subtype': unit.subtype,
                      'source_spans': [asdict(span) for span in unit.evidence],
                      'information': asdict(unit.information),
                      'not_observed': list(unit.not_observed),
                      'verification_needed': list(unit.verification_needed),
                      'needs_review': needs_review})
    return {'source_text': extracted.source_text, 'decision': decision,
            'confidence': extracted.confidence,
            'confidence_details': asdict(extracted.confidence_details) if extracted.confidence_details is not None else None,
            'cascade': audit,
            'manual_review_required': extracted.manual_review_required,
            'review_reasons': list(extracted.review_reasons),
            'status': 'needs_human_review' if extracted.manual_review_required else 'needs_clarification' if is_ask else 'ready' if units else 'no_intent',
            'units': units, 'semantic_verification': 'not_performed',
            'business_execution': 'not_performed',
            'clarification_question': '请说明你当前希望处理的目标。' if is_ask else None,
            'needs_review': [*(['goal_unclear'] if is_ask else ['semantic_verification_not_performed']), *confidence_flags]}
