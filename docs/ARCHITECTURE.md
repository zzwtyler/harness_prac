# 用户原文提取 Harness

这个 Harness 的任务仍是：**只从当前用户输入提取原文片段，按 intent 整理成不同 JSON**。
不生成事实、默认值、业务答复或经营结论，不执行订单、退款、发布等动作。
`docs/PROJECT_BRIEF.md` 保留业务背景；当前纯提取要求优先于其中的草稿生成建议。

## 各部分是否需要

| 部分 | 判断与实现 | 不扩展的原因或边界 |
| --- | --- | --- |
| task | 需要。`core/14_execution_config.py` 的 `ExtractionTask` 明确当前输入、决策/详情两个模型及尝试/超时预算。 | 目标固定为提取，不让模型生成新目标。 |
| context management | 需要。`core/03_context.py` 限制模型输入预算，在提取校验后按unit保存来源、分层信息和待复查项。 | 不引入历史、检索、摘要或额外事实。ready只代表结构和来源可消费，不代表事实核实或业务执行授权。 |
| instructions | 需要。可信指令集中在 `core/04_instructions.py`，与用户数据分离。 | 用户消息及网页自定义prompt不能覆盖提取协议。 |
| planning | 需要轻量形式。`core/05_planning.py` 固定定义提取、路由整理、校验、保存四步。 | 不需要模型自主制定行动计划；当前任务路径已知。 |
| tools | 需要受限工具。`core/06_tools.py` 只允许模型选择标签/原文索引；整理、校验、保存是固定本地操作。 | 不暴露shell、网页查询、数据库写入、订单操作等工具。 |
| skills | 当前不需要独立的动态skill系统。领域差异由 `core/02_task_classes/` 的结果模型及映射负责。 | 没有需要运行时发现/加载的额外工作流程，添加空skill目录没有实际作用。以后有独立且重复使用的工具流程再引入。 |
| agent loop | 需要有界执行循环。`harness/main.py` 执行固定步骤，`recovery.py` 在提取失败时有限重试。 | 不采用模型自行决定下一动作、无限反思或继续生成的自主循环。 |
| state / memory | 需要单次运行状态与检查点。`core/11_state.py` 保存运行状态、尝试数、输入/配置/代码摘要和已验证提取。 | 不使用跨用户/跨请求长期记忆，防止上一请求的订单、地址等污染当前输出。 |
| verification | 需要。`core/10_verification.py` 检查Schema、完整原文片段和intent字段映射。 | 不声称能证明分类、提取完整性或用户陈述的真实性；语义核验标为 `not_performed`。 |
| error recovery | 需要。提取协议错误、临时网络错误、HTTP不完整响应可重试；支持显式检查点恢复。 | 超出预算即失败；权限错误、不可重试HTTP错误不会靠重试绕过；不编造备用答案。 |
| permission | 需要应用层权限。`core/13_permissions.py` 限制能力、本机模型地址；结果文件限定在所选目录。 | 模型请求禁用代理和重定向。它不是OS沙箱，不能约束任意新增的可信Python扩展。 |
| subagents / orchestration | 需要orchestration：由固定执行计划统一调度。当前不需要运行时subagents。 | Tev1选择固定决策选项，高分由Qwen3.5标注；低分或校验失败由qwen3:8b重审决策并提取，最多升级一次。不自动办理业务。 |

这些判断针对本项目，不表示所有AI应用都不需要长期记忆、动态skills或多代理。

## 目录和阶段

所有流程模块统一位于 `core/`，功能文件采用 `编号_名称.py`。
有不同分类的模块，其类型放在旁边的 `同编号_名称_classes/` 目录。
`harness/` 只保留主流程入口 `main.py`，网页、评测、文档另行存放。

