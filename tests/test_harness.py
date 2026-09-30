import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import StageRegistry
from core import task_loader as _task_loader
load_task = _task_loader.load_task

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '下周六公司活动需要 20 杯咖啡，预算 500 元，怎么订？'
PLAN = {'intent': 'group_order', 'selections': [{'category': 'date', 'clause_index': 0}, {'category': 'quantity', 'clause_index': 0}, {'category': 'budget', 'clause_index': 1}, {'category': 'request', 'clause_index': 2}]}


def response(value):
    content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    raw = {'message': {'content': content, 'thinking': 'PRIVATE_THINKING'}, 'done': True}
    if isinstance(value, str) and len(value.strip()) == 1 and value.strip() in 'ABCDEFGHIJKLM':
        option = value.strip()
        raw['logprobs'] = [{'token': option, 'bytes': [ord(option)], 'logprob': -0.01005033585350145}]
    return io.BytesIO(json.dumps(raw).encode())


def model_responder(plan):
    """Serve explicit routing/detail protocol fixtures at the HTTP boundary."""
    def upstream(req, timeout):
        return respond_to_plan(req, plan)
    return upstream


def respond_to_plan(req, plan):
    payload = json.loads(req.data)
    # Fixtures now encode the letter -> one-shot annotation wire contract.
    # Semantic choices are explicit fixtures; never synthesize a request label.
    letters = {'store_info': 'A', 'menu_advice': 'B', 'order_support': 'C', 'group_order': 'D',
               'complaint': 'E', 'membership_help': 'F', 'campaign_brief': 'G', 'sales_analysis': 'H',
               'other_request': 'I', 'multi_intent': 'J', 'no_intent': 'K'}
    if 'format' not in payload:
        extra = set(plan) - {'intent', 'selections'}
        value = letters.get(plan['intent'], 'invalid') if not extra else 'invalid extra output'
    else:
        data = json.loads(payload['messages'][1]['content'])
        names = ['membership_help', 'order_support'] if plan['intent'] == 'multi_intent' else [plan['intent']]
        value = {'intents': [{'intent': name, 'subtype': 'unspecified',
                  'clause_ids': [clause['id'] for clause in data['clauses']],
                  'request': [f"clause_{s['clause_index']}" for s in plan['selections'] if s['category'] == 'request'],
                  'selections': [{'category': s['category'], 'clause_id': f"clause_{s['clause_index']}"}
                                 for s in plan['selections'] if s['category'] != 'request']} for name in names]}
    return response(value)


