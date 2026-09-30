"""Reproducible direct-answer vs Harness comparison; only final artifacts persist."""
import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from core import runtime as _runtime
run_structured_chat = _runtime.run_structured_chat
from core import task_loader as _task_loader
load_task = _task_loader.load_task
from core import extraction as _extraction
source_clauses = _extraction.source_clauses
from core import paths as _paths
execution_sources = _paths.execution_sources

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    {'id': '01_group_order', 'request': '下周六公司活动需要 20 杯咖啡，预算 500 元，怎么订？', 'expected_intent': 'group_order'},
    {'id': '02_menu_advice', 'request': '不喝奶，想点不太甜的，推荐什么？', 'expected_intent': 'menu_advice'},
    {'id': '03_order_support', 'request': '订单 123 的自取时间想改到 15 点。', 'expected_intent': 'order_support'},
    {'id': '04_sales_analysis', 'request': '上周三家门店哪家销售下降最多？', 'expected_intent': 'sales_analysis'},
    {'id': '05_multi_intent', 'request': '积分没到，顺便帮我把订单取消。', 'expected_intent': 'multi_intent'},
    {'id': '06_store_info', 'request': '哪家店离我近？几点营业？', 'expected_intent': 'store_info'},
    {'id': '07_complaint', 'request': '上次拿到的饮品做错了，请帮我处理。', 'expected_intent': 'complaint'},
    {'id': '08_membership_help', 'request': '积分为什么没到账？', 'expected_intent': 'membership_help'},
    {'id': '09_campaign_brief', 'request': '我是店长，下个月做工作日早餐活动，帮我拟一份策划。', 'expected_intent': 'campaign_brief'},
    {'id': '10_other_request', 'request': '帮我修一下办公室的打印机。', 'expected_intent': 'other_request'},
]


@dataclass
class DirectAnswer:
    reply: str


BASELINE_PROMPT = '''你是虚构的拾光咖啡门店客服与运营助理。根据项目背景和当前请求，直接给出员工审核用的中文答复草稿。
背景中的示例不是当前请求。未接入的数据不能编造，不能声称已执行订单、退款或发布操作。
仅在 reply 字段中给出最终答复。'''


def check_result(case, output):
    """Check source fidelity and a few extraction fixtures, not factual truth."""
    if output['status'] != 'ok':
        return {'intent_matches': False, 'source_grounded': False, 'fixture_requirements': False}
    result = output['output']['result']
    normalized = output['output']['intent']
    source = case['request']
    grounded = result.get('source_text') == source and normalized.get('source_text') == source
    allowed = {(c['start'], c['end'], c['text']) for c in source_clauses(source)}
    for keyword in [*normalized['keywords'], *result['keywords']]:
        grounded = grounded and (keyword['start'], keyword['end'], keyword['text']) in allowed
    for key, value in result.items():
        if key not in ('source_text', 'keywords', 'intents'):
            grounded = grounded and isinstance(value, list) and all(isinstance(v, str) and v in {c[2] for c in allowed} for v in value)
    expected = case['expected_intent']
    # An input clause can be used in several slots; quantities/dates are not normalized.
    text = lambda key: ' '.join(result.get(key, []))
    if expected == 'group_order':
        fixture = '20' in text('quantity') and '500' in text('budget') and result.get('location') == []
    elif expected == 'menu_advice':
        fixture = '不喝奶' in text('dietary_constraints') and '不太甜' in text('preferences')
    elif expected == 'order_support':
        fixture = '123' in text('order_id') and '15' in text('time') and result.get('current_status') == []
    elif expected == 'sales_analysis':
        fixture = '上周' in text('period') and '下降' in text('comparison_request')
    elif expected == 'multi_intent':
        fixture = '积分' in text('requests') and '取消' in text('requests') and result.get('order_id') == []
    elif expected == 'store_info':
        fixture = result.get('location') == [] and result.get('opening_hours') == []
    elif expected == 'complaint':
        fixture = '做错' in text('issue') and result.get('impact') == []
    elif expected == 'membership_help':
        fixture = result.get('policy') == [] and result.get('account_id') == [] and '积分' in text('issue')
    elif expected == 'campaign_brief':
        fixture = '早餐' in text('objective') and result.get('budget') == [] and result.get('offer') == []
    else:
        fixture = '打印机' in text('request')
    return {'intent_matches': normalized['intent'] == expected,
            'source_grounded': bool(grounded), 'fixture_requirements': bool(fixture)}


def capture(operation):
    started = perf_counter()
    try:
        return {'status': 'ok', 'output': operation(), 'elapsed_seconds': round(perf_counter() - started, 3)}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {'status': 'error', 'error': f'{type(exc).__name__}: {exc}', 'elapsed_seconds': round(perf_counter() - started, 3)}


