# 示例业务项目：拾光咖啡

> 这是为开发 Harness 而设定的虚构项目，不代表真实品牌、门店或政策。

## 行业与业务

拾光咖啡是一家有三家门店的本地咖啡品牌，销售咖啡、茶饮和烘焙产品，提供到店消费、自取，以及面向公司活动的团体订单。顾客会通过网页发来咨询；店长也会向运营团队提出活动和销售分析需求。

目前只有上述业务设定。门店地址、营业时间、菜单价格、库存、订单、会员规则和销售报表尚未接入。Harness 可以分析需求和生成草稿，但不能把缺失的数据当成已知事实。

## Harness 参与的岗位

**岗位：门店客服与运营助理。** 它是顾客消息和店长需求的第一道分流台：理解请求，判断主要 intent，收集办理所需的信息，再生成适合员工检查的业务产物。

工作流程：

1. Stage 01 识别主要 intent，并提取目标、约束、关键缺失项和验收标准。
2. 后续 Python Stage 根据 intent 生成不同结构的分析结果。
3. 前端展示分析结果、依据和仍需员工确认的事项。
4. 员工决定是否发送答复或执行订单、退款、活动发布等动作。

Harness 不直接承诺价格、库存、配送范围、预订成功或退款结果；这些信息需要接入数据源或经员工确认。

## 可以实现的 intent 与回答类型

下表的字段是**后续专用 Python 结果模型**的建议，不要求全部塞进 Stage 01 的通用 `UserIntentModel`。

| intent | 谁会提出、典型需求 | 建议回答类型 | 建议结果字段 |
| --- | --- | --- | --- |
| `store_info` | 顾客：“哪家店离我近？几点营业？” | `StoreInfoAnswer`：事实答复草稿 | `question`、`verified_facts`、`reply_draft`、`missing_facts` |
| `menu_advice` | 顾客：“不喝奶，想要低甜度饮品。” | `MenuAdvice`：推荐分析 | `preferences`、`dietary_constraints`、`candidates`、`reasons`、`facts_to_verify` |
| `order_support` | 顾客：“我想把自取时间改到下午。” | `OrderSupportCase`：订单处理单 | `order_id`、`requested_change`、`current_status`、`verification_needed`、`next_action` |
| `group_order` | 顾客：“下周公司活动要 20 杯，能配送吗？” | `GroupOrderLead`：团体订单线索单 | `date`、`quantity`、`budget`、`pickup_or_delivery`、`missing_details`、`handoff_action` |
| `complaint` | 顾客：“上次拿到的饮品做错了。” | `ComplaintCase`：客诉分级单 | `issue`、`impact`、`evidence_needed`、`urgency`、`reply_draft`、`escalation` |
| `membership_help` | 顾客：“积分为什么没到账？” | `MembershipAnswer`：规则与账户核查单 | `question`、`account_lookup_needed`、`policy_basis`、`reply_draft`、`missing_facts` |
| `campaign_brief` | 店长：“下个月做工作日早餐活动。” | `CampaignBrief`：活动策划简报 | `objective`、`audience`、`offer_assumptions`、`channels`、`assets_needed`、`approval_items` |
| `sales_analysis` | 店长：“比较上周三家店的销量。” | `SalesAnalysis`：经营分析简报 | `period`、`metrics`、`comparisons`、`findings`、`data_gaps`、`follow_up` |
| `multi_intent` | 顾客同时要求改订单和投诉服务 | `SplitRequest`：拆分与路由清单 | `subrequests`、`intent_for_each`、`priority`、`shared_context` |
| `other_request` | 与以上范围无关或暂时无法识别 | `TriageNote`：澄清或转人工记录 | `summary`、`reason_unclassified`、`clarifying_question`、`handoff_target` |

## 供 Stage 01 测试的输入

| 输入 | 期望 intent | 后续产物 |
| --- | --- | --- |
| “下周六公司活动需要 20 杯咖啡，预算 500 元，怎么订？” | `group_order` | 团体订单线索单；缺少地点、取货或配送方式时列为待确认。 |
| “不喝奶，想点不太甜的，推荐什么？” | `menu_advice` | 推荐分析；菜单和配料未接入时，不编造具体产品。 |
| “订单 123 的自取时间想改到 15 点。” | `order_support` | 订单处理单；先核查订单状态，不声称已经修改。 |
| “上周三家门店哪家销售下降最多？” | `sales_analysis` | 经营分析简报；报表缺失时标记无法计算的指标。 |
| “积分没到，顺便帮我把订单取消。” | `multi_intent` | 拆成会员与订单两个子请求。 |

## 写后续 Python Stage 时的边界

- Stage 01 只做分流和通用任务归一化；业务回答由专用 Stage 负责。
- 每个专用 Stage 定义自己的 dataclass/JSON Schema。事实答复、处理单、推荐和分析简报需要不同字段。
- 结构化结果区分**已核实事实**、**合理假设**与**待查询数据**。缺少真实数据时仍可产出有用的处理单或答复草稿，但不能生成虚假的业务结论。
- 首批适合实现 `group_order`、`order_support`、`sales_analysis`：它们分别练习信息收集、状态核查和数据分析，结果结构差异明显。
