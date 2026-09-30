"""Business-specific selection rules and deterministic information layers.

not_observed is a review hint, not proof that the user omitted a value.
verification_needed names future checks; no business data is fetched here.
"""
from core import models

COMMON = ('request', 'constraint')
BUSINESS = {
    'group_order': ('date', 'time', 'quantity', 'budget', 'pickup_or_delivery', 'location', 'preference', 'dietary_constraint'),
    'order_support': ('order_id', 'current_status', 'time', 'date', 'pickup_or_delivery', 'location', 'quantity', 'preference', 'dietary_constraint'),
    'store_info': ('location', 'time'),
    'menu_advice': ('preference', 'dietary_constraint', 'budget'),
    'complaint': ('issue', 'impact', 'order_id'),
    'membership_help': ('issue', 'account_id', 'order_id', 'policy'),
    'campaign_brief': ('objective', 'date', 'period', 'audience', 'offer', 'channel', 'asset', 'budget'),
    'sales_analysis': ('period', 'metric', 'comparison', 'location'),
    'other_request': ('issue',),
}
SUBTYPES = {
    'group_order': ('new_order', 'unspecified'),
    'order_support': ('query', 'modify', 'cancel', 'unspecified'),
    'store_info': ('location', 'hours', 'general', 'unspecified'),
    'menu_advice': ('recommendation', 'unspecified'),
    'complaint': ('product', 'service', 'unspecified'),
    'membership_help': ('points', 'account', 'benefits', 'unspecified'),
    'campaign_brief': ('planning', 'unspecified'),
    'sales_analysis': ('comparison', 'summary', 'unspecified'),
    'other_request': ('unspecified',),
}
OPERATION = {
    ('order_support', 'modify'): ('time', 'date', 'pickup_or_delivery', 'location', 'quantity', 'preference', 'dietary_constraint'),
    ('membership_help', 'points'): ('issue', 'order_id'),
    ('membership_help', 'benefits'): ('policy',),
    ('store_info', 'location'): ('location',),
    ('store_info', 'hours'): ('time',),
    ('sales_analysis', 'comparison'): ('comparison',),
}
FOLLOW_UP = {
    'group_order': ('quantity', 'date'),
    'order_support': ('order_id',),
    'membership_help': ('account_id',),
    'sales_analysis': ('period', 'metric'),
    'campaign_brief': ('objective', 'period'),
}
VERIFY = {
    'group_order': ('availability',),
    'order_support': ('order_status',),
    'store_info': ('store_directory',),
    'menu_advice': ('menu_and_allergens',),
    'complaint': ('reported_issue',),
    'membership_help': ('account_records',),
    'campaign_brief': ('campaign_feasibility',),
    'sales_analysis': ('sales_records',),
    'other_request': (),
}


def categories(intent):
    return (*COMMON, *BUSINESS[intent])


def summarize(units):
    return 'no_intent' if not units else units[0].intent if len(units) == 1 else 'multi_intent'


def merge_keywords(units):
    unique = {}
    for unit in units:
        for keyword in unit.keywords:
            unique.setdefault((keyword.start, keyword.end, keyword.category), keyword)
    return sorted(unique.values(), key=lambda k: (k.start, k.category))


def enrich(intent, subtype, evidence, keywords):
    if subtype not in SUBTYPES[intent]:
        raise ValueError(f'子类型不属于当前意图：{intent}/{subtype}')
    if any(k.category not in categories(intent) for k in keywords):
        raise ValueError('字段不属于当前意图允许的类别')
    operation = OPERATION.get((intent, subtype), ())
    information = models.Information(
        common=[k for k in keywords if k.category in COMMON],
        business=[k for k in keywords if k.category not in (*COMMON, *operation)],
        operation=[k for k in keywords if k.category in operation],
    )
    observed = {k.category for k in keywords}
    not_observed = [c for c in FOLLOW_UP.get(intent, ()) if c not in observed]
    # A campaign date is also evidence of its intended period.
    if intent == 'campaign_brief' and 'date' in observed and 'period' in not_observed:
        not_observed.remove('period')
    verification = list(VERIFY[intent])
    if (intent, subtype) == ('order_support', 'cancel'):
        verification.append('cancellation_policy')
    return models.IntentUnit(intent, subtype, evidence, keywords, information, not_observed, verification)


