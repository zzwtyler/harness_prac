from dataclasses import dataclass
from typing import Literal

from core import models as _models
ExtractedInput = _models.ExtractedInput


@dataclass
class MultiIntentIntent(ExtractedInput):
    """Stage 01 source spans classified as multi_intent."""
    intent: Literal["multi_intent"]
