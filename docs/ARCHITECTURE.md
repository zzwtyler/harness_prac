# 当前架构与协议

代码/状态核对：2026-09-30。这是一个用于学习与实验的**本地原文提取练习项目**。本文对照当前 `core/` 与 `harness/` 实现，说明已有行为；历史设计过程见 [双模型分工计划](DUAL_MODEL_DEBUG_PLAN.md) 和 [confidence 级联计划](CONFIDENCE_CASCADE_PLAN.md)。历史实验不构成当前准确率或性能保证。

项目只处理一次提交的完整用户原文：判断输入性质、选择业务路线、标注来源，再整理成 JSON 与 Task。不生成业务事实、默认值或答复，不执行订单、退款、账号变更、数据库写入或发布。

## 1. 单次输入与状态边界

当前不是原生多轮对话，也没有会话 ID、跨请求任务记忆或历史检索。`RunState` 和检查点记录一次运行的进度，`--resume` 恢复同一输入的执行，并非给已有任务追加一轮对话。

同一次原文可以同时包含旧值、新值、否定与纠正；完整 `source_text` 保留这些文字。标注不维护 `active`/`superseded` 状态、有效预算替换或第二项修改的状态，不计算最终有效值、不消解冲突，也不推断单独补充信息属于上一请求。分开调用不继承历史。字段仍可能漏标或误标。

## 2. 模型角色与流程

Python 3.10+，实现使用标准库；模型服务为支持 token logprobs 的本地 Ollama。

| 角色 | 默认模型 | 协议与默认生成设置 |
| --- | --- | --- |
| primary 决策 | `tev1:4b` | 单字母；temperature=0、think=false、num_predict=8 |
| primary 原文标注 | `qwen3.5:4b` | 动态 JSON Schema；temperature=0.2、think=false、num_predict=4096 |
| fallback 重审及标注 | `qwen3:8b` | 决策使用同一字母协议，标注使用同一 JSON 协议；设置随角色切换 |

三者共享显式采样：top_k=20、top_p=0.95、min_p=0、seed=0、presence_penalty=0、frequency_penalty=0、repeat_penalty=1、num_ctx=32768。设置不继承各模型的采样默认值；固定 seed 不保证后端逐位确定。`think` 参数只控制 JSON 标注角色，完整提取入口默认 false。

```text
当前原文 → Tev1 决策 ──合法高分 request──→ Qwen3.5 标注
                │                              │
                ├─低分 / metadata 不可用        └─标注校验失败
                └─非法决策 ────────────→ Qwen3:8b 重审决策及标注
                                                │
                  同一来源/结构校验 ←────────────┘
                            ↓
                  Context → Task → 输出校验 → 可选保存
```

默认启用级联，阈值为 0.8。8b 最多进入一次 fallback 分支，不递归升级。最终决策为 social/background/unclear 时不调用字段标注模型；unclear/ask 保留固定澄清问题。fallback 可改变初始路线，但同一分支内的标注不能改变该分支已固定的 Decision。

## 3. 决策协议

`core/06_tools.py` 通过 Ollama `/api/chat` 发送以下结构作为用户消息；当前不使用 `/v1/systemone`：

```text
{task: 通用判断说明, state: {source_text: 完整原文}, options: A–M 通用定义}
```

state 只含当前完整原文，没有已切开的 clauses。决策请求不设置 JSON `format`，使用 `logprobs:true`；原文始终是数据，不是可信指令。

模型输出经首尾空白去除后须恰为一个合法字母，不能从解释、JSON 或其它字符中挖取答案。Python 在 `core/15_models.py` 冻结映射为 `Decision(option, input_kind, mode, routing)`：

| 选项 | input_kind / mode / routing |
| --- | --- |
| A | request / infer / store_info |
| B | request / infer / menu_advice |
| C | request / infer / order_support |
| D | request / infer / group_order |
| E | request / infer / complaint |
| F | request / infer / membership_help |
| G | request / infer / campaign_brief |
| H | request / infer / sales_analysis |
| I | request / infer / other_request |
| J | request / infer / multi_intent |
| K | social / infer / no_intent |
| L | background / infer / no_intent |
| M | unclear / ask / no_intent |

`infer` 仅表示理解当前原文，不补事实；`ask` 用于目标或路线不明确。缺少参数、`not_observed` 或仅有附属条件不会在 Python 中自动改为 ask。多个独立目标按 unit 保存，同业务目标不合并，other 可以与已知业务并存。这些语义边界由通用文字定义交给模型判断，来源校验不能证明判断正确。

