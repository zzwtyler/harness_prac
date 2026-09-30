# Confidence 级联：历史开发计划

**状态：历史开发记录，不是待执行任务或当前准确率承诺。** 代码/状态核对：2026-09-30。字母决策 confidence、8b 级联和明确人工交接均已实现。现有接口、限制与恢复行为以 [当前架构与协议](ARCHITECTURE.md) 和生产代码为准。

## 当时目标与方案

在已有 Tev1 → Qwen3.5 原文提取上，为低 confidence 增加本地 `qwen3:8b` 重审；保留原文来源校验、固定 Decision 映射及有界调用。confidence 采用所选决策字母 token 的 exp(logprob)，而不是另加模型自评分。

默认模型为 `tev1:4b` 决策、`qwen3.5:4b` 标注、`qwen3:8b` fallback。阈值先验设为 0.8，可配置；启用状态、角色模型名称和阈值进入执行配置。

## 已实现的当前行为

- Ollama `/api/chat` 的原生单字母决策，请求 logprobs，无 JSON format。只读取唯一匹配 selected token/bytes 的有限非正 logprob；不拿 top candidate 代替它。
- 合法高分走 Tev → Qwen3.5；低于阈值或 metadata 不可用时跳过 primary 标注，走 8b 重审决策及标注。metadata 缺失/非法/歧义使用明确 gate_default=0，即使 threshold=0 也升级。
- primary 决策非法或结构/来源/unit 数量/request 校验失败可强制升级；高分不能绕过 validator。fallback 最多进入一次，不递归。
- 每分支最多 max_attempts 次管线尝试，默认 2、范围 1–3；总模型调用上限 2 * (max_attempts + 1)，关闭级联为 max_attempts + 1。state.attempts 是累计管线尝试数，不是调用数。
- 重试沿用合法 Decision；JSON 标注失败只带固定白名单诊断反馈。权限与不可重试 HTTP 错误立即终止，无合法结构时仍报告失败。
- confidence/details、初始 Decision/分数和 cascade 审计贯穿 ExtractedInput、Task、Context、envelope 与提取检查点；可关闭级联做同代码对照。
- 最终人工政策已替代早期“只标 needs_review”的描述：最终 score < 实际阈值，或最终 metadata 不可用时 manual_review_required=true，Context 优先 needs_human_review。只有 decision_confidence_low 与 decision_confidence_metadata_unavailable 两项固定原因。

最终人工判断不取决于级联开关、初始低分或一般 semantic_verification_not_performed 诊断。恰好等于阈值不算低分；threshold=0 也不能接受缺 metadata。低分 ask 保留澄清问题，不凭分数改模式或目标。

## 历史验证方法

开发期间先用 mock 校验协议、来源、分支预算、审计防伪和恢复；再冻结候选进行真实响应重放与同代码启用/关闭对照，最后使用未参与修改的独立输入。实现者不接触独立输入、答案或原始响应，评分口径不因模型失败而放宽。

历史发现包括高 confidence 误判、更大模型未稳定改善独立输入。这些观察不构成当前准确率、延迟或升级收益保证。本文不包含题目、答案、原始响应或私有报告入口。

## 仍存在的限制

- token 概率未经校准，不是决策语义正确率，也不覆盖字段漏标/误标；没有字段级 confidence 或分歧核验策略。
- 默认 static threshold=0.8；曾讨论的人工量预算仅为报告参考，没有运行配额、动态阈值或低分自动接收策略。
- 当前是单次原文输入，同次原文保留旧/新文字，但无原生多轮、active/superseded、有效预算替换或第二项修改状态；分开调用不继承历史，不执行业务操作。标点正则切分仍保留，不使用语义正则补标。
- resume 只绑定输入 hash、ExtractionTask 配置及 core/harness `.py`/`.json` SHA；模型名称不等于权重 digest，不绑定 Ollama 版本。文档或其它目录变化不进入该指纹。
- 输入、生成长度、响应和尝试均有预算；超限及最终校验失败仍会失败，不能伪造可交接结果。

最新字段和 Stage API 请读 [当前架构](ARCHITECTURE.md)，不要将本计划的历史实验条件视为生产保证。
