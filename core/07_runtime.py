"""Ollama adapter shared by direct Python calls and the web service."""

from __future__ import annotations

import json
from dataclasses import asdict
from http.client import HTTPException
from typing import Any
from urllib import request

from core import schema as _schema
model_json_schema = _schema.model_json_schema
model_validate_json = _schema.model_validate_json
from core import stage as _stage
HarnessStage = _stage.HarnessStage
from core import permissions as _permissions
validate_model_url = _permissions.validate_model_url
from core import execution_config as _execution_config
DEFAULT_DECISION_MODEL = _execution_config.DEFAULT_DECISION_MODEL
DEFAULT_DETAIL_MODEL = _execution_config.DEFAULT_DETAIL_MODEL

# Explicit settings avoid inheriting different Modelfile sampling defaults.
# These constants are covered by the execution source fingerprint.
SAMPLING_OPTIONS = _execution_config.SAMPLING_OPTIONS


def _chat_payload(user_request, system_prompt, model, *, think, temperature, num_predict):
    return {'model': model, 'messages': [
        {'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_request}],
        'stream': False, 'think': think,
        'options': {**SAMPLING_OPTIONS, 'temperature': temperature, 'num_predict': num_predict}}


def _send_chat(payload, base_url, timeout_seconds, *, return_response=False):
    validate_model_url(base_url)
    if len(json.dumps({'messages': payload['messages'], 'format': payload.get('format')}, ensure_ascii=False).encode('utf-8')) > 24_000:
        raise ValueError('指令、Schema与输入超过24,000字节预算；拒绝隐式上下文截断')
    upstream = request.Request(f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    raw = read_model_response(upstream, timeout_seconds)
    if raw.get('done_reason') == 'length' or raw.get('done') is not True:
        raise ValueError('模型输出未完整结束或达到生成长度上限')
    return raw if return_response else raw['message']['content']


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PermissionError('模型请求禁止HTTP重定向')


def open_model_request(req, *, timeout):
    validate_model_url(req.full_url.removesuffix('/api/chat'))
    # Ignore environment proxies as well as redirects: current user text stays local.
    return request.build_opener(request.ProxyHandler({}), _NoRedirect()).open(req, timeout=timeout)


def read_model_response(upstream, timeout):
    try:
        with open_model_request(upstream, timeout=timeout) as response:
            content = response.read(4 * 1024 * 1024 + 1)
        if len(content) > 4 * 1024 * 1024:
            raise ValueError('模型响应超过4MB限制')
        return json.loads(content.decode('utf-8'))
    except HTTPException as exc:
        raise OSError(f'模型HTTP传输未完整完成：{type(exc).__name__}') from exc


def run_stage(stage: HarnessStage, user_request: str, *, model: str = DEFAULT_DETAIL_MODEL, base_url: str = "http://127.0.0.1:11434", think: bool = True, decision_model: str = DEFAULT_DECISION_MODEL,
              fallback_model=_execution_config.DEFAULT_FALLBACK_MODEL, confidence_threshold=_execution_config.DEFAULT_CONFIDENCE_THRESHOLD,
              cascade_enabled=True) -> tuple[dict[str, Any], Any]:
    if stage.runner is not None:
        result = stage.runner(user_request, model=model, decision_model=decision_model, base_url=base_url, think=think,
                              fallback_model=fallback_model, confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
        return {"message": {"content": json.dumps(asdict(result), ensure_ascii=False)}, "done": True}, result
    validate_model_url(base_url)
    payload = stage.make_ollama_payload(user_request, model=model, think=think, stream=False)
    upstream = request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    raw = read_model_response(upstream, 60)
    result = model_validate_json(stage.model_type, raw["message"]["content"])
    return raw, result


def run_structured_chat(
    user_request: str,
    *,
    result_type: type[Any],
    system_prompt: str,
    model: str = DEFAULT_DETAIL_MODEL,
    base_url: str = "http://127.0.0.1:11434",
    think: bool = True,
    timeout_seconds: float = 60,
) -> Any:
    """Run one structured Ollama request and return the typed dataclass result."""
    payload = _chat_payload(user_request, system_prompt, model, think=think, temperature=0.2, num_predict=4096)
    payload['format'] = model_json_schema(result_type)
    return model_validate_json(result_type, _send_chat(payload, base_url, timeout_seconds))


def run_decision_chat(user_request: str, *, system_prompt: str,
                      model: str = DEFAULT_DECISION_MODEL,
                      base_url: str = 'http://127.0.0.1:11434', timeout_seconds: float = 60,
                      with_confidence=False):
    """Tev uses its native letter protocol, without a JSON output format."""
    from core import models
    payload = _chat_payload(user_request, system_prompt, model, think=False, temperature=0, num_predict=8)
    payload['logprobs'] = True
    raw = _send_chat(payload, base_url, timeout_seconds, return_response=True)
    decision = models.decision_from_letter(raw['message']['content'])
    if not with_confidence:
        return decision
    confidence, details = selected_option_confidence(decision, raw.get('logprobs'), model)
    return models.DecisionAssessment(decision, confidence, details)


def selected_option_confidence(decision, logprobs, model):
    """Use only the selected ASCII letter token, never a top candidate or guess."""
    import math
    from core import models
    status = 'missing' if logprobs is None else 'invalid'
    if isinstance(logprobs, list):
        if len(logprobs) != 1:
            status = 'ambiguous'
        elif isinstance(logprobs[0], dict):
            entry = logprobs[0]
            try:
                finite_logprob = type(entry.get('logprob')) in (int, float) and math.isfinite(entry['logprob'])
            except OverflowError:
                finite_logprob = False
            if entry.get('token') != decision.option:
                status = 'ambiguous'
            elif (entry.get('bytes') == [ord(decision.option)]
                  and finite_logprob and entry['logprob'] <= 0
                  and isinstance(entry.get('bytes'), list)
                  and all(type(byte) is int for byte in entry['bytes'])):
                value = float(entry['logprob'])
                return math.exp(value), models.ConfidenceDetails(
                    'selected_option_token_probability', model, 'available', value)
    return 0.0, models.ConfidenceDetails('gate_default', model, status, None)