## 4. 原文标注与 canonical 结果

`prepare_context()` 使用标点正则分出完整片段，去除片段首尾空白并保留 Unicode 字符索引；数字两侧的 ASCII 逗号不拆分。取消的是语义正则补标或细拆业务字段，并非所有正则。Tev 不接收片段列表；JSON 标注输入包含完整原文、固定 Decision、允许业务/子类型/标签说明及 `clause_N` 片段。

Qwen 的 wire 仅返回：

```text
intents[] = {
  intent, subtype,
  clause_ids: [自身目标及相关属性的片段 ID],
  request: [承载动作、问题或实际异常隐含求助的片段 ID],
  selections: [{category: request 以外的标签, clause_id}]
}
```

`request` 为独立必答数组，canonical 校验要求每个目标至少一项。`selections` 可以为空，同一来源可同时选择 request 与专用标签。Python 仅复制模型明确选择的原文，不猜标签或自动补 request；不存在从字段值生成新事实的步骤。

单业务分支仅一个 unit，multi 分支必须至少两个，最多 16 个。Schema 限制当前允许业务、子类型、标签和 ID；后续校验还检查所有 request/selection 都属于自身 `clause_ids`。不同 unit 可共享原文，但程序无法证明共享片段确实承载独立目标，也无法识别所有伪拆或漏拆。

canonical `ExtractedInput` 包含：

- `source_text`、`input_kind`、固定 `decision`。
- `intents[]`：每个目标的 `intent`、`subtype`、`evidence`、`keywords`、`information`、`not_observed`、`verification_needed`。
- 顶层 `intent`、`keywords`：由 units 派生的兼容汇总，不替代 unit 边界。
- `confidence`、`confidence_details`、`cascade`、`manual_review_required`、`review_reasons`：可信程序元数据。

`keywords` 的 `text/start/end` 必须引用完整原文片段，满足 `source_text[start:end] == text`；`information` 分为 common/business/operation。`not_observed` 是未提取到的字段提示，不证明用户未提供，也不是完整的业务必填规则。`verification_needed` 只说明将来需要的核实，当前不查询业务数据。

Task 的专用字段是原文片段数组，由各类型的 `FIELD_CATEGORIES` 确定。缺项保留 `[]`，不填默认值。单业务 formatter 先检查顶层路线匹配，消费该业务 unit 的字段；multi 保留全部 units。相同业务的独立目标仍在 `intents[]` 中逐个保留，兼容汇总字段可对相同原文去重，不能代替逐目标交接。

## 5. confidence、审计与人工核验

confidence 来自最终合法决策字母的 `exp(selected_logprob)`。只接受 top-level `logprobs` 中唯一、匹配选中字母的 ASCII token，要求 bytes 匹配、logprob 是有限非正数；不取 `top_logprobs` 中其它候选代替它。

它是**未经校准的决策 token 概率，不是语义正确率或字段准确率**。高分不能跳过 validator，8b 也可能高分误判，级联不保证稳定改善所有输入。

| 字段 | 内容 |
| --- | --- |
| `confidence_details` | method、model、metadata_status、selected_logprob、calibrated=false、范围说明 |
| `cascade` | enabled、used、reason、threshold、fallback_model、initial_decision、initial_confidence、initial_confidence_details |
| `manual_review_required` | 最终结果是否必须人工核验 |
| `review_reasons` | 仅允许下面两项固定代码 |

metadata 为 missing/invalid/ambiguous 时，confidence 为显式 `gate_default=0`，selected_logprob 为 null；这是程序 gate 默认值，不是模型给出的零概率。启用级联时 metadata 不可用总会升级，即使 threshold=0。

`manual_review_policy()` 仅按最终分数与实际 `cascade.threshold`、最终 metadata 状态计算：

1. confidence 严格小于 threshold：`decision_confidence_low`。
2. metadata 不可用或旧对象缺少 metadata：`decision_confidence_metadata_unavailable`。

恰好等于阈值不算低分；threshold=0 也不能消除 metadata 缺失的人工要求。人工标志不依赖级联开关、初始低分或一般语义诊断；不硬编码人工配额，也不自动调整阈值。validator 独立重算标志并校验分数、元数据和级联记录的一致性；不证明上游响应真实性或模型判断正确。缺 metadata 的旧对象不会因此成为合法 Context：Context 还要求固定 Decision 和合法提取。

