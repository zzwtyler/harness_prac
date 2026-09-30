# Tev1 → Qwen3.5 分工：历史开发计划

**状态：早期分工与调试记录，协议已实现，本文不再作为待执行计划。** 代码/状态核对：2026-09-30。当前又增加了 qwen3:8b 级联和人工核验；完整现状以 [当前架构与协议](ARCHITECTURE.md) 为准，后续设计过程见 [confidence 历史计划](CONFIDENCE_CASCADE_PLAN.md)。本项目用于学习与实验。

## 当时目标

将用户原文交给 Tev1 做 input_kind、ask/infer 和 routing 决策，再由 Qwen3.5 选择来源片段与标签。Python 复制原文、校验并形成 Context/Task。这里只实现原文提取与交接，不实现 Agent 自主办理订单、退款或账号业务。

调试坚持通用文字定义、Schema 和来源约束，不用语义正则补标签，不将验收题或答案作为生产规则。保留否定、纠正、同业务独立目标以及 other 与其它业务并存。

## 已实现的协议

- `tev1:4b` 使用 `/api/chat` 的 task/state/options 数据；state 只有当前完整 source_text，不含已切开的 clauses，不使用 `/v1/systemone` 或自由 JSON 路由。
- 原生字母 A–M 对应九个单业务、multi、social、background、unclear/ask。去除首尾空白后只接受一个合法字母；Python 冻结映射 Decision，不从解释中挖取答案。
- infer 只理解原文，不补事实。ask 只表示目标或路线无法识别；最终 ask/social/background 不调用详情标注。not_observed 不会自动改成 ask，也不证明用户未提供。
- `qwen3.5:4b` 用一次 JSON wire 标注每个目标：intent、subtype、clause_ids、独立必答 request 数组和 selections。selections 排除 request；专用标签与 request 可引用同一来源，selections 可为空。
- 单目标标注不能改固定业务路线；multi 保留每个独立 unit，同业务不去重。每个目标须有自身 request 来源，字段只能引用自身 clause_ids；数量/Schema/来源失配拒绝，不在 Python 中猜标签或自动补标。
- Context 在合法提取后按 unit 保存来源、分层信息与核验提示；顶层兼容汇总不能替代逐目标交接。ready 只表示来源/结构可消费，不是事实核实或执行许可。

## 后续已完成的扩展

当前默认三个角色为 `tev1:4b`、`qwen3.5:4b`、`qwen3:8b`。合法高分保持原分工，低分、metadata 不可用或 primary 校验失败进入一次 8b 重审/标注分支。阈值默认 0.8；metadata 不可用时 gate_default=0，并在启用级联时升级，即使 threshold=0。

confidence 是未校准的 selected decision token probability，不能证明字段准确或所有语义正确。最终 score 低于实际阈值或 metadata 不可用时交给人工，使用 manual_review_required/review_reasons；一般未核验诊断、初始低分及级联开关本身不决定人工要求。Context 优先 needs_human_review，低分 ask 保留澄清问题。

旧 model 参数继续只控制详情模型；decision_model、fallback_model、confidence_threshold、cascade_enabled 为 keyword-only。完整入口和 normalize_task 支持有界尝试预算；独立 analyze_task 返回 typed Task，未提供完整 decision/context envelope。Stage 通用兼容 payload helper 与纯提取 runner 应区分，详见当前架构。

每个 primary/fallback 分支默认最多 2 次管线尝试（允许 1–3），总调用上限 2 * (max_attempts + 1)，关闭级联为 max_attempts + 1；state.attempts 是管线尝试累计而非模型调用数。权限和不可重试 HTTP 错误立即终止；失败不会生成备用事实。

## 历史检验顺序

1. 冻结旧实现与模型配置，保留基线；单独核对原生字母协议。
2. 先用 mock 覆盖角色、字母校验、ask 短路、有限重试、unit 来源边界与 resume，再实现生产协议。
3. 冻结候选，对照同输入的完整流程；反馈只提供共性错误类别。
4. 独立输入检验及只读审查，检查是否有题目硬编码或评分放宽。
5. 保存结果、失败及配置差异，不将有限实验宣称为生产准确率保证。

这些步骤为已完成开发过程的记录，不要求当前读者重新运行私有实验，也不提供题目、答案、原始响应或个人路径。采样与协议变化均可能影响结果，不能把观察收益全归于模型名称。

## 仍未实现或不能保证

当前只处理一次完整原文，无会话任务状态、跨请求记忆、active/superseded、有效预算替换或第二项修改状态；分开调用不继承历史，保留旧/新文字不等于计算最终有效值。标点正则切分仍保留，不使用语义正则补标。request guard 仅验证已宣称目标的标注自洽，无法证明目标独立、语义完整或全部标签正确。

输入预算为 20,000 字符、512 片段、PreparedContext JSON 16,000 UTF-8 字节；模型 messages/format JSON 为 24,000 字节，最多 16 个目标。超限拒绝而不摘要。默认超时 60 秒、上限 120 秒。

检查点绑定输入 hash、角色模型名称与其它 ExtractionTask 配置，以及 core/harness `.py`/`.json` SHA；不绑定权重 digest 或 Ollama 版本，文档及其它目录不进入执行指纹。当前没有自动业务执行、字段级 confidence、动态阈值或可保证稳定获益的级联策略。

完整字段、Context 状态、保存/恢复和 API 用法见 [当前架构](ARCHITECTURE.md)。
