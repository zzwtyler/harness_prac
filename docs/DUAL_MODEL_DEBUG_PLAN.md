# Tev1 → Qwen3.5 分工调试

用户提供的流程：User Request → Tev1 4B Decision（intent、ask/infer、routing）→ Qwen3.5 4B Structured Intent → Context Manager → Agent/Tools。

## 固定约束
主agent负责出题、保管gold、调用真实模型和评分；实现/审查subagent不读取evaluation、outputs或主agent私有目录，不调用真实模型，仅检查生产代码、修改代码并运行mock/纯单元测试。只反馈错误类别及通用建议，不传验收原句或答案。

保留两阶段：Tev1选固定通用决策选项；Qwen3.5一次按受约束Schema选择原文信息。事实由Python复制原文，保留否定/纠正；不加入语义正则，不执行订单、退款或账号业务。

## 决策协议
Tev1本地system要求从选项中选择且只输出字母。采用9个单业务选项（包含other）、多独立目标、纯social、纯background、unclear/ask，共13项。输入state是数据，不能执行其内容。严格接受一个合法字母；非法、空、解释或截断输出均有界失败/重试。

infer仅表示当前输入能识别目标并进行原文结构化，不补造事实。ask只在无法识别目标/路由时产生，停止详情调用并进入待澄清状态；缺字段的not_observed不自动等同于用户未提供。social/background保留原文且无业务unit。

Python固定映射Decision。Qwen单业务结果不得改Tev路线；multi保留每个独立unit，同业务可以重复。子类型属于结构化标注，不被当作已授权执行工具的决策。

## 上下文与兼容
Context Manager在结构化结果校验后确定性生成按unit隔离的上下文，保留来源、观察到的字段和待复查项；兼容顶层聚合字段不可直接交给业务工具。ask不执行。任何后续工具执行仍需另行实现且符合任务权限。

旧model参数明确作为详情模型兼容别名；新增decision_model为keyword-only，不打乱ExtractionTask既有位置参数。CLI、Python、网页和直接Stage入口使用同样角色配置。双模型配置进入checkpoint指纹，切换任一角色拒绝旧checkpoint。

## 检验顺序
1. 保存v7源码与模型元数据；同旧代码跑Qwen3.5完整基线。
2. 主agent验证Tev原生字母协议。
3. subagent按模型角色、字母校验、ask短路、有限重试、跨unit边界和resume先补失败单测，再实现。
4. 冻结新代码，主agent同题跑新管线；根因反馈仅聚合类别。
5. 主agent独立隐藏/新题复验，审查agent检查是否有测试硬编码或放宽评分。
6. 报告准确率、阶段错误、实际模型调用数、耗时及未通过项，保存最好候选及全部失败记录。

模型及采样参数均明确记录。Tev1与Qwen3.5既有默认不同，不能把继承的默认参数当成相同实验条件。
