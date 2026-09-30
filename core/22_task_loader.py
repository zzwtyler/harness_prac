"""Load numbered task files without putting web concerns into those files."""

from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path


def load_task(path: Path) -> types.ModuleType:
    # Both stage class directories intentionally contain the same filenames.
    # Keep their module namespaces separate so dataclass type hints stay valid.
    path = path.resolve()
    identity = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    module_name = f"stage_module_{path.stem}_{identity}"
    module = types.ModuleType(module_name)
    module.__file__ = str(path)
    sys.modules[module_name] = module
    try:
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module
