from dataclasses import dataclass
from typing import Literal

from core import models as _models
ExtractedInput = _models.ExtractedInput


@dataclass
class OrderSupportIntent(ExtractedInput):
    """Stage 01 source spans classified as order_support."""
    intent: Literal["order_support"]