SUBTYPE_DESCRIPTIONS = {
    'new_order': '团体新下单或询问如何订购', 'query': '查询已有订单',
    'modify': '修改已有订单的信息或自取安排（不含取消）', 'cancel': '取消已有订单',
    'location': '门店位置距离', 'hours': '门店营业时间', 'general': '同一门店的位置及时间等综合咨询',
    'recommendation': '饮品口味或忌口推荐', 'product': '饮品商品做错或质量投诉',
    'service': '服务体验投诉', 'points': '积分查询、积分未到账', 'account': '会员账户问题',
    'benefits': '会员权益规则', 'planning': '制定营销活动方案',
    'comparison': '销售比较、升降分析', 'summary': '销售统计汇总',
    'unspecified': '只有在不能确定更具体操作时使用',
}
CATEGORY_DESCRIPTIONS = {
    'request': '本片段的动作、问题或实际异常隐含求助；每独立目标至少一处。可以与专用字段兼标，彼此不能替代。身份、编号、纯参数、规则、假设或否定异常本身不是request，不为满足完整性而强贴',
    'constraint': '只能用于没有专用字段的额外限制。数量、预算、日期、取送、口味、忌口本身不重复标constraint；同句确有另一个额外限制才兼标',
    'date': '明确日期或相对日期（保留原文）', 'time': '明确时间或时间变更；询问几点不是已知时间',
    'quantity': '数量，含被否定的旧数量和纠正的新数量', 'budget': '预算金额或预算限制',
    'location': '用户提供的具体位置，询问哪里不是已知位置',
    'pickup_or_delivery': '自取/配送要求，含否定及纠正', 'order_id': '明确的订单编号；仅提及订单或取消订单但没有编号时必须为空',
    'current_status': '用户描述的订单当前状态', 'preference': '甜度、口味偏好',
    'dietary_constraint': '忌口、过敏和饮食禁忌', 'issue': '本片段叙述用户实际发生的异常；仅提出处理/查询动作，或正常规则、假设、否定异常均不是issue',
    'impact': '用户描述的影响', 'account_id': '会员账户编号', 'policy': '用户转述的消费、积分到账、会员权益条件或规定；规则本身不是问题，也不代表已经核实',
    'period': '统计或活动期间', 'metric': '销售/经营指标', 'comparison': '比较差异或升降要求',
    'objective': '活动主题或期望达成的业务结果。不必出现目标二字。单独的受众、优惠、渠道、资源、预算分别归各自专用字段，不重复算目标；身份和请写方案不是目标', 'audience': '受众', 'offer': '优惠', 'channel': '渠道', 'asset': '资源',
}


def detail_model(routed_intents):
    """Expose only applicable subtypes/slots and require one result per routed unit."""
    from dataclasses import make_dataclass
    from typing import Literal
    units = []
    for index, routed in enumerate(routed_intents):
        fields = [('subtype', Literal[SUBTYPES[routed.intent]])]
        clauses = tuple(f'clause_{i}' for i in sorted(routed.clause_indices))
        fields.extend((category, list[Literal[clauses]]) for category in categories(routed.intent))
        unit = make_dataclass(f'Intent{index}Details', fields)
        units.append((f'intent_{index}', unit))
    return make_dataclass('ScopedDetails', units)


def structured_model(decision, clauses):
    """Bind route, source ids and slots before asking Qwen to annotate units."""
    from dataclasses import make_dataclass
    from typing import Literal, get_args
    from core import schema
    routes = get_args(models.BusinessIntent) if decision.routing == 'multi_intent' else (decision.routing,)
    subtypes = tuple(dict.fromkeys(s for route in routes for s in SUBTYPES[route]))
    slots = tuple(dict.fromkeys(c for route in routes for c in categories(route) if c != 'request'))
    clause_ids = tuple(f'clause_{i}' for i in range(len(clauses)))
    selection = make_dataclass('ScopedSelection', [('category', Literal[slots]), ('clause_id', Literal[clause_ids])])
    unit = make_dataclass('StructuredUnit', [('intent', Literal[routes]), ('subtype', Literal[subtypes]),
             ('clause_ids', list[Literal[clause_ids]]),
             ('request', list[Literal[clause_ids]], schema.schema_field(description=CATEGORY_DESCRIPTIONS['request'])),
             ('selections', list[selection])])
    return make_dataclass('StructuredIntent', [('intents', list[unit])])
