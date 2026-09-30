"""Expose semantic Python imports for the numbered files in this directory.

Use ``from core import context`` to load ``03_context.py``. The numeric prefix
organizes source files; dependencies still use readable Python identifiers.
"""
from importlib import import_module
from pathlib import Path
import sys

_DIRECTORY = Path(__file__).resolve().parent
_EXPORTS = {
    'SchemaModel': ('schema', 'SchemaModel'),
    'schema_field': ('schema', 'schema_field'),
    'HarnessStage': ('stage', 'HarnessStage'),
    'StageRegistry': ('stage', 'StageRegistry'),
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name in _EXPORTS:
        module_name, attribute = _EXPORTS[name]
        value = getattr(__getattr__(module_name), attribute)
    else:
        if not name.isidentifier() or name.startswith('_'):
            raise AttributeError(name)
        matches = list(_DIRECTORY.glob(f'[0-9][0-9]_{name}.py'))
        if len(matches) != 1:
            raise AttributeError(f'编号模块不存在或重复：{name}')
        value = import_module(f'.{matches[0].stem}', __name__)
        # Preserve one module identity for tools that resolve dotted targets.
        sys.modules[f'{__name__}.{name}'] = value
    globals()[name] = value
    return value
