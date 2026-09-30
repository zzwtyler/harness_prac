"""Explicit task contract and bounded execution budget."""
from dataclasses import dataclass, field
from core import permissions as _permissions
validate_model_url = _permissions.validate_model_url

DEFAULT_DETAIL_MODEL = 'qwen3.5:4b'
DEFAULT_DECISION_MODEL = 'tev1:4b'
DEFAULT_FALLBACK_MODEL = 'qwen3:8b'
DEFAULT_CONFIDENCE_THRESHOLD = 0.8

# Fixed sampling is part of the code fingerprint, not inherited from Modelfiles.
SAMPLING_OPTIONS = {'top_k': 20, 'top_p': 0.95, 'min_p': 0, 'seed': 0,
                    'presence_penalty': 0, 'frequency_penalty': 0, 'repeat_penalty': 1,
                    'num_ctx': 32768}


@dataclass(frozen=True)
class ExtractionTask:
    source_text: str
    model: str = DEFAULT_DETAIL_MODEL
    base_url: str = 'http://127.0.0.1:11434'
    think: bool = False
    max_attempts: int = 2
    timeout_seconds: float = 60
    decision_model: str = field(default=DEFAULT_DECISION_MODEL, kw_only=True)
    fallback_model: str = field(default=DEFAULT_FALLBACK_MODEL, kw_only=True)
    confidence_threshold: float = field(default=DEFAULT_CONFIDENCE_THRESHOLD, kw_only=True)
    cascade_enabled: bool = field(default=True, kw_only=True)

    def __post_init__(self):
        validate_model_url(self.base_url)
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 3:
            raise ValueError('max_attempts必须是1至3的整数')
        if type(self.timeout_seconds) not in (int, float) or not 0 < self.timeout_seconds <= 120:
            raise ValueError('单次请求超时必须在0至120秒之间')
        if not isinstance(self.source_text, str):
            raise ValueError('输入必须是文本')
        import math
        if (type(self.confidence_threshold) not in (int, float) or not math.isfinite(self.confidence_threshold)
                or not 0 <= self.confidence_threshold <= 1):
            raise ValueError('confidence_threshold必须为0至1的有限数值')
        if type(self.cascade_enabled) is not bool:
            raise ValueError('cascade_enabled必须为布尔值')
        for name in (self.model, self.decision_model, self.fallback_model):
            if not isinstance(name, str) or not name.strip() or len(name) > 128:
                raise ValueError('角色模型名称都必须是非空且不超过128字符的文本')
