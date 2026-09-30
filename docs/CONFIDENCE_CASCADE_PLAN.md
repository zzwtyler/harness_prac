# Confidence模型级联实验

新增用户需求：低confidence交给本地qwen3:8b，主agent继续独立保管问题/答案及实际调用，subagent只实现/审查和mock。

confidence来自Ollama 0.35的所选决策字母token logprob，取exp(logprob)。它只表示decision token probability，不是经过校准的意图或字段正确率。缺失/歧义/非法metadata以明确gate默认0升级，不能虚构模型概率。

Tev native letter协议与R3 request wire继续保留。先验阈值0.8，可配置；高分Tev→Qwen3.5，低分Tev→8b独立重审完整source→8b提取；结构/来源/数量/request失败也强制升级，不靠高分绕过校验。8b最多进入一次lane；每lane最多max_attempts次尝试，总调用上限2(max_attempts+1)。权限错误与不可重试HTTP立即终止。最终8b低分只标needs_review，不递归升级或擅自改ask。

数字confidence及来源信息、初始Decision/分数、升级原因贯穿typed结果、Context、checkpoint及envelope。threshold/fallback_model/enabled为keyword-only执行配置，进恢复指纹；CLI/Web/direct一致，缺模型不静默替换。支持关闭级联进行同代码对照。

主agent冻结评测：固定43题同代码关闭/开启级联对照，统计整题通过率、升级量、救回/退步/高分误判及耗时。独立hidden20/fresh14在候选确定后首次使用，不据其调阈值或改Gold。原题不进入subagent上下文，评分器不放宽，模型只收到source和通用生产协议。

官方接口：<https://docs.ollama.com/api/chat>。原生探测验证真实logprobs有区分度，但更大模型也可能高置信判错。

最新用户修正：不要求每个判断准确，低confidence允许人工核验且控制比例。新增明确manual_review_required/review_reasons与Context needs_human_review，保留所有推理请求和校验；暂定20%仅报告预算，不硬编码配额。独立题已完成，详见outputs/09_dual_model/confidence_cascade_report.md。
