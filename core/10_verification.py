"""Verify source, scope and projections; this is not semantic truth verification."""
from dataclasses import asdict
import math
from core import context, models, schema, permissions, intent_details


VALIDATION_NOTES = {
    'schema_invalid': '上次标注未符合Schema或当前业务的子类型/标签约束；按给定Schema重新核对，不添加新字段。',
    'unit_count': 'unit数量须符合固定Decision；只保留真实独立目标，不能把参数/规则另建目标或重复同一目标来凑数。',
    'source_scope': '每个unit只能引用当前原文clause_id，selection必须由自身clause_ids承载，不借用其它unit信息。',
    'empty_annotations': '已宣称的目标没有任何标注；复查原文动作/问题/实际异常及其专用信息，不补造事实或改变路线。',
    'missing_request': '本unit缺request。仅在原文确有动作、问题或实际异常隐含求助证据时选择request，并保留同片段专用标签；身份、编号、纯参数、规则、假设或否定异常不能为过关而贴request。不补造、不重复目标、不改Decision。',
}


def validation_feedback(code, previous_attempt, unit_index=None):
    if code not in VALIDATION_NOTES or type(previous_attempt) is not int or not 1 <= previous_attempt <= 3:
        raise ValueError('校验反馈必须使用白名单诊断码与有效尝试编号')
    if unit_index is not None and (type(unit_index) is not int or not 0 <= unit_index < 16):
        raise ValueError('校验反馈unit编号无效')
    return {'code': code, 'message': VALIDATION_NOTES[code], 'previous_attempt': previous_attempt,
            'unit_id': f'intent_{unit_index}' if unit_index is not None else None}


class AnnotationValidationError(ValueError):
    def __init__(self, code, message, unit_index=None):
        super().__init__(message)
        self.code = code
        self.unit_index = unit_index


def verify_confidence(value, details):
    if (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
            or not isinstance(details, models.ConfidenceDetails)):
        raise ValueError('confidence必须有合法数值和来源')
    if details.calibrated is not False or details.meaning != models.CONFIDENCE_MEANING or not details.model.strip():
        raise ValueError('confidence必须明确未校准及其决策token范围')
    if details.method == 'selected_option_token_probability':
        logprob = details.selected_logprob
        if (details.metadata_status != 'available' or type(logprob) not in (int, float)
                or not math.isfinite(logprob) or logprob > 0
                or not math.isclose(value, math.exp(logprob), rel_tol=1e-12, abs_tol=1e-12)):
            raise ValueError('confidence与所选token logprob不一致')
    elif details.method != 'gate_default' or details.metadata_status == 'available' or details.selected_logprob is not None or value != 0:
        raise ValueError('缺失/非法metadata只能使用显式0 gate默认值')


def verify_audit(extracted):
    if extracted.confidence is None and extracted.confidence_details is None and extracted.cascade is None:
        return  # Legacy formatter construction, never produced by the new runtime.
    verify_confidence(extracted.confidence, extracted.confidence_details)
    audit = extracted.cascade
    if not isinstance(audit, models.CascadeAudit):
        raise ValueError('提取须保存cascade审计')
    verify_confidence(audit.initial_confidence, audit.initial_confidence_details)
    if not math.isfinite(audit.threshold) or not 0 <= audit.threshold <= 1 or not audit.fallback_model.strip():
        raise ValueError('cascade阈值或角色配置无效')
    if audit.initial_decision is not None:
        models.verify_decision(audit.initial_decision)
    if audit.used:
        if not audit.enabled or audit.reason == 'none' or extracted.confidence_details.model != audit.fallback_model:
            raise ValueError('cascade升级记录与最终角色不一致')
        if audit.reason == 'low_confidence' and not (audit.initial_confidence < audit.threshold and audit.initial_confidence_details.metadata_status == 'available'):
            raise ValueError('低confidence升级原因不一致')
        if audit.reason == 'metadata_unavailable' and audit.initial_confidence_details.metadata_status == 'available':
            raise ValueError('缺metadata升级原因不一致')
        if (audit.reason == 'decision_invalid') != (audit.initial_decision is None):
            raise ValueError('初始Decision审核记录不一致')
    elif (audit.reason != 'none' or audit.initial_decision != extracted.decision
          or audit.initial_confidence != extracted.confidence or audit.initial_confidence_details != extracted.confidence_details):
        raise ValueError('未升级记录必须与当前Decision和confidence相同')
    elif audit.enabled and (extracted.confidence < audit.threshold or extracted.confidence_details.metadata_status != 'available'):
        raise ValueError('启用cascade时未升级记录不能跳过低分或缺metadata gate')


