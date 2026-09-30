# harness_prac · 本地原文提取 Harness

一个使用本地小模型的结构化提取项目：从当前用户原文判断意图、标注来源片段，再整理成带审计信息的 JSON 和 Task。适用于业务请求的分类与信息交接，不生成业务事实、默认值或经营结论，也不执行下单、退款、发布等操作。

## 工作流程

```text
用户原文 → Tev1 决策 → Qwen3.5 标注 → 来源校验 → Context → Task
                 ↓低分或 metadata 不可用    ↓校验失败
                 └──── Qwen3:8b 重审决策并标注 ──→ 同一校验流程
```

- **Tev1 决策**：`tev1:4b` 只选择 A–M 的一个字母，Python 映射为输入性质、ask/infer 和业务路线。
- **Qwen3.5 标注**：`qwen3.5:4b` 选择原文片段 ID 和字段类别。单业务不能改决策路线；多个独立目标按 unit 保存，同业务的独立目标也可并存。
- **Qwen3:8b 级联**：默认启用。低决策 confidence、缺少有效 confidence metadata，或主流程结构、来源、目标数量、request 校验失败时，由 `qwen3:8b` 重新决策并提取；最多升级一次。
- **来源校验**：Python 复制模型明确选择的原文，检查 Schema、范围和 unit 归属。每个已宣称目标必须明确选择 request 来源；不会靠语义正则自动补标签。
- **Context 与 Task**：按目标保留来源、信息、缺项和核验提示，再生成对应业务类型的 Task。`ready` 仅表示结构可消费。

目标不明确时返回固定澄清提示；social/background 输入跳过字段标注。所有分支仍保留原文和决策审计。

## 环境准备

- Python **3.10+**；Python 实现只依赖标准库。
- 本地 Ollama，支持 `/api/chat` 的 token logprobs。
- 已安装以下模型；模型来源及安装方式请按各自实际分发渠道确认。

| 角色 | 默认模型 |
| --- | --- |
| 决策 | `tev1:4b` |
| 原文标注 | `qwen3.5:4b` |
| 级联重审及标注 | `qwen3:8b` |

在项目根目录运行：

```bash
ollama serve
```

另开终端用 `ollama list` 检查模型是否已安装。默认连接 `http://127.0.0.1:11434`；仅允许本机 HTTP 模型服务。

## 使用

### CLI

将占位文字换成当前用户原文：

```bash
python3 -m harness.main '当前用户原文' --output outputs/demo
```

省略 `--output` 时只输出到终端。输出目录须为新目录，文件包含运行状态、提取检查点、Task 和结构/来源校验报告。`outputs/` 是本地运行数据，不随仓库发布。

恢复同一输入、配置及代码的运行：

```bash
python3 -m harness.main '当前用户原文' --output outputs/demo --resume
```

检查点通过输入、角色模型、阈值、执行代码指纹及内容摘要校验；不一致时拒绝恢复。已有有效提取检查点可复用，不再次调用模型。

### Web

```bash
python3 -m web.main
```

打开 <http://127.0.0.1:8000>。页面可选择模型角色、confidence 阈值和级联开关；缺少某个启用的角色模型时禁用执行，需明确选择替代模型。

Web 和独立 Stage 返回对应的 typed result，包含 confidence、级联审计和人工核验标志。完整的 decision/context 交接 envelope 使用 CLI 或下面的 Python 入口。

### Python

```python
from harness.main import execute_task

response = execute_task(
    '当前用户原文',
    decision_model='tev1:4b',
    model='qwen3.5:4b',
    fallback_model='qwen3:8b',
    confidence_threshold=0.8,
    cascade_enabled=True,
)

print(response['context']['status'])
print(response['manual_review_required'], response['review_reasons'])
print(response['result'])
```

`model` 是详情标注模型的兼容参数。可传 `output_directory='outputs/demo-python'` 保存运行，或配合 `resume=True` 显式恢复。

## 配置与人工核验

| CLI 参数 | 默认值 / 含义 |
| --- | --- |
| `--decision-model` | `tev1:4b` |
| `--model` | `qwen3.5:4b`，详情标注角色 |
| `--fallback-model` | `qwen3:8b` |
| `--confidence-threshold` | `0.8` |
| `--no-cascade` | 关闭自动升级，可作同代码对照 |
| `--max-attempts` | 每个 primary/fallback 分支默认 2 次尝试，允许 1–3 |
| `--timeout` | 单次请求默认 60 秒，最大 120 秒 |

`confidence` 是所选决策字母 token 的 `exp(logprob)`，**未经校准，不等于语义正确率或字段准确率**。metadata 缺失、非法或歧义时使用显式的 `gate_default=0`，不称其为模型给出的零概率。高分不会跳过任何结构或来源校验，也不能保证字段没有漏标或误标；8b 也可能高分误判，不能保证级联稳定提升准确率。

人工核验只依据最终结果：confidence 严格低于实际阈值，或最终 metadata 不可用时，`manual_review_required=true`，Context 状态为 `needs_human_review`。`review_reasons` 只有 `decision_confidence_low` 和 `decision_confidence_metadata_unavailable` 两码。低分 ask 保留原澄清提示；高分 ask 为 `needs_clarification`。一般的 `semantic_verification_not_performed` 诊断不会自动要求人工。

不设人工处理配额，也不通过降低阈值自动接受低分。无法产生有效结构时仍报告失败。级联不递归；每次运行总模型调用数最多 `2 * (max_attempts + 1)`，关闭级联时最多 `max_attempts + 1`。权限错误及不可重试 HTTP 错误立即终止。

## 当前边界

当前是**单次完整原文提取，不是原生多轮对话**。若在同一次提交中包含旧内容和纠正内容，完整原文会保留旧/新片段及否定，但不维护 `active`/`superseded` 标记或条目替换状态，不跨请求追踪既有任务，也不自动消解冲突。

每个字段都带原文来源；索引校验只能证明来源和结构一致，不能证明分类正确、提取完整、目标独立或业务事实真实。项目不调用订单、数据库写入或发布工具。

## 测试与文档

```bash
python3 -m unittest discover -s tests -v
```

测试使用 mock 覆盖模型角色、来源范围、有界重试、级联、人工核验和检查点恢复，不等同于真实模型语义验收。

可选的网页脚本测试需要 Node.js；未安装时这部分测试会跳过，不影响 Python 服务运行。

完整模块说明、协议字段和恢复机制见 [架构与协议文档](docs/ARCHITECTURE.md)。主要代码位于 `core/`，完整执行入口在 `harness/`，网页在 `web/`，单元测试在 `tests/`。
