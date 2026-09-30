"""Project locations shared by loaders, checkpoints and evaluation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTENT_CLASSES = ROOT / 'core/01_user_intent_classes'
TASK_CLASSES = ROOT / 'core/02_task_classes'


def execution_sources():
    """Include numbered stages and all code/catalogs that affect execution."""
    sources = []
    for directory in ('harness', 'core'):
        sources.extend((ROOT / directory).rglob('*.py'))
        sources.extend((ROOT / directory).rglob('*.json'))
    return sorted(sources)