这五项元数据从提取一致复制到 typed Task、Context、完整 envelope 和提取检查点；metadata 经独立校验后不作为用户原文事实扫描。

## 6. Context 交接状态

`build_intent_context()` 在来源/结构校验后确定性生成 `units[]`：id、业务/子类型、source_spans、information、not_observed、verification_needed、needs_review。状态按以下优先级确定：

| 条件 | status |
| --- | --- |
| manual_review_required=true | needs_human_review |
| 无强制人工且 Decision.mode=ask | needs_clarification |
| 无强制人工且有业务 units | ready |
| 其余非请求 | no_intent |

低分 ask 仍保留原 Decision、mode 和 `clarification_question`；问题固定为通用目标澄清，不调用额外模型、不猜对象。Context 的 `semantic_verification` 和 `business_execution` 都为 `not_performed`。

`needs_review` 包含未执行语义核验、缺项和业务核验提示；这些一般诊断并不全部意味着必须人工。强制人工只看 `manual_review_required` 与两项 `review_reasons`。`ready` 只表示结构/来源可消费，不证明事实已核实、业务已获授权或可自动退款取消。

## 7. 输入、请求与重试预算

| 限制 | 当前值及计量范围 |
| --- | --- |
| 原文 | 非空，最多 20,000 个 Python Unicode 字符 |
| 原文片段 | 最多 512 个 |
| PreparedContext 序列化输入 | source_text 与 clauses JSON 最多 16,000 UTF-8 字节 |
| 模型请求预算 | messages 与 format 的序列化 JSON 最多 24,000 UTF-8 字节 |
| HTTP 响应 | 最多 4 MiB，且模型须完整结束，拒绝 length 截断 |
| 独立目标 | 最多 16 个，单/多数量须与 Decision 匹配 |
| max_attempts | 每个 primary/fallback 分支默认 2，允许 1–3 |
| timeout_seconds | 默认 60 秒，须大于 0 且不超过 120 秒 |

字节预算不等于 tokenizer token 数；超限拒绝，不静默摘要或截断。

合法 Decision 在分支内缓存。启用级联时 primary 非法决策或标注校验失败进入 fallback；fallback 或关闭级联时按剩余尝试预算重试。详情重试使用生产 validator 的白名单诊断码、固定短说明、合法尝试号及 unit ID，不把异常字符串、未知模型键、原始响应或用户文字拼为新增可信指令。

每次完整提取总模型调用数上限：启用级联为 `2 * (max_attempts + 1)`，关闭为 `max_attempts + 1`。无重试时，高分 request 通常 2 次；低分直接升级后 request 通常 3 次；最终仍非 request 的高/低分分支通常 1/2 次。结构失败后升级可能增加调用。

`RunState.attempts` 和 `on_attempt` 是跨分支累计的**管线尝试计数，不是 HTTP 或模型调用数**。网络错误不会伪装为语义低分；可重试 HTTP 状态为 408/429/500/502/503/504，权限与其它 HTTP 错误立即终止。最终 fallback 低分只交由人工，不再升级；无有效结构仍抛失败，不生成伪成功结果。

模型地址默认 `http://127.0.0.1:11434`，仅允许本机 HTTP（localhost、127.0.0.1、::1），无 URL 认证、query/fragment 或非根路径。模型请求禁用环境代理和重定向。能力限制属于应用层，不是对任意 Python 扩展的 OS 沙箱。

## 8. 入口与 Stage API

| 入口 | 行为与返回值 |
| --- | --- |
| `harness.main.execute_task(source, ...)` / `run_harness` | 完整固定计划与 envelope；可选保存/恢复 |
| `python3 -m harness.main` | CLI 对上述入口的包装，成功打印 JSON，运行失败退出 1 |
| `core.user_intent.normalize_task(source, ...)` | 执行决策/标注/级联，返回 typed ExtractedInput，不保存运行状态 |
| `core.task.build_task(extracted)` | 校验已提取结果并确定性生成 typed Task，不再调用模型 |
| `TaskRegistry().get(intent).module.analyze_task(source, ...)` | 单独业务入口，返回对应 typed Task；错误业务或 multi 不能交给单业务 formatter |
| `definition.module.from_extraction(extracted)` | 只消费已有合法提取并格式化，不调用模型 |

完整入口及 normalize_task 默认 think=false，可配置 max_attempts、timeout_seconds；业务 analyze_task 暴露三个模型角色、base_url、think、threshold 和 cascade_enabled，使用提取器默认尝试/超时预算。新角色参数为 keyword-only；ExtractionTask 原六个位置参数次序不变，`model` 仍只表示详情模型。

