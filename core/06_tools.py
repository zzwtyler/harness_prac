"""The only model tool: select fixed labels and source indices. No shell/web/CRUD tools."""
from core import permissions as _permissions
require = _permissions.require
from core import runtime as _runtime
run_structured_chat = _runtime.run_structured_chat
run_decision_chat = _runtime.run_decision_chat


def select_decision(context, *, task):
    import json
    from core import instructions
    require('model.extract')
    content = json.dumps({'task': instructions.DECISION_TASK,
                          'state': {'source_text': context.source_text},
                          'options': instructions.DECISION_OPTIONS}, ensure_ascii=False)
    return run_decision_chat(content, system_prompt=instructions.DECISION_PROMPT,
                             model=task.decision_model, base_url=task.base_url,
                             timeout_seconds=task.timeout_seconds, with_confidence=True)


def select_source(context, *, result_type, instructions, task):
    require('model.extract')
    return run_structured_chat(context.model_input, result_type=result_type,
                               system_prompt=instructions, model=task.model,
                               base_url=task.base_url, think=task.think,
                               timeout_seconds=task.timeout_seconds)
