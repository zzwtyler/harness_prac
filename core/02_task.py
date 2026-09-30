"""Stage 02: map stage 01 source spans into the matching structured task."""
from core import models as _models
ExtractedInput = _models.ExtractedInput
from core import task_registry as _task_registry
TaskRegistry = _task_registry.TaskRegistry
from core import verification as _verification
verify_extraction = _verification.verify_extraction


def build_task(user_intent: ExtractedInput):
    """Use only the previous stage's result; no model call or new facts."""
    verify_extraction(user_intent)
    definition = TaskRegistry().get(user_intent.intent)
    return definition.module.from_extraction(user_intent)
