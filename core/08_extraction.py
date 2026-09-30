"""Tev decides a route; Qwen annotates its source; Python copies every span."""
import json
from dataclasses import asdict, replace
from core import models, instructions, context, intent_details
from core import execution_config as _execution_config
DEFAULT_DECISION_MODEL = _execution_config.DEFAULT_DECISION_MODEL
DEFAULT_DETAIL_MODEL = _execution_config.DEFAULT_DETAIL_MODEL
DEFAULT_FALLBACK_MODEL = _execution_config.DEFAULT_FALLBACK_MODEL
DEFAULT_CONFIDENCE_THRESHOLD = _execution_config.DEFAULT_CONFIDENCE_THRESHOLD

Intent = models.Intent
Category = models.Category
Selection = models.Selection
Keyword = models.Keyword
ExtractedInput = models.ExtractedInput
EXTRACTION_PROMPT = instructions.DECISION_TASK
source_clauses = context.source_clauses
prepare_context = context.prepare_context


def extract_user_input(source: str, *, model=DEFAULT_DETAIL_MODEL,
                       decision_model=DEFAULT_DECISION_MODEL, base_url='http://127.0.0.1:11434', think=False,
                       max_attempts=2, timeout_seconds=60, on_attempt=None,
                       fallback_model=DEFAULT_FALLBACK_MODEL,
                       confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD, cascade_enabled=True) -> ExtractedInput:
    from core import execution_config, tools, recovery, verification
    task = execution_config.ExtractionTask(source, model, base_url, think, max_attempts, timeout_seconds,
                                            decision_model=decision_model, fallback_model=fallback_model,
                                            confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
    prepared = prepare_context(source)
    current_task = task
    decision = None
    assessment = None
    initial_assessment = None
    feedback = None
    detail_attempts = 0
    total_attempts = 0
    allow_escalation = task.cascade_enabled

    class Escalation(Exception):
        def __init__(self, reason):
            self.reason = reason

    def record_attempt(_number):
        nonlocal total_attempts
        total_attempts += 1
        if on_attempt:
            on_attempt(total_attempts)

    def annotate():
        nonlocal detail_attempts
        units = []
        if decision.input_kind == 'request':
            routes = list(intent_details.BUSINESS) if decision.routing == 'multi_intent' else [decision.routing]
            scoped = {'source_text': source, 'decision': asdict(decision),
                      'businesses': {route: {
                          'subtypes': {s: intent_details.SUBTYPE_DESCRIPTIONS[s] for s in intent_details.SUBTYPES[route]},
                          'allowed_categories': {c: intent_details.CATEGORY_DESCRIPTIONS[c]
                                                 for c in intent_details.categories(route) if c != 'request'},
                      } for route in routes},
                      'clauses': [{'id': f'clause_{i}', 'text': clause['text']} for i, clause in enumerate(prepared.clauses)]}
            if feedback is not None:
                scoped['validation_feedback'] = feedback
            scoped_context = replace(prepared, model_input=json.dumps(scoped, ensure_ascii=False))
            detail_attempts += 1
            plan = tools.select_source(scoped_context,
                result_type=intent_details.structured_model(decision, prepared.clauses),
                instructions=instructions.DETAIL_PROMPT, task=current_task)
            if not 1 <= len(plan.intents) <= 16:
                raise verification.AnnotationValidationError('unit_count', '业务诉求必须为1至16个独立unit')
            if (decision.routing == 'multi_intent') != (len(plan.intents) > 1):
                raise verification.AnnotationValidationError('unit_count', '结构化unit数量与固定的单目标/多目标路线不一致')
            sources = {f'clause_{i}': clause for i, clause in enumerate(prepared.clauses)}
            for index, unit in enumerate(plan.intents):
                if not unit.clause_ids or len(set(unit.clause_ids)) != len(unit.clause_ids):
                    raise verification.AnnotationValidationError('source_scope', 'unit必须引用唯一的完整原文片段', index)
                if any(clause_id not in sources for clause_id in unit.clause_ids):
                    raise verification.AnnotationValidationError('source_scope', 'unit引用了当前输入之外的原文', index)
                owned = set(unit.clause_ids)
                keywords, seen = [], set()
                selected = [('request', clause_id) for clause_id in unit.request]
                selected.extend((selection.category, selection.clause_id) for selection in unit.selections)
                for category, clause_id in selected:
                    if clause_id not in owned:
                        raise verification.AnnotationValidationError('source_scope', '字段必须来自自身unit的原文依据', index)
                    key = (category, clause_id)
                    if key in seen:
                        continue
                    clause = sources[clause_id]
                    keywords.append(Keyword(category, clause['text'], clause['start'], clause['end']))
                    seen.add(key)
                if not keywords:
                    raise verification.AnnotationValidationError('empty_annotations',
                        f'intent_{index} 已判定为当前诉求但未提取任何字段，结果不完整', index)
                keywords.sort(key=lambda k: (k.start, k.category))
                evidence = sorted((models.SourceSpan(**sources[key]) for key in unit.clause_ids), key=lambda span: span.start)
                units.append(intent_details.enrich(unit.intent, unit.subtype, evidence, keywords))
        result = ExtractedInput(source, intent_details.summarize(units), intent_details.merge_keywords(units),
                                input_kind=decision.input_kind, intents=units, decision=decision)
        verification.verify_extraction(result)
        return result

    def attempt():
        nonlocal decision, assessment, initial_assessment, feedback
        if decision is None:
            try:
                assessment = tools.select_decision(prepared, task=current_task)
            except (ValueError, TypeError, KeyError):
                if allow_escalation:
                    raise Escalation('decision_invalid') from None
                raise
            decision = assessment.decision
            models.verify_decision(decision)
            if current_task is task:
                initial_assessment = assessment
            if allow_escalation and (assessment.confidence_details.metadata_status != 'available'
                                     or assessment.confidence < task.confidence_threshold):
                reason = ('low_confidence' if assessment.confidence_details.metadata_status == 'available'
                          else 'metadata_unavailable')
                raise Escalation(reason)
        try:
            return annotate()
        except (ValueError, TypeError, KeyError) as exc:
            if allow_escalation:
                raise Escalation('annotation_invalid') from None
            if decision.input_kind == 'request' and detail_attempts:
                code = exc.code if isinstance(exc, verification.AnnotationValidationError) else 'schema_invalid'
                unit_index = exc.unit_index if isinstance(exc, verification.AnnotationValidationError) else None
                feedback = verification.validation_feedback(code, detail_attempts, unit_index)
            raise

    reason = 'none'
    try:
        result = recovery.run_with_retries(attempt, max_attempts=task.max_attempts, on_attempt=record_attempt)
    except Escalation as escalation:
        reason = escalation.reason
        current_task = replace(task, model=task.fallback_model, decision_model=task.fallback_model)
        allow_escalation = False
        decision = assessment = feedback = None
        detail_attempts = 0
        result = recovery.run_with_retries(attempt, max_attempts=task.max_attempts, on_attempt=record_attempt)
    initial_details = (initial_assessment.confidence_details if initial_assessment else
                       models.ConfidenceDetails('gate_default', task.decision_model, 'invalid', None))
    audit = models.CascadeAudit(task.cascade_enabled, reason != 'none', reason, float(task.confidence_threshold),
        task.fallback_model, initial_assessment.decision if initial_assessment else None,
        initial_assessment.confidence if initial_assessment else 0.0, initial_details)
    manual_required, review_reasons = models.manual_review_policy(assessment.confidence, assessment.confidence_details, audit)
    result = replace(result, confidence=assessment.confidence,
                     confidence_details=assessment.confidence_details, cascade=audit,
                     manual_review_required=manual_required, review_reasons=review_reasons)
    verification.verify_extraction(result)
    return result
