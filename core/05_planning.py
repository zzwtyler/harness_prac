"""A fixed plan: the model never invents goals, actions, or additional tool calls."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PlanStep:
    order: int
    name: str
    capability: str


EXECUTION_PLAN = (
    PlanStep(1, 'extract', 'model.extract'),
    PlanStep(2, 'route_and_format', 'format.intent'),
    PlanStep(3, 'verify', 'verify.result'),
    PlanStep(4, 'save', 'save.result'),
)
