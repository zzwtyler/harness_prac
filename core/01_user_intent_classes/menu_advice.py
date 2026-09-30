from dataclasses import dataclass
from typing import Literal

from core import models as _models
ExtractedInput = _models.ExtractedInput


@dataclass
class MenuAdviceIntent(ExtractedInput):
    """Stage 01 source spans classified as menu_advice."""
    intent: Literal["menu_advice"]
