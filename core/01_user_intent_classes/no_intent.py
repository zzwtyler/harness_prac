from dataclasses import dataclass
from typing import Literal
from core import models

@dataclass
class NoIntent(models.ExtractedInput):
    intent: Literal["no_intent"]
