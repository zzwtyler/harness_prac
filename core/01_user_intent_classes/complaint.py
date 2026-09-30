from dataclasses import dataclass
from typing import Literal

from core import models as _models
ExtractedInput = _models.ExtractedInput


@dataclass
class ComplaintIntent(ExtractedInput):
    """Stage 01 source spans classified as complaint."""
    intent: Literal["complaint"]
