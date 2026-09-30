"""Application-level capabilities; this is not an OS sandbox for Python code."""
from urllib.parse import urlsplit

CAPABILITIES = frozenset({'model.extract', 'format.intent', 'verify.result', 'save.result', 'load.checkpoint'})


def require(capability: str) -> None:
    if capability not in CAPABILITIES:
        raise PermissionError(f'未授权工具能力：{capability}')


def validate_model_url(base_url: str) -> None:
    url = urlsplit(base_url)
    if (url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1', '::1'}
            or url.username or url.password or url.query or url.fragment or url.path not in ('', '/')):
        raise PermissionError('仅允许本机HTTP Ollama服务；未授权向远程服务发送用户输入')
    try:
        url.port
    except ValueError as exc:
        raise PermissionError('模型服务端口无效') from exc