def verify_extraction(extracted):
    permissions.require('verify.result')
    schema.model_from_dict(models.ExtractedInput, asdict(extracted))
    verify_audit(extracted)
    manual_required, review_reasons = models.manual_review_policy(
        extracted.confidence, extracted.confidence_details, extracted.cascade)
    if extracted.manual_review_required is not manual_required or extracted.review_reasons != review_reasons:
        raise ValueError('人工核验标记和原因必须由最终confidence与metadata状态确定')
    allowed = {(c['start'], c['end'], c['text']) for c in context.source_clauses(extracted.source_text)}
    def span_key(span):
        if type(span.start) is not int or type(span.end) is not int:
            raise ValueError('原文位置必须是整数')
        return span.start, span.end, span.text
    if extracted.intent != intent_details.summarize(extracted.intents):
        raise ValueError('顶层分类与子意图列表不一致')
    if extracted.decision is not None:
        models.verify_decision(extracted.decision)
        if extracted.decision.input_kind != extracted.input_kind or extracted.decision.routing != extracted.intent:
            raise ValueError('提取结果不能改变固定Decision的输入性质或路线')
    if (extracted.input_kind == 'request') != bool(extracted.intents):
        raise ValueError('输入性质与子意图列表矛盾')
    if len(extracted.intents) > 16:
        raise ValueError('独立诉求超过16个')
    for index, unit in enumerate(extracted.intents):
        evidence = {span_key(span) for span in unit.evidence}
        if not evidence or not evidence.issubset(allowed) or len(evidence) != len(unit.evidence):
            raise ValueError('意图依据必须是唯一的完整原文片段')
        if any(span_key(k) not in evidence for k in unit.keywords):
            raise ValueError('关键词必须来自当前意图的原文依据')
        if not any(keyword.category == 'request' for keyword in unit.keywords):
            raise AnnotationValidationError('missing_request',
                f'intent_{index}缺少承载动作/问题/实际异常的request标签，结果不完整', index)
        keys = [(k.start, k.end, k.category) for k in unit.keywords]
        if len(keys) != len(set(keys)):
            raise ValueError('意图关键词重复')
        expected = intent_details.enrich(unit.intent, unit.subtype, unit.evidence, unit.keywords)
        if asdict(unit) != asdict(expected):
            raise ValueError('分层信息或待确认信息与原文选择不一致')
    if extracted.keywords != intent_details.merge_keywords(extracted.intents):
        raise ValueError('汇总关键词与各意图的信息不一致')


def verify_result(extracted, result, definition):
    permissions.require('verify.result')
    verify_extraction(extracted)
    data = asdict(result)
    schema.model_from_dict(definition.model_type, data)
    if data['source_text'] != extracted.source_text or data['keywords'] != asdict(extracted)['keywords']:
        raise ValueError('业务输出改变了用户来源或原文关键词')
    if data['intents'] != asdict(extracted)['intents']:
        raise ValueError('业务输出改变了子意图或信息归属')
    for name in ('confidence', 'confidence_details', 'cascade', 'manual_review_required', 'review_reasons'):
        if data[name] != asdict(extracted)[name]:
            raise ValueError('业务输出改变了confidence或cascade审计')
    allowed = {c['text'] for c in context.source_clauses(extracted.source_text)}
    for field, values in data.items():
        if field not in ('source_text', 'keywords', 'intents', 'confidence', 'confidence_details', 'cascade', 'manual_review_required', 'review_reasons') and any(value not in allowed for value in values):
            raise ValueError(f'{field} 包含用户输入之外的事实')
    expected = asdict(definition.module.from_extraction(extracted))
    if data != expected:
        raise ValueError('业务字段与intent映射不一致')
    return {'schema_valid': True, 'source_grounded': True, 'mapping_valid': True,
            'intent_scope_valid': True, 'semantic_verification': 'not_performed'}