```text
core/
  01_user_intent.py             # Tev决策与Qwen原文标注入口
  01_user_intent_classes/       # 各种意图类型及index.json
  02_task.py                    # 意图结果 → 结构化任务
  02_task_classes/              # 各种任务类型、字段映射及index.json
  03_context.py                # 输入预算、提取后的unit隔离上下文
  04_instructions.py           # 可信提取指令
  05_planning.py               # 固定执行计划
  06_tools.py                  # 受限工具调用
  07_runtime.py                # 本机模型通信
  08_extraction.py             # 原文索引提取实现
  09_business.py               # 公共字段整理
  10_verification.py           # 结果校验
  11_state.py                  # 状态与结果存储
  12_recovery.py               # 有限重试
  13_permissions.py            # 能力与网络限制
  14_execution_config.py       # 单次运行配置
  15_models.py                 # 共享原文协议类型
  16_schema.py                 # JSON Schema与类型校验
  17_intent_registry.py        # 意图类型注册表
  18_task_registry.py          # 任务类型注册表
  19_stage.py                  # Stage契约与发现
  20_checkpoints.py            # 检查点摘要
  21_paths.py                  # 统一路径配置
  22_task_loader.py            # 动态文件加载
  23_cli.py                    # 命令行参数
  24_intent_details.py         # 各业务字段/子类型、动态标注Schema和分层信息
  __init__.py                  # Python包的编号模块导入适配
harness/
  main.py                      # 唯一主流程调用入口
web/                           # HTTP服务、Stage适配与静态资源
evaluation/                    # 对比实验
tests/
outputs/
docs/
```

编号用于模块组织，实际执行顺序由 `harness/main.py` 和 `core/05_planning.py` 决定，
不会按编号从01到23逐个执行。除Python要求的 `__init__.py` 外，core顶层功能文件都有编号。
当前有分类分支的是01和02；其他模块为共享实现，不创建空的分类目录。
以后某个模块需要分类，沿用 `NN_name.py` + `NN_name_classes/`，放在同一目录内。

模型调用顺序：用户原文 → `tev1:4b`固定字母决策 → `qwen3.5:4b`一次结构化标注 →
原文及归属校验 → Context Manager按unit隔离 → `02_task.build_task()`格式化任务 → 校验、保存。
`01_user_intent.normalize_task()`封装前两个模型步骤并返回带固定Decision的意图类型实例。
正常高分业务请求两次调用，低分业务请求三次（Tev → 8b决策 → 8b提取）；非request/ask高分一次，低分重审后仍非request两次。阶段02不再次调用模型。
默认启用cascade：Tev合法所选字母token概率低于阈值0.8，或metadata不可用时，跳过3.5并由8b重新决策；primary结构、来源、数量或request校验失败也强制升级。8b用同一A–M字母协议及R3必答request JSON协议，所有校验保持一致。
8b最多进入一次lane。每lane最多`max_attempts`次尝试，缓存已合法Decision，详情重试携带固定白名单诊断码、短说明、尝试号和合法unit编号，不复制异常文本、未知模型键、原始输出或用户文字为新增指令。总调用数最多`2 * (max_attempts + 1)`，attempts跨lane累计；关闭cascade时仍最多`max_attempts + 1`次。
网络错误不伪装低语义confidence；权限与不可重试HTTP错误立即终止。最终8b仍低分交由人工核验，不递归升级、不凭分数把目标改为ask。
两个 `_classes/` 目录存放Python类型定义，运行数据仍保存到 `outputs/`。
`core/__init__.py` 将语义名称映射到编号文件，例如 `from core import context` 加载
`core/03_context.py`；同一模块只保留一个实例。阶段文件及分类文件由 `core/22_task_loader.py`
按完整路径动态加载，同名分类文件不会互相覆盖。新增core模块保持编号唯一、语义名称唯一即可。

`core/02_task_classes/index.json` 中的 `order` 继续用于网页排序及业务结果文件编号，
例如 `08_membership_help.json`；它不是第八个处理阶段。新增类型时同步更新两份目录配置、
两个类型文件及 `core/15_models.py` 中允许的intent标签。

旧的 `intents/` 已迁至 `core/02_task_classes/`；旧入口 `02_harness.py` 和 `03_comparison.py`
分别迁至 `harness/main.py` 和 `evaluation/comparison.py`，启动方式见下文。
历史 `outputs/` 不改写。迁移改变了代码与路径摘要，旧检查点不能跨版本恢复；请用新输出目录。

阶段02的十一种任务拥有不同dataclass和JSON Schema，共用 `source_text`、`keywords` 和 `intents`。
`intents` 完整保留各个诉求及其分层信息；下表为兼容原有调用方保留的顶层原文字段。

