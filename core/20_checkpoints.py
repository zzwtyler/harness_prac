"""Fingerprints bind checkpoints to their input, settings and stage implementations."""
import hashlib
import json
from dataclasses import asdict
from core import paths as _paths
ROOT = _paths.ROOT
execution_sources = _paths.execution_sources


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def execution_fingerprint(task):
    sources = execution_sources()
    return digest({'settings': {k: v for k, v in asdict(task).items() if k != 'source_text'},
                   'code': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}})