def write_report(report, directory):
    (directory / '03_comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = [
        '# 直接回答与 Harness 输出对比', '',
        f"模型：`{report['model']}`；think：`{report['think']}`；生成时间：{report['generated_at']}。", '',
        f"已保存 {len(report['cases'])}/{report['planned_case_count']} 个样例；状态：{report['run_status']}。", '',
        '两组使用相同模型、temperature=0.2 和 think 设置，直接回答调用一次模型；Harness业务请求通常调用两次，无诉求一次，失败时最多尝试两轮。直接回答保留项目背景；纯提取Harness仅接收当前用户输入，业务字段由Python复制原文并整理。',
        '这是两种工作方式的对比，不是控制相同提示词的模型评测。Harness的事实值由原文复制，保留否定/纠正片段；分类标签不是已核实业务事实。',
        '下列自动检查只覆盖分类、字段和固定样例的部分约束，不能证明全文事实正确，也不是两组回答质量评分。耗时包含本地加载及缓存影响，不作性能结论。', '',
        '| 样例 | 期望 intent | 实际 intent | 直接回答 | Harness | 自动检查 | 耗时：直接 / Harness |',
        '| --- | --- | --- | --- | --- | --- | --- |',
    ]
    for case in report['cases']:
        base, harness = case['baseline'], case['harness']
        actual = harness.get('output', {}).get('intent', {}).get('intent', '运行失败')
        checks = '通过' if all(case['checks'].values()) else '未通过'
        lines.append(f"| {case['id']} | {case['expected_intent']} | {actual} | {base['status']} | {harness['status']} | {checks} | {base['elapsed_seconds']}s / {harness['elapsed_seconds']}s |")
    for case in report['cases']:
        lines += ['', f"## {case['id']}", '', f"输入：{case['request']}", '', '### 直接回答', '']
        base = case['baseline']
        lines += [base['output']['reply'] if base['status'] == 'ok' else base['error']]
        lines += ['', '### Harness 最终输出', '', '```json', json.dumps(case['harness'].get('output', case['harness']), ensure_ascii=False, indent=2), '```', '', '自动检查：`' + json.dumps(case['checks'], ensure_ascii=False) + '`']
    (directory / '03_comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def run_comparison(directory: Path, *, cases=None, model='qwen3:4b',
                   base_url='http://127.0.0.1:11434', think=False, progress=False):
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('对比目录非空，请选择新目录以保留旧结果')
    directory.mkdir(parents=True, exist_ok=True)
    pipeline = load_task(ROOT / 'harness/main.py')
    context = (ROOT / 'docs/PROJECT_BRIEF.md').read_text(encoding='utf-8')
    settings = dict(model=model, base_url=base_url, think=think)
    selected_cases = list(CASES if cases is None else cases)
    sources = [*execution_sources(), *ROOT.glob('web/**/*.py'), Path(__file__)]
    report = {'model': model, 'think': think, 'temperature': 0.2, 'num_predict': 4096, 'num_ctx': 32768, 'harness_max_attempts': 2,
              'planned_case_count': len(selected_cases), 'run_status': 'partial',
              'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)},
              'generated_at': datetime.now(timezone.utc).isoformat(),
              'project_context': context, 'cases': []}
    for case in selected_cases:
        if progress:
            print(f"运行 {case['id']}…", flush=True)
        content = f"【项目背景】\n{context}\n\n【当前请求】\n{case['request']}"
        baseline = capture(lambda: asdict(run_structured_chat(content, result_type=DirectAnswer, system_prompt=BASELINE_PROMPT, **settings)))
        case_dir = directory / case['id']
        case_dir.mkdir()
        (case_dir / '00_direct_answer.json').write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        harness = capture(lambda: pipeline.run_harness(case['request'], project_context=context, output_directory=case_dir, **settings))
        item = {**case, 'baseline': baseline, 'harness': harness, 'checks': check_result(case, harness)}
        if harness['status'] != 'ok':
            (case_dir / '02_harness.json').write_text(json.dumps(harness, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report['cases'].append(item)
        report['run_status'] = 'complete' if len(report['cases']) == len(selected_cases) else 'partial'
        write_report(report, directory)
    if not report['cases']:
        report['run_status'] = 'complete'
        write_report(report, directory)
    return report


def main():
    parser = argparse.ArgumentParser(description='实跑 brief 样例并保存直接回答与 Harness 的结果对比')
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs' / datetime.now().strftime('%Y%m%d_%H%M%S'))
    parser.add_argument('--model', default='qwen3:4b')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    parser.add_argument('--think', action='store_true')
    parser.add_argument('--brief-only', action='store_true', help='只运行 brief 原始五个测试输入')
    args = parser.parse_args()
    try:
        report = run_comparison(args.output, cases=CASES[:5] if args.brief_only else None,
                                model=args.model, base_url=args.base_url, think=args.think, progress=True)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'对比运行失败：{exc}\n')
    print(f'结果与对比：{args.output.resolve()}')
    if any(case[side]['status'] != 'ok' for case in report['cases'] for side in ('baseline', 'harness')):
        parser.exit(1, '存在运行失败的样例，详见对比文件。\n')
    if any(not all(case['checks'].values()) for case in report['cases']):
        parser.exit(2, '存在未通过自动检查的样例，详见对比文件。\n')


if __name__ == '__main__':
    main()