| intent | 专用字段 |
| --- | --- |
| group_order | date、time、quantity、budget、pickup_or_delivery、location、request |
| order_support | order_id、requested_change、time、current_status |
| sales_analysis | period、metrics、comparison_request、scope |
| store_info | question、location、opening_hours |
| menu_advice | preferences、dietary_constraints、request |
| complaint | issue、impact、order_id、request |
| membership_help | issue、account_id、order_id、policy、request |
| campaign_brief | objective、period、audience、offer、channels、assets、budget |
| multi_intent | requests、order_id、account_id、constraints |
| other_request | request、constraints |
| no_intent | 无额外业务字段；原文保留在 source_text |

## 原文提取保障

Tev只返回A–M中的单一选项字母。Python固定映射为`Decision(option, input_kind, mode, routing)`：
A–I对应九种单业务，J表示多个独立目标，K/L表示social/background，M表示unclear/ask。
`infer`只表示理解当前原文并提取，不补事实；`ask`只表示目标或路线不明确，不因字段未观察到而触发。
决策输入采用`task`、`state`、`options`；state只含完整`source_text`，用户文字只是数据。解释、额外字符、非法字母或截断均拒绝并按预算重试。

`confidence`是数字，来自Ollama `logprobs:true`返回的合法所选字母token的`exp(logprob)`，只接受匹配的单字母/ASCII bytes和有限非正logprob；不取top候选代替它。它是决策token概率，**不是校准的语义正确率或字段准确率**，高分也不能跳过任何validator。
`confidence_details`记录method、model、metadata_status、selected_logprob、calibrated=false和范围说明。缺失/非法/歧义metadata的confidence=0明确是`gate_default`，不是模型给出的0概率，启用cascade时强制重审。
`cascade`保存enabled、used、reason、threshold、fallback_model及initial_decision/initial_confidence/initial_confidence_details。最终Decision来自Python映射，初始Decision独立留作审计；同份元数据复制到intent、Task、context、完整envelope与检查点。
`manual_review_required`和`review_reasons`由同一纯函数计算并独立校验，只看最终confidence与实际`cascade.threshold`以及最终metadata是否可用。分数严格低于阈值时使用`decision_confidence_low`；metadata缺失、非法或歧义时使用`decision_confidence_metadata_unavailable`，旧对象缺少metadata也保守要求核验。恰好等于阈值不算低分；threshold=0也不能接受缺metadata。初始分数、cascade是否启用和一般语义诊断不决定此标志；两项随上述元数据一致复制。无法产生有效结构时仍报告失败。

Qwen只返回`intents[]`，每个unit包含`intent`、`subtype`、`clause_ids`、必答`request[clause_id]`及`selections[{category, clause_id}]`；selections只承载request以外的业务/constraint标签。
单业务Schema收窄业务、子类型和标签，不能改Tev路线；multi的Schema允许全部业务，Python再验证每个unit的业务字段归属。
所有clause_id都受当前原文片段枚举约束；字段必须来自自身unit的clause_ids，原文允许共享，但不允许跨unit搬运事实。
模型逐片段枚举全部适用标签，Python复制完整原文并整理字段，不输出模型编写的字段值。
每个已宣称目标的unit必须在`request`数组明确选择至少一个来源，承载动作、问题或实际异常隐含求助；每个ID必须属于自身clause_ids。Python只按明确选择复制request关键词，不根据其它字段猜标签。专用字段与request可以兼标，不能互相替代。缺key或空数组时拒绝并有限重试，Python不自动补标签。
纯身份、编号、参数、规则、假设或否定异常不能为通过校验而贴request；参数和规则不能另建unit。这个guard只检查已宣称目标的标注自洽，不能证明语义完整性、标签正确或目标独立，也不能识别伪拆后的共享目标。
Python 校验索引归属并复制原文，生成以下层级：

- `input_kind`：`request`、`social`、`background`、`unclear`；后三类不进入详细提取。
- `decision`：Python冻结的选项映射，同时进入提取检查点，校验时不能改变输入性质、ask/infer或路线。
- 顶层 `intent`：由子意图数量推导为 `no_intent`、单个业务类型或 `multi_intent`。
- `intents[]`：每个独立诉求的业务类型、`subtype`、`evidence` 和自己的 `keywords`。
- `information`：`common` 通用诉求/限制、`business` 业务信息、`operation` 操作相关信息。
- `not_observed`：配置关注但未提取到的字段，需复查或澄清，不代表用户一定没说，也不是完整的业务必填规则。
- `verification_needed`：后续需要核实的数据类别；当前没有执行查询或业务操作。

