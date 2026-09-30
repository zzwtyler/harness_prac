from dataclasses import dataclass
from typing import Literal

from core import models as _models
ExtractedInput = _models.ExtractedInput


@dataclass
class SalesAnalysisIntent(ExtractedInput):
    """Stage 01 source spans classified as sales_analysis."""
    intent: Literal["sales_analysis"]
