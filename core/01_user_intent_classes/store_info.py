from dataclasses import dataclass
from typing import Literal

from core import models as _models
ExtractedInput = _models.ExtractedInput


@dataclass
class StoreInfoIntent(ExtractedInput):
    """Stage 01 source spans classified as store_info."""
    intent: Literal["store_info"]