`multi_intent` 不再与业务类型竞争：不同订单的两个操作可以是两个 `order_support`；`other_request` 可以与已知业务并存。
同一门店的位置和营业时间默认视作同一个信息咨询目标；拆分按独立目标，不按句子数量。
仅处理当前输入，不使用历史推断“补充信息”属于哪个既有任务。支持最多16个独立诉求，超出时要求拆分。
校验能保证索引归属、原文来源和派生字段一致，不能证明模型没有漏提、误分类或把同一个共享片段的语义归错。
`keywords` 保存 `text`、`start`、`end`，满足 `source_text[start:end] == text`，位置采用Python Unicode字符索引。
专用字段为原文片段数组；没有提取到则为 `[]`。空数组可能是未提供，也可能是模型漏提，不能直接视为用户没有说过。

保留完整片段、否定和纠正，不把“不要配送”截为“配送”，不把“不是20杯”变为肯定数量。
带数字的逗号（如 `1,500`）不拆开。同一片段可属于多个类别；不执行金额换算、相对日期计算或冲突消解。
标签仍可能错误，用户原话本身也未经过业务核实。

## 运行与恢复

以下命令在项目根目录运行。依赖Python 3.10+、支持token logprobs的本地Ollama，以及`tev1:4b`、`qwen3.5:4b`和默认级联模型`qwen3:8b`；Python只使用标准库。

```bash
ollama serve
ollama list
python3 -m harness.main '下周六需要20杯咖啡，预算500元，怎么订？' --output outputs/new_request
```

输出包括：

- `00_run_state.json`：运行状态、尝试数及恢复校验信息。
- `01_user_intent.json`：校验后的当前请求提取检查点。
- 对应阶段02的任务结果，例如 `02_group_order.json`：编号来自intent目录配置。
- `98_verification.json`：结构、来源和映射校验结果。

每个文件通过临时文件和原子替换写入。失败状态保存在当前运行状态中，未通过校验的业务结果不会保存为成功。
不保存思考流、原始模型推理或过程日志。输出目录默认不得混入旧运行；对比工具自己生成的直接回答文件除外。

```bash
# 输入、执行配置和代码须与原运行一致
python3 -m harness.main '下周六需要20杯咖啡，预算500元，怎么订？' --output outputs/new_request --resume
```

`--resume`会检查输入、三个角色模型、阈值/启用状态、采样/提示/相关代码摘要及检查点内容摘要；不一致时拒绝复用。
已有有效提取检查点时重新整理与校验，不重复调用模型；在提取前失败时重新执行受限提取。
恢复次数由调用者显式决定，每次调用仍受尝试预算限制；累计次数记在状态中。
目录锁防止同一目录同时写入。硬终止可能留下 `.run.lock`；此时不会擅自解除锁，需确认旧进程已退出后再清理锁并恢复。

`--model` / Python的`model`是旧参数的兼容别名，只控制详情模型，默认`qwen3.5:4b`。
新增`--decision-model` / keyword-only `decision_model`控制字母决策模型，默认`tev1:4b`；原有ExtractionTask六个位置参数次序不变。
新增keyword-only `fallback_model`、`confidence_threshold`、`cascade_enabled`，CLI对应`--fallback-model`、`--confidence-threshold`、`--no-cascade`；默认qwen3:8b、0.8、启用，关闭可做同代码对照。
另支持`--base-url`、`--think`（仅详情模型）、`--max-attempts`（每lane默认2，范围1–3）、`--timeout`（默认60秒，最大120秒套接字超时）。
`--base-url` 仅允许本机HTTP服务，禁止远程地址、认证信息、代理和HTTP重定向。
输入最多20,000字符、512片段，且序列化输入最多16,000 UTF-8字节；总指令/Schema/输入最多24,000字节。
这些是保守字节预算，不是精确token计数。上下文设为32768，Tev生成上限8 tokens，Qwen上限4096；超限拒绝或失败，不静默摘要。
采样显式固定：Tev temperature=0、think=false；Qwen temperature=0.2。两者top_k=20、top_p=0.95、min_p=0、seed=0、presence_penalty=0、frequency_penalty=0、repeat_penalty=1。
这些设置不继承各模型Modelfile的采样默认值，代码常量进入执行指纹；固定seed不保证所有后端逐位确定。
`--context` / Python的 `project_context` 为旧调用兼容保留，不进入模型输入。

