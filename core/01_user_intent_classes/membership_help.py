from dataclasses import dataclass
from typing import Literal

from core import models as _models
ExtractedInput = _models.ExtractedInput


@dataclass
class MembershipHelpIntent(ExtractedInput):
    """Stage 01 source spans classified as membership_help."""
    intent: Literal["membership_help"]
