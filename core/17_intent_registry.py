"""Resolve stage 01's classification to its dedicated source model."""
import json
import re
from dataclasses import asdict

from core import paths as _paths
INTENT_CLASSES = _paths.INTENT_CLASSES
from core import schema as _schema
model_from_dict = _schema.model_from_dict
from core import task_loader as _task_loader
load_task = _task_loader.load_task
from core import verification as _verification
verify_extraction = _verification.verify_extraction


def classify_extraction(extracted):
    verify_extraction(extracted)
    entries = json.loads((INTENT_CLASSES / 'index.json').read_text(encoding='utf-8'))
    matches = [entry for entry in entries if entry['id'] == extracted.intent]
    if len(matches) != 1 or not re.fullmatch(r'[a-z][a-z0-9_]*', extracted.intent):
        raise ValueError(f'意图类型未注册或重复：{extracted.intent}')
    path = INTENT_CLASSES / f'{extracted.intent}.py'
    if path.is_symlink():
        raise ValueError('意图类型必须位于本地类型目录内')
    module = load_task(path)
    return model_from_dict(getattr(module, matches[0]['model']), asdict(extracted))