class ExtractionTests(unittest.TestCase):
    def pipeline(self):
        return load_task(ROOT / 'harness/main.py')

    def test_pipeline_copies_source_with_two_scoped_calls_and_excludes_project_examples(self):
        sent = []
        def upstream(req, timeout):
            sent.append(json.loads(req.data))
            return respond_to_plan(req, PLAN)
        with patch('core.runtime.open_model_request', side_effect=upstream):
            result = self.pipeline().run_harness(SOURCE, project_context='北京门店8点营业，订单123')
        self.assertEqual(len(sent), 2)
        self.assertNotIn('北京', sent[0]['messages'][1]['content'])
        self.assertNotIn('123', sent[0]['messages'][1]['content'])
        self.assertEqual(result['stage'], '02_group_order')
        self.assertEqual(result['result']['budget'], ['预算 500 元'])
        self.assertEqual(result['result']['quantity'], ['下周六公司活动需要 20 杯咖啡'])
        self.assertEqual(result['result']['location'], [])
        self.assertEqual(result['result']['pickup_or_delivery'], [])
        self.assertEqual(result['result']['source_text'], SOURCE)
        for keyword in result['intent']['keywords']:
            self.assertEqual(SOURCE[keyword['start']:keyword['end']], keyword['text'])
        self.assertNotIn('PRIVATE_THINKING', json.dumps(result))

    def test_request_without_business_values_produces_no_default_facts(self):
        with patch('core.runtime.open_model_request', side_effect=model_responder({'intent': 'store_info', 'selections': [{'category': 'request', 'clause_index': 0}]})):
            result = self.pipeline().run_harness('哪家店离我近？几点营业？')
        self.assertEqual(result['result']['location'], [])
        self.assertEqual(result['result']['opening_hours'], [])
        self.assertNotIn('reply_draft', result['result'])
        self.assertNotIn('assumptions', result['result'])

    def test_invalid_indices_and_unknown_categories_fail_closed(self):
        for index in (-1, 100, True):
            with self.subTest(index=index):
                plan = {'intent': 'store_info', 'selections': [{'category': 'location', 'clause_index': index}]}
                with patch('core.runtime.open_model_request', side_effect=model_responder(plan)):
                    with self.assertRaises(ValueError):
                        self.pipeline().run_harness('哪家店离我近？')
        plan = {'intent': 'store_info', 'selections': [{'category': 'invented', 'clause_index': 0}]}
        with patch('core.runtime.open_model_request', side_effect=model_responder(plan)):
            with self.assertRaises(ValueError):
                self.pipeline().run_harness('哪家店离我近？')

    def test_extra_model_text_is_rejected_not_saved_as_a_fact(self):
        plan = {**PLAN, 'reply_draft': '北京8点营业'}
        with tempfile.TemporaryDirectory() as tmp:
            with patch('core.runtime.open_model_request', side_effect=model_responder(plan)):
                with self.assertRaises(ValueError):
                    self.pipeline().run_harness(SOURCE, output_directory=Path(tmp))
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ['00_run_state.json'])

    def test_negation_and_corrections_keep_whole_clauses_in_source_order(self):
        source = '请安排团订，不要配送，要自取；不是20杯，是12杯。'
        plan = {'intent': 'group_order', 'selections': [
            {'category': 'request', 'clause_index': 0},
            {'category': 'quantity', 'clause_index': 4}, {'category': 'quantity', 'clause_index': 3},
            {'category': 'pickup_or_delivery', 'clause_index': 1}, {'category': 'pickup_or_delivery', 'clause_index': 2},
            {'category': 'quantity', 'clause_index': 4}]}
        with patch('core.runtime.open_model_request', side_effect=model_responder(plan)):
            result = self.pipeline().run_harness(source)
        self.assertEqual(result['result']['quantity'], ['不是20杯', '是12杯'])
        self.assertEqual(result['result']['pickup_or_delivery'], ['不要配送', '要自取'])

    def test_direct_stage_uses_the_same_grounded_extraction(self):
        task = load_task(ROOT / 'core/02_task_classes/membership_help.py')
        plan = {'intent': 'membership_help', 'selections': [{'category': 'issue', 'clause_index': 0}, {'category': 'request', 'clause_index': 0}]}
        with patch('core.runtime.open_model_request', side_effect=model_responder(plan)):
            result = task.analyze_task('积分为什么没到账？')
        self.assertEqual(result.issue, ['积分为什么没到账'])
        self.assertEqual(result.policy, [])
        self.assertEqual(result.account_id, [])
        self.assertFalse(hasattr(result, 'reply_draft'))

    def test_all_stages_are_extractive_and_offer_typed_output(self):
        stages = StageRegistry(ROOT / 'web/stages').all()
        self.assertEqual(len(stages), 12)
        self.assertEqual(len({s.model_type.__name__ for s in stages}), 12)
        for stage in stages:
            self.assertTrue(callable(getattr(stage, 'runner', None)))
            self.assertIn('source_text', stage.output_schema['properties'])
            self.assertNotIn('reply_draft', stage.output_schema['properties'])

    def test_outputs_use_numbered_names_and_do_not_include_thinking(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('core.runtime.open_model_request', side_effect=model_responder(PLAN)):
                self.pipeline().run_harness(SOURCE, output_directory=Path(tmp))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['00_run_state.json', '01_user_intent.json', '02_group_order.json', '98_verification.json'])
            self.assertNotIn('PRIVATE_THINKING', ''.join(p.read_text() for p in Path(tmp).iterdir()))

    def test_empty_request_is_rejected(self):
        for source in ('  ', '？！；'):
            with self.subTest(source=source), patch('core.runtime.open_model_request', side_effect=model_responder(PLAN)), self.assertRaises(ValueError):
                self.pipeline().run_harness(source)

    def test_unknown_intent_is_rejected(self):
        with patch('core.runtime.open_model_request', side_effect=model_responder({'intent': 'invented', 'selections': []})):
            with self.assertRaises(ValueError):
                self.pipeline().run_harness('你好')

    def test_numeric_commas_remain_in_whole_amounts(self):
        from core import extraction as _extraction
        source_clauses = _extraction.source_clauses
        self.assertEqual([c['text'] for c in source_clauses('预算1,500元，需要1,000杯')], ['预算1,500元', '需要1,000杯'])

    def test_direct_formatter_rejects_partial_negation_span(self):
        from core import extraction as _extraction
        ExtractedInput = _extraction.ExtractedInput
        Keyword = _extraction.Keyword
        stage = load_task(ROOT / 'core/02_task_classes/group_order.py')
        with patch('core.runtime.open_model_request', side_effect=model_responder({'intent': 'group_order', 'selections': [
                {'category': 'request', 'clause_index': 0}, {'category': 'pickup_or_delivery', 'clause_index': 1}]})):
            forged = _extraction.extract_user_input('请团订，不要配送')
        forged.intents[0].keywords = [forged.intents[0].keywords[0], Keyword('pickup_or_delivery', '配送', 6, 8)]
        with self.assertRaises(ValueError):
            stage.from_extraction(forged)

    def test_runtime_stage_entrypoint_returns_only_grounded_content(self):
        from core import runtime as _runtime
        run_stage = _runtime.run_stage
        stage = StageRegistry(ROOT / 'web/stages').get('group_order')
        with patch('core.runtime.open_model_request', side_effect=model_responder(PLAN)):
            raw, result = run_stage(stage, SOURCE, think=False)
        self.assertEqual(result.budget, ['预算 500 元'])
        self.assertNotIn('thinking', raw['message'])
        self.assertNotIn('PRIVATE_THINKING', json.dumps(raw))

    def test_comparison_preserves_error_records(self):
        comparison = load_task(ROOT / 'evaluation/comparison.py')
        with tempfile.TemporaryDirectory() as tmp:
            with patch('core.runtime.open_model_request', side_effect=OSError('offline')):
                report = comparison.run_comparison(Path(tmp), cases=[{'id': '01_group_order', 'request': SOURCE, 'expected_intent': 'group_order'}])
            self.assertEqual(report['cases'][0]['harness']['status'], 'error')
            self.assertTrue((Path(tmp) / '03_comparison.json').exists())

    def test_truncated_model_response_is_reported_as_failure(self):
        raw = io.BytesIO(json.dumps({'message': {'content': json.dumps(PLAN)}, 'done_reason': 'length'}).encode())
        with patch('core.runtime.open_model_request', return_value=raw):
            with self.assertRaises(ValueError):
                self.pipeline().run_harness(SOURCE)

    def test_interruption_preserves_completed_baseline(self):
        comparison = load_task(ROOT / 'evaluation/comparison.py')
        with tempfile.TemporaryDirectory() as tmp:
            with patch('core.runtime.open_model_request', side_effect=[response({'reply': '请确认地点'}), KeyboardInterrupt()]):
                with self.assertRaises(KeyboardInterrupt):
                    comparison.run_comparison(Path(tmp), cases=[{'id': '01_group_order', 'request': SOURCE, 'expected_intent': 'group_order'}])
            self.assertTrue((Path(tmp) / '01_group_order/00_direct_answer.json').exists())

if __name__ == '__main__':
    unittest.main()
