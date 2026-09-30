from dataclasses import dataclass
from typing import Literal

from core import models as _models
ExtractedInput = _models.ExtractedInput


@dataclass
class OtherRequestIntent(ExtractedInput):
    """Stage 01 source spans classified as other_request."""
    intent: Literal["other_request"]
