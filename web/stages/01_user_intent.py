from pathlib import Path

from core import HarnessStage
from core import task_loader as _task_loader
load_task = _task_loader.load_task


def build_stage() -> HarnessStage:
    task = load_task(Path(__file__).resolve().parents[2] / "core/01_user_intent.py")
    return HarnessStage(
        id="user_intent",
        order=1,
        title="01 · 用户意图归一化",
        description="Tev决定输入性质与路线，Qwen标注原文，再按独立目标保存信息。",
        headline="先识别客户需求，\n再进入业务分析。",
        intro="示例项目是虚构的“拾光咖啡”：Harness 担任门店客服与运营助理。输入一条顾客或店长的需求，检查它被归成哪种 intent。",
        input_label="原始用户请求",
        input_placeholder="例如：下周六公司活动需要 20 杯咖啡，预算 500 元，怎么订？",
        output_title="意图清样",
        action_label="运行意图归一化",
        field_labels={"source_text": "用户原文", "intent": "分类标签", "keywords": "原文关键词汇总", "input_kind": "输入性质", "intents": "各意图及分层信息", "decision": "固定路线决策"},
        presentation={"source_text": "primary", "intent": "code", "keywords": "object-list", "intents": "object-list", "input_kind": "code", "decision": "object"},
        examples=(
            ("顾客：团体订单", "下周六公司活动需要 20 杯咖啡，预算 500 元，想了解如何下单和能否配送。"),
            ("店长：销售分析", "请分析上周三家门店的销售表现，指出差异和可能需要跟进的问题。"),
        ),
        runner=task.normalize_task,
        model_type=task.UserIntentModel,
        system_prompt=task.SYSTEM_PROMPT,
    )