完整 envelope 有 `intent`、`decision`、`context`、五项 confidence/人工元数据、`stage`、`result`、`verification`、`state`；这里的 `intent` 是完整提取对象，内部 `intent` 才是路由字符串。独立 typed Task 不含完整 decision/context envelope，可自行调用 `build_intent_context(extracted)` 获得 Context。

`HarnessStage` 与 `StageRegistry` 是通用适配契约。`runtime.run_stage()` 有 runner 时调用注册的提取入口，不直接把 typed output Schema 当作 Qwen 的 wire Schema；其默认 think=true，与完整入口不同，需显式配置以作一致对照。`HarnessStage.make_ollama_payload()` 及无 runner 的通用路径保留背景/自定义 prompt 等兼容能力，不等于这里的完整纯提取协议。纯提取入口的 `project_context`/CLI `--context` 仅为兼容参数，不进入该模型输入或字段事实。

CLI 的角色与策略参数是 `--decision-model`、`--model`、`--fallback-model`、`--confidence-threshold`、`--no-cascade`；其它参数包括 `--base-url`、`--think`、`--max-attempts`、`--timeout`、`--output`、`--resume`。省略 output 时不写持久文件。

## 9. 保存与显式恢复

指定 output_directory 后，固定计划执行 extract → route_and_format → verify → save：

- `00_run_state.json`：run_id、source_hash、execution_hash、status、step、attempts、resumed、extraction_hash、error。
- `01_user_intent.json`：已校验提取检查点，包含决策、来源和审计元数据。
- `NN_<intent>.json`：Task；编号来自 `core/02_task_classes/index.json` 的 order，不代表阶段执行次序。
- `98_verification.json`：Schema、来源、映射及 unit scope 校验结果；semantic_verification 为 not_performed。

写入采用临时文件、fsync 与原子替换。目录锁 `.run.lock` 防止同时写入，硬终止的遗留锁需确认旧进程退出后显式清理。模型响应与思考流不另存过程文件；失败时运行状态可记录截短异常说明，未通过校验的结果不保存为成功。

输出目录不能混用旧运行（代码对历史比较文件 `00_direct_answer.json` 有兼容例外）。resume 必须指定目录，且校验：

1. 当前 source_text 的 hash 与 state.source_hash 一致。
2. ExtractionTask 配置及 core/harness 下 `.py`/`.json` 文件 SHA 形成的 execution_hash 一致。
3. 存在已完成提取时，检查点内容摘要、原文和 canonical 校验一致。

配置绑定**模型名称**、启用状态、阈值、预算等；代码 SHA 覆盖采样/指令实现。它不绑定实际模型权重 digest 或 Ollama 版本，docs 与其它目录改动也不进入执行指纹。因此同名模型被替换不能靠现有 resume 指纹检测。

合法提取检查点可重做 Context/Task/校验而不重复模型调用；没有有效提取时重新执行受限流程。恢复次数由调用者决定，每次仍受尝试预算限制，state.attempts 累计管线尝试。`RunState.status=completed` 只代表管线完成，不代表无需人工核验。

## 10. 模块定位与保证范围

| 模块 | 职责 |
| --- | --- |
| core/01_user_intent.py、02_task.py | 两个执行阶段入口 |
| core/03_context.py、15_models.py | 输入范围、canonical 类型和 Context/人工政策 |
| core/04_instructions.py、06_tools.py、07_runtime.py、08_extraction.py | 可信指令、模型适配和有界分支 |
| core/09_business.py、10_verification.py、24_intent_details.py | 原文字段整理、派生信息和来源/结构校验 |
| core/11_state.py、12_recovery.py、14_execution_config.py、20_checkpoints.py | 状态、重试、配置和恢复摘要 |
| core/17_intent_registry.py、18_task_registry.py、19_stage.py、22_task_loader.py | 分类模型与 Stage 发现/加载 |
| harness/main.py、core/05_planning.py、23_cli.py | 完整固定编排与 CLI |

编号用于模块组织，不按文件编号依次执行。只有程序列出的受限能力可用，没有运行时技能发现、业务执行 subagent 或自主规划循环。

本次文档核对不等于真实模型验收。Schema/来源/映射有效不代表全部意图、子类型、标签及独立目标判断正确，也不证明用户陈述的真实性。未观察到的字段可能是漏提；高 confidence 与更大模型都不能替代业务核验。
