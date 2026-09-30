from dataclasses import dataclass
from typing import Literal

from core import models as _models
ExtractedInput = _models.ExtractedInput


@dataclass
class GroupOrderIntent(ExtractedInput):
    """Stage 01 source spans classified as group_order."""
    intent: Literal["group_order"]
