"""Required goal-source wire tests with explicit HTTP fixtures, never live models."""
import json
import unittest
from unittest.mock import patch

from core import context, intent_details, models, schema, verification
from harness.main import execute_task as _execute_task
from test_dual_model_pipeline import ScriptedModel


def execute_task(*args, **kwargs):
    """Exercise the R3 wire/guard directly; cascade has its own defaults tests."""
    kwargs.setdefault('cascade_enabled', False)
    return _execute_task(*args, **kwargs)


def annotation(*, request, clause_ids=('clause_0',), selections=()):
    return {'intents': [{'intent': 'order_support', 'subtype': 'modify',
            'clause_ids': list(clause_ids), 'request': list(request),
            'selections': [{'category': category, 'clause_id': clause_id}
                           for category, clause_id in selections]}]}


class RequiredRequestWireTests(unittest.TestCase):
    def test_each_unit_requires_request_and_selection_enum_excludes_it(self):
        decision = models.Decision('C', 'request', 'infer', 'order_support')
        result_type = intent_details.structured_model(decision, context.source_clauses('请修改当前订单'))
        unit = schema.model_json_schema(result_type)['properties']['intents']['items']
        self.assertIn('request', unit['required'])
        self.assertEqual(unit['properties']['request']['type'], 'array')
        self.assertEqual(unit['properties']['request']['items']['enum'], ['clause_0'])
        categories = unit['properties']['selections']['items']['properties']['category']['enum']
        self.assertNotIn('request', categories)
        self.assertIn('constraint', categories)
        self.assertIn('quantity', categories)

    def test_empty_request_is_rejected_by_the_existing_canonical_guard(self):
        value = annotation(request=[], selections=[('quantity', 'clause_0')])
        fake = ScriptedModel('C', value)
        with patch('core.runtime.open_model_request', side_effect=fake):
            with self.assertRaises(verification.AnnotationValidationError) as rejected:
                execute_task('请把当前订单改成七杯', max_attempts=1)
        self.assertEqual(rejected.exception.code, 'missing_request')
        self.assertEqual(rejected.exception.unit_index, 0)

    def test_missing_request_key_is_a_schema_error(self):
        value = annotation(request=[], selections=[('quantity', 'clause_0')])
        del value['intents'][0]['request']
        fake = ScriptedModel('C', value)
        with patch('core.runtime.open_model_request', side_effect=fake):
            with self.assertRaisesRegex(TypeError, 'request'):
                execute_task('请把当前订单改成七杯', max_attempts=1)

    def test_request_must_belong_to_its_own_unit_evidence(self):
        value = annotation(request=['clause_1'])
        fake = ScriptedModel('C', value)
        with patch('core.runtime.open_model_request', side_effect=fake):
            with self.assertRaises(verification.AnnotationValidationError) as rejected:
                execute_task('请修改当前订单，稍后自取', max_attempts=1)
        self.assertEqual(rejected.exception.code, 'source_scope')
        self.assertEqual(rejected.exception.unit_index, 0)

    def test_explicit_request_with_empty_selections_is_valid(self):
        fake = ScriptedModel('C', annotation(request=['clause_0']))
        with patch('core.runtime.open_model_request', side_effect=fake):
            output = execute_task('请修改当前订单', max_attempts=1)
        self.assertEqual([keyword['category'] for keyword in output['intent']['keywords']], ['request'])
        self.assertEqual(output['result']['requested_change'], ['请修改当前订单'])
        self.assertEqual(output['result']['order_id'], [])

    def test_request_and_dedicated_label_can_explicitly_select_the_same_source(self):
        value = annotation(request=['clause_0'], selections=[('quantity', 'clause_0')])
        fake = ScriptedModel('C', value)
        with patch('core.runtime.open_model_request', side_effect=fake):
            output = execute_task('请把当前订单改成七杯', max_attempts=1)
        self.assertEqual({keyword['category'] for keyword in output['intent']['keywords']}, {'request', 'quantity'})
        self.assertTrue(all(keyword['text'] == '请把当前订单改成七杯' for keyword in output['intent']['keywords']))

    def test_empty_request_feedback_retry_preserves_decision_and_other_labels(self):
        common = {'clause_ids': ('clause_0', 'clause_1'), 'selections': [('quantity', 'clause_1')]}
        fake = ScriptedModel('C', annotation(request=[], **common), annotation(request=['clause_0'], **common))
        with patch('core.runtime.open_model_request', side_effect=fake):
            output = execute_task('请修改当前订单，改成七杯', max_attempts=2)
        self.assertEqual([payload['model'] for payload in fake.payloads], ['tev1:4b', 'qwen3.5:4b', 'qwen3.5:4b'])
        first = json.loads(fake.payloads[1]['messages'][1]['content'])
        retry = json.loads(fake.payloads[2]['messages'][1]['content'])
        self.assertEqual(first['decision'], retry['decision'])
        self.assertEqual(retry['validation_feedback']['code'], 'missing_request')
        self.assertEqual(retry['validation_feedback']['unit_id'], 'intent_0')
        self.assertEqual(output['result']['requested_change'], ['请修改当前订单'])
        self.assertEqual(output['state']['attempts'], 2)
        self.assertEqual([keyword['text'] for keyword in output['intent']['keywords'] if keyword['category'] == 'quantity'], ['改成七杯'])

    def test_selection_cannot_reintroduce_request(self):
        value = annotation(request=['clause_0'], selections=[('request', 'clause_0')])
        fake = ScriptedModel('C', value)
        with patch('core.runtime.open_model_request', side_effect=fake):
            with self.assertRaises(ValueError):
                execute_task('请修改当前订单', max_attempts=1)


if __name__ == '__main__':
    unittest.main()