完整`execute_task()`/CLI返回envelope，包含原有`intent`、`result`、校验与状态，以及新增的`decision`、`context`。
context按`units[]`保留`id`、业务/子类型、`source_spans`、`information`、`not_observed`、`verification_needed`、`needs_review`。`manual_review_required=true`时status优先为`needs_human_review`；否则ask为`needs_clarification`，可消费业务结构为`ready`，非请求为`no_intent`。低分ask仍保留原Decision、mode和澄清问题。`needs_review`中的`semantic_verification_not_performed`等诊断说明核验未执行，并不自动要求人工；是否必须核验只由两项固定`review_reasons`判断。
它明确标记`semantic_verification`和`business_execution`均为`not_performed`；ask提供固定通用`clarification_question`，不调用额外模型、不猜业务对象。
仅有固定Decision、通过来源校验且不需要人工核验的业务提取才可生成status=ready；它只表示结构可消费，不证明语义或业务事实正确。不能把兼容顶层聚合字段直接交给业务工具，当前所有业务操作仍未执行。人工量预算仅用于报告，不设运行配额、不自动接受低分，也不调整阈值。本次交接政策未改模型请求、提示、Schema、采样、角色或级联判定；代码指纹变化使旧检查点不能跨版本恢复。

## 网页和独立Stage

```bash
python3 -m web.main
```

访问 <http://127.0.0.1:8000>。前端继续按Schema显示不同结果，嵌套意图数据以格式化JSON显示。
网页和单独 `analyze_task()` 使用同一输入限制、固定指令、原文校验、网络权限与有限重试。
它们返回所选Stage的已有typed result格式，不是完整的decision/context handoff envelope；模型角色与纯提取保障仍一致。
单业务Stage会拒绝其它业务或multi输入，字段只由可消费unit提供，不会把其它目标的request当作requested_change。
网页缺少某个角色模型时保留该角色并禁用运行，只有用户明确选择已安装替代才更换；不会默认为列表首个模型。
网页可选择fallback模型、阈值和启用状态，关闭cascade后无需安装fallback角色。Web与直接Stage的typed result也包含同份confidence、cascade审计及人工核验标志，仍不是完整handoff envelope。
独立Stage不写持久状态；完整envelope、计划、文件检查点与恢复使用`python3 -m harness.main`或`execute_task()`。
页面背景、自定义System prompt不覆盖纯提取协议。共享Python实现/指令变更后需重启服务；intent文件及目录配置由注册表重新加载。

## 对比与验证

```bash
python3 -m unittest discover -s tests -v
python3 -m evaluation.comparison --output outputs/new_comparison
python3 -m evaluation.comparison --brief-only --output outputs/new_brief_comparison
```

对比保存当前编号的 `03_comparison.json` / `.md`，逐例保留直接回答、提取结果、运行状态、校验报告和错误记录。
直接回答保留项目背景；纯提取只用当前用户输入，因此比较的是工作方式，不是同提示词的受控实验。
Harness业务请求通常调用两次模型，无诉求输入一次，失败时按预算重试；表中的耗时可能包含重试与模型加载，不是严格性能基准。
调用失败退出码1，有限样例检查未通过退出码2，全部有限检查通过退出码0。
自动结构/来源校验通过，不等于业务语义或提取完整性验收通过。

### 分层意图改造对比

```bash
python3 -m evaluation.intent_layers --output outputs/intent_layers_new.json --repeats 2
```

固定16条样例检查顶层分类、原文字段、子意图类型及信息归属，记录真实本机模型调用数、token数和耗时。
`outputs/07_intent_layers/` 保存改造前源码快照及各轮实测。样例有限且参与调试，结果不能替代独立测试集或生产准确率。
