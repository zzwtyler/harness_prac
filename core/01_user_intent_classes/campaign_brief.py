from dataclasses import dataclass
from typing import Literal

from core import models as _models
ExtractedInput = _models.ExtractedInput


@dataclass
class CampaignBriefIntent(ExtractedInput):
    """Stage 01 source spans classified as campaign_brief."""
    intent: Literal["campaign_brief"]
