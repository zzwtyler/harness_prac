"""Bounded extraction orchestration, verification and explicit checkpoint recovery."""
from contextlib import nullcontext
from dataclasses import asdict
from pathlib import Path

from core import context as _context
prepare_context = _context.prepare_context
build_intent_context = _context.build_intent_context
from core import models as _models
ExtractedInput = _models.ExtractedInput
from core import task_registry as _task_registry
TaskRegistry = _task_registry.TaskRegistry
from core import permissions as _permissions
require = _permissions.require
from core import planning as _planning
EXECUTION_PLAN = _planning.EXECUTION_PLAN
from core import schema as _schema
model_from_dict = _schema.model_from_dict
from core import state as _state
ResultStore = _state.ResultStore
RunState = _state.RunState
from core import execution_config as _execution_config
ExtractionTask = _execution_config.ExtractionTask
DEFAULT_DETAIL_MODEL = _execution_config.DEFAULT_DETAIL_MODEL
DEFAULT_DECISION_MODEL = _execution_config.DEFAULT_DECISION_MODEL
from core import verification as _verification
verify_extraction = _verification.verify_extraction
verify_result = _verification.verify_result

from core import paths as _paths
ROOT = _paths.ROOT
from core import checkpoints as _checkpoints
digest = _checkpoints.digest
execution_fingerprint = _checkpoints.execution_fingerprint
from core import task_loader as _task_loader
load_task = _task_loader.load_task
from core import intent_registry as _intent_registry
classify_extraction = _intent_registry.classify_extraction


def execute_task(user_request: str, *, project_context=None, model=DEFAULT_DETAIL_MODEL, decision_model=DEFAULT_DECISION_MODEL,
                 base_url='http://127.0.0.1:11434', think=False, output_directory=None,
                 max_attempts=2, timeout_seconds=60, resume=False,
                 fallback_model=_execution_config.DEFAULT_FALLBACK_MODEL,
                 confidence_threshold=_execution_config.DEFAULT_CONFIDENCE_THRESHOLD, cascade_enabled=True):
    # project_context is compatibility-only and is never evidence or model input.
    task = ExtractionTask(user_request, model, base_url, think, max_attempts, timeout_seconds,
                          decision_model=decision_model, fallback_model=fallback_model,
                          confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
    context = prepare_context(task.source_text)
    fingerprint = execution_fingerprint(task)
    store = ResultStore(Path(output_directory)) if output_directory is not None else None
    if resume and store is None:
        raise ValueError('恢复运行必须指定结果目录')

    with store.lock() if store else nullcontext():
        extracted = None
        if resume:
            state = RunState(**store.read('00_run_state'))
            if state.source_hash != context.source_hash or state.execution_hash != fingerprint:
                raise ValueError('当前输入、配置或代码与检查点不同，拒绝复用；请使用新的输出目录')
            state.resumed = True
            if state.extraction_hash:
                checkpoint = store.read('01_user_intent')
                if digest(checkpoint) != state.extraction_hash:
                    raise ValueError('检查点内容已改变，拒绝复用')
                extracted = model_from_dict(ExtractedInput, checkpoint)
                if extracted.source_text != user_request:
                    raise ValueError('检查点不属于当前输入')
                verify_extraction(extracted)
                extracted = classify_extraction(extracted)
        else:
            if store and any(p.name not in {'.run.lock', '00_direct_answer.json'} for p in store.directory.iterdir()):
                raise ValueError('结果目录非空；使用新目录或显式resume')
            state = RunState.new(context.source_hash, fingerprint)

        def persist():
            if store:
                store.write('00_run_state', state.to_dict())

        attempts_before = state.attempts
        def on_attempt(number):
            state.attempts = attempts_before + number
            persist()

        persist()
        try:
            for step in EXECUTION_PLAN:
                require(step.capability)
                state.step = step.name
                state.status = 'running'
                state.error = None
                persist()
                if step.name == 'extract':
                    if extracted is None:
                        extracted = load_task(ROOT / 'core/01_user_intent.py').normalize_task(user_request, model=model, decision_model=decision_model, base_url=base_url, think=think,
                                                       max_attempts=max_attempts, timeout_seconds=timeout_seconds,
                                                       on_attempt=on_attempt, fallback_model=fallback_model,
                                                       confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
                    verify_extraction(extracted)
                    state.extraction_hash = digest(asdict(extracted))
                    if store:
                        store.write('01_user_intent', asdict(extracted))
                    persist()
                elif step.name == 'route_and_format':
                    unit_context = build_intent_context(extracted)
                    definition = TaskRegistry().get(extracted.intent)
                    result = load_task(ROOT / 'core/02_task.py').build_task(extracted)
                    stage_name = f'{definition.order:02d}_{definition.id}'
                elif step.name == 'verify':
                    verification = verify_result(extracted, result, definition)
                elif step.name == 'save':
                    if store:
                        store.write(stage_name, asdict(result))
                        store.write('98_verification', verification)
            state.status = 'completed'
            persist()
            return {'intent': asdict(extracted), 'decision': asdict(extracted.decision), 'context': unit_context,
                    'confidence': extracted.confidence, 'confidence_details': asdict(extracted.confidence_details),
                    'cascade': asdict(extracted.cascade),
                    'manual_review_required': extracted.manual_review_required, 'review_reasons': list(extracted.review_reasons),
                    'stage': stage_name, 'result': asdict(result),
                    'verification': verification, 'state': state.to_dict()}
        except BaseException as exc:
            state.status = 'failed'
            state.error = f'{type(exc).__name__}: {exc}'[:500]
            try:
                persist()
            except OSError:
                pass
            raise


run_harness = execute_task


if __name__ == "__main__":
    from core import cli as _cli
    main = _cli.main
    main(execute_task)
