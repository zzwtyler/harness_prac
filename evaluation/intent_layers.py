"""Fixed-case before/after evaluation of intent structure and source ownership."""
import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.main import execute_task
from core import runtime, context, paths

# Expectations are independent, hand-authored fixtures; do not infer from output.
CASES = [
    ('group', '下周六公司活动需要20杯咖啡，预算500元，怎么订？', ['group_order'], [('group_order', 'quantity', '20'), ('group_order', 'budget', '500')]),
    ('menu', '不喝奶，想点不太甜的，推荐什么？', ['menu_advice'], [('menu_advice', 'dietary_constraint', '不喝奶'), ('menu_advice', 'preference', '不太甜')]),
    ('order', '订单123的自取时间想改到15点。', ['order_support'], [('order_support', 'order_id', '123'), ('order_support', 'time', '15')]),
    ('sales', '上周三家门店哪家销售下降最多？', ['sales_analysis'], [('sales_analysis', 'period', '上周'), ('sales_analysis', 'comparison', '下降')]),
    ('multi', '积分没到，顺便帮我把订单取消。', ['membership_help', 'order_support'], [('membership_help', 'issue', '积分'), ('order_support', 'request', '取消')]),
    ('store', '哪家店离我近？几点营业？', ['store_info'], []),
    ('complaint', '上次拿到的饮品做错了，请帮我处理。', ['complaint'], [('complaint', 'issue', '做错')]),
    ('member', '积分为什么没到账？', ['membership_help'], [('membership_help', 'issue', '积分')]),
    ('campaign', '我是店长，下个月做工作日早餐活动，帮我拟一份策划。', ['campaign_brief'], [('campaign_brief', 'objective', '早餐')]),
    ('other', '帮我修一下办公室的打印机。', ['other_request'], [('other_request', 'request', '打印机')]),
    ('social', '你好，谢谢！', [], []),
    ('background', '补充信息：预算500元。', [], []),
    ('mixed_other', '请取消订单A123，另外帮我修打印机。', ['order_support', 'other_request'], [('order_support', 'order_id', 'A123'), ('other_request', 'request', '打印机')]),
    ('same_business', '请取消订单A123，另一个订单B456改成明天自取。', ['order_support', 'order_support'], [('order_support', 'order_id', 'A123'), ('order_support', 'date|time', '明天')]),
    ('negation', '公司活动不是20杯，是12杯；不要配送，要自取，怎么订？', ['group_order'], [('group_order', 'quantity', '不是20杯'), ('group_order', 'quantity', '12杯'), ('group_order', 'pickup_or_delivery', '不要配送')]),
    ('ownership', '会员账号M789的积分没到，请取消订单A123。', ['membership_help', 'order_support'], [('membership_help', 'account_id', 'M789'), ('order_support', 'order_id', 'A123')]),
]


# Held out from prompt/format iteration; report separately and do not tune against it.
HOLDOUT_CASES = [
    ('polite_cancel', '谢谢，帮我取消订单C802。', ['order_support'], [('order_support', 'order_id', 'C802'), ('order_support', 'request', '取消')]),
    ('background_preference', '补充一下：不要加糖。', [], []),
    ('group_dietary', '周五给团队订30杯咖啡，其中两杯不能含牛奶。', ['group_order'], [('group_order', 'quantity', '30'), ('group_order', 'dietary_constraint', '不能含牛奶')]),
    ('same_type_goals', '帮我查订单C802状态，另外取消订单D903。', ['order_support', 'order_support'], [('order_support', 'order_id', 'C802'), ('order_support', 'order_id', 'D903')]),
    ('known_and_other', '我的积分还没到账，另外请帮我安装电脑软件。', ['membership_help', 'other_request'], [('membership_help', 'issue', '积分'), ('other_request', 'request', '软件')]),
    ('group_correction', '公司团订不要18杯，改成9杯，周五自取。', ['group_order'], [('group_order', 'quantity', '不要18杯'), ('group_order', 'quantity', '9杯'), ('group_order', 'pickup_or_delivery', '自取')]),
]


def score(case, output):
    _, source, types, fields = case
    data = output['intent']
    expected = 'no_intent' if not types else types[0] if len(types) == 1 else 'multi_intent'
    units = data.get('intents', [])
    keywords = data['keywords']
    allowed = {(c['text'], c['start'], c['end']) for c in context.source_clauses(source)}
    grounded = all((k['text'], k['start'], k['end']) in allowed for k in keywords)
    field_match = all(any(k['category'] in cat.split('|') and text in k['text'] for k in keywords) for _, cat, text in fields)
    ownership = all(any(u['intent'] == kind and any(k['category'] in cat.split('|') and text in k['text'] for k in u['keywords']) for u in units) for kind, cat, text in fields)
    unit_match = sorted(u['intent'] for u in units) == sorted(types) and ('intents' in data)
    if case[0] == 'ownership':
        ownership = ownership and all(not any(k['category'] == ('order_id' if u['intent'] == 'membership_help' else 'account_id') for k in u['keywords']) for u in units)
    if case[0] == 'store':
        field_match = field_match and not any(k['category'] in ('location', 'time') for k in keywords)
    return dict(routing=data['intent'] == expected, fields=field_match, source_grounded=grounded,
                intent_units=unit_match, ownership=ownership if fields else unit_match)


def run(path, repeats):
    report = {'model': 'qwen3:4b', 'think': False, 'temperature': 0.2, 'repeats': repeats, 'planned_cases': len(CASES) * repeats,
              'source_hashes': {str(p.relative_to(paths.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.execution_sources()}, 'cases': []}
    original = runtime.read_model_response
    for repeat in range(repeats):
        for case in CASES:
            metrics = []
            def measured(req, timeout):
                raw = original(req, timeout)
                metrics.append({k: raw.get(k) for k in ('prompt_eval_count', 'eval_count', 'total_duration')})
                return raw
            started = perf_counter()
            try:
                with patch.object(runtime, 'read_model_response', side_effect=measured):
                    output = execute_task(case[1])
                item = dict(id=case[0], repeat=repeat, source=case[1], expected_types=case[2], output=output, checks=score(case, output))
            except (OSError, ValueError, TypeError, KeyError) as exc:
                item = dict(id=case[0], repeat=repeat, source=case[1], error=f'{type(exc).__name__}: {exc}', checks={k: False for k in ('routing','fields','source_grounded','intent_units','ownership')})
            item.update(elapsed_seconds=round(perf_counter()-started, 3), calls=len(metrics), metrics=metrics)
            report['cases'].append(item)
            report['summary'] = {k: sum(c['checks'][k] for c in report['cases']) for k in item['checks']}
            report['summary'].update(total=len(report['cases']), calls=sum(c['calls'] for c in report['cases']), mean_seconds=round(statistics.mean(c['elapsed_seconds'] for c in report['cases']),3), median_seconds=round(statistics.median(c['elapsed_seconds'] for c in report['cases']),3))
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
            print(case[0], item['checks'], item['elapsed_seconds'], item.get('error',''), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--holdout', action='store_true')
    args = parser.parse_args()
    if args.holdout:
        CASES = HOLDOUT_CASES
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error('output already exists')
    run(args.output, args.repeats)
