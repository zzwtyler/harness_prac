"""Protocol and ownership tests; semantic choices are hand-written HTTP fixtures.

These fixtures never call a model or claim to measure classification accuracy.
The public contract is Tev's single-letter decision followed, when needed, by
one Qwen structured annotation. No evaluation data is imported here.
"""
import inspect
import io
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from core import checkpoints, context, execution_config, intent_details, models, task_loader, task_registry, verification
from harness.main import execute_task as _execute_task


def execute_task(*args, **kwargs):
    """Keep R3 parsing/retry contracts as the explicit cascade-off control."""
    kwargs.setdefault('cascade_enabled', False)
    return _execute_task(*args, **kwargs)


ROOT = Path(__file__).resolve().parents[1]
SINGLE_ROUTES = (
    ('A', 'store_info', 'general'), ('B', 'menu_advice', 'recommendation'),
    ('C', 'order_support', 'modify'), ('D', 'group_order', 'new_order'),
    ('E', 'complaint', 'service'), ('F', 'membership_help', 'account'),
    ('G', 'campaign_brief', 'planning'), ('H', 'sales_analysis', 'summary'),
    ('I', 'other_request', 'unspecified'),
)


def unit(intent='order_support', subtype='modify', clause_ids=('clause_0',), selections=None):
    """Construct wire fixtures, independent of production annotation builders."""
    if selections is None:
        selections = [('request', clause_ids[0])]
    return {'intent': intent, 'subtype': subtype, 'clause_ids': list(clause_ids),
            'request': [clause_id for category, clause_id in selections if category == 'request'],
            'selections': [{'category': category, 'clause_id': clause_id}
                           for category, clause_id in selections if category != 'request']}


def structured(*units):
    return {'intents': list(units)}


class ScriptedModel:
    """Replace only external HTTP; leave parsing, retry, formatting and IO real."""
    def __init__(self, *answers):
        self.answers = iter(answers)
        self.payloads = []
        self.timeouts = []

    def __call__(self, req, timeout):
        payload = json.loads(req.data)
        self.payloads.append(payload)
        self.timeouts.append(timeout)
        answer = next(self.answers)
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, dict) and '_raw_response' in answer:
            value = answer['_raw_response']
        else:
            value = {'model': payload['model'], 'message': {'role': 'assistant',
                     'content': answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)},
                     'done': True, 'done_reason': 'stop', 'eval_count': 1, 'prompt_eval_count': 20}
            # Synthetic transport metadata keeps old semantic fixtures on their
            # intended primary lane; explicit raw responses test missing scores.
            if isinstance(answer, str) and answer.strip() in models.DECISIONS:
                option = answer.strip()
                value['logprobs'] = [{'token': option, 'bytes': [ord(option)], 'logprob': -0.01005033585350145}]
        return io.BytesIO(json.dumps(value, ensure_ascii=False).encode())


class DualModelPipelineTests(unittest.TestCase):
    def execute(self, source, *answers, **kwargs):
        fake = ScriptedModel(*answers)
        with patch('core.runtime.open_model_request', side_effect=fake):
            try:
                output = execute_task(source, max_attempts=kwargs.pop('max_attempts', 1), **kwargs)
            except (ValueError, TypeError, KeyError) as exc:
                self.fail(f'Dual-model success contract was rejected: {type(exc).__name__}: {exc}')
        return output, fake

    def assert_roles(self, fake, expected):
        self.assertEqual([payload['model'] for payload in fake.payloads], expected)

    def test_default_pipeline_uses_letter_decision_then_structured_detail(self):
        output, fake = self.execute('修改甲订单', 'C', structured(unit()))
        self.assert_roles(fake, ['tev1:4b', 'qwen3.5:4b'])
        self.assertNotIn('format', fake.payloads[0])
        self.assertIn('format', fake.payloads[1])
        self.assertEqual(output['intent']['decision']['mode'], 'infer')
        self.assertEqual(output['intent']['decision']['routing'], 'order_support')
        self.assertEqual(output['result']['requested_change'], ['修改甲订单'])

    def test_model_alias_changes_detail_role_only(self):
        _, fake = self.execute('修改甲订单', 'C', structured(unit()), model='custom-detail:4b')
        self.assert_roles(fake, ['tev1:4b', 'custom-detail:4b'])

    def test_explicit_decision_role_is_independent_and_timeout_reaches_both_calls(self):
        _, fake = self.execute('修改甲订单', 'C', structured(unit()),
                               model='detail-test:4b', decision_model='decision-test:4b', timeout_seconds=17)
        self.assert_roles(fake, ['decision-test:4b', 'detail-test:4b'])
        self.assertEqual(fake.timeouts, [17, 17])

    def test_all_single_route_letters_constrain_business_type(self):
        for letter, intent, subtype in SINGLE_ROUTES:
            with self.subTest(letter=letter):
                output, fake = self.execute('当前独立目标', letter, structured(unit(intent, subtype)))
                self.assertEqual(output['intent']['intent'], intent)
                self.assertEqual(output['intent']['decision']['routing'], intent)
                self.assertEqual(len(output['intent']['intents']), 1)
                self.assert_roles(fake, ['tev1:4b', 'qwen3.5:4b'])

    def test_ask_stops_before_detail_and_keeps_source(self):
        output, fake = self.execute('这个怎么办', 'M')
        self.assert_roles(fake, ['tev1:4b'])
        self.assertEqual(output['intent']['source_text'], '这个怎么办')
        self.assertEqual(output['intent']['input_kind'], 'unclear')
        self.assertEqual(output['intent']['intent'], 'no_intent')
        self.assertEqual(output['intent']['decision']['mode'], 'ask')
        self.assertEqual(output['intent']['intents'], [])
        self.assertEqual(output['context']['units'], [])
        self.assertEqual(output['context']['decision']['mode'], 'ask')
        self.assertEqual(output['context']['clarification_question'], '请说明你当前希望处理的目标。')

    def test_social_and_background_use_one_call_and_preserve_no_intent(self):
        for letter, kind in [('K', 'social'), ('L', 'background')]:
            with self.subTest(kind=kind):
                output, fake = self.execute('当前原文', letter)
                self.assert_roles(fake, ['tev1:4b'])
                self.assertEqual(output['intent']['input_kind'], kind)
                self.assertEqual(output['intent']['decision']['mode'], 'infer')
                self.assertEqual(output['intent']['intents'], [])

    def test_unobserved_fields_are_review_hints_and_do_not_create_ask(self):
        output, fake = self.execute('取消当前订单', 'C', structured(unit(subtype='cancel')))
        self.assert_roles(fake, ['tev1:4b', 'qwen3.5:4b'])
        self.assertEqual(output['intent']['decision']['mode'], 'infer')
        self.assertEqual(output['intent']['intents'][0]['not_observed'], ['order_id'])
        self.assertEqual(output['result']['order_id'], [])
        saved = output['context']['units'][0]
        self.assertEqual(saved['not_observed'], ['order_id'])
        self.assertTrue(saved['needs_review'])
        self.assertEqual(saved['verification_needed'], ['order_status', 'cancellation_policy'])

    def test_decision_object_from_python_mapping_is_frozen(self):
        stage = task_loader.load_task(ROOT / 'core/01_user_intent.py')
        fake = ScriptedModel('M')
        with patch('core.runtime.open_model_request', side_effect=fake):
            try:
                result = stage.normalize_task('这个怎么办', max_attempts=1)
            except (ValueError, TypeError) as exc:
                self.fail(f'Letter decision is not supported: {exc}')
        self.assertTrue(hasattr(result, 'decision'))
        with self.assertRaises(FrozenInstanceError):
            result.decision.mode = 'infer'

    def test_invalid_decision_letters_retry_only_decision_with_bounded_budget(self):
        for invalid in ['', 'AB', 'A because...', '```\nA\n```', 'Z', 'a']:
            with self.subTest(invalid=invalid):
                fake = ScriptedModel(invalid, invalid)
                with patch('core.runtime.open_model_request', side_effect=fake), self.assertRaises(ValueError):
                    execute_task('当前原文', max_attempts=2)
                self.assert_roles(fake, ['tev1:4b', 'tev1:4b'])

    def test_decision_length_truncation_is_rejected_even_with_legal_letter(self):
        raw = {'message': {'role': 'assistant', 'content': 'M'}, 'done': True, 'done_reason': 'length'}
        fake = ScriptedModel({'_raw_response': raw})
        with patch('core.runtime.open_model_request', side_effect=fake), self.assertRaises(ValueError):
            execute_task('当前原文', max_attempts=1)
        self.assert_roles(fake, ['tev1:4b'])

    def test_detail_retry_reuses_validated_decision(self):
        malformed = structured(unit(clause_ids=('clause_99',)))
        output, fake = self.execute('修改甲订单', 'C', malformed, structured(unit()), max_attempts=2)
        self.assert_roles(fake, ['tev1:4b', 'qwen3.5:4b', 'qwen3.5:4b'])
        self.assertEqual(output['state']['attempts'], 2)
        self.assertEqual(output['result']['requested_change'], ['修改甲订单'])

    def test_parameters_without_a_goal_annotation_are_rejected(self):
        value = structured(unit(clause_ids=('clause_0', 'clause_1'),
                                selections=[('quantity', 'clause_1')]))
        fake = ScriptedModel('C', value)
        with patch('core.runtime.open_model_request', side_effect=fake), self.assertRaisesRegex(ValueError, 'request'):
            execute_task('请调整当前订单，改成七杯', max_attempts=1)
        self.assert_roles(fake, ['tev1:4b', 'qwen3.5:4b'])

    def test_missing_goal_annotation_retries_with_safe_feedback_then_succeeds(self):
        missing = structured(unit(clause_ids=('clause_0', 'clause_1'),
                                  selections=[('quantity', 'clause_1')]))
        corrected = structured(unit(clause_ids=('clause_0', 'clause_1'),
                                    selections=[('request', 'clause_0'), ('quantity', 'clause_1')]))
        output, fake = self.execute('请调整当前订单，改成七杯', 'C', missing, corrected, max_attempts=2)
        self.assert_roles(fake, ['tev1:4b', 'qwen3.5:4b', 'qwen3.5:4b'])
        first = json.loads(fake.payloads[1]['messages'][1]['content'])
        retry = json.loads(fake.payloads[2]['messages'][1]['content'])
        self.assertNotIn('validation_feedback', first)
        self.assertEqual(retry['validation_feedback']['code'], 'missing_request')
        self.assertEqual(retry['validation_feedback']['unit_id'], 'intent_0')
        self.assertEqual(retry['validation_feedback']['previous_attempt'], 1)
        self.assertEqual(first['decision'], retry['decision'])
        self.assertEqual(first['clauses'], retry['clauses'])
        self.assertEqual(output['state']['attempts'], 2)
        self.assertEqual(output['result']['requested_change'], ['请调整当前订单'])
        goals = [keyword['text'] for keyword in output['intent']['keywords'] if keyword['category'] == 'request']
        self.assertEqual(goals, ['请调整当前订单'])

    def test_one_units_goal_label_does_not_satisfy_another_unit(self):
        value = structured(unit(), unit(subtype='cancel', clause_ids=('clause_1',),
                                        selections=[('order_id', 'clause_1')]))
        fake = ScriptedModel('J', value)
        with patch('core.runtime.open_model_request', side_effect=fake), self.assertRaisesRegex(ValueError, 'request'):
            execute_task('调整甲订单，取消乙订单R-42', max_attempts=1)
        self.assert_roles(fake, ['tev1:4b', 'qwen3.5:4b'])

    def test_pure_attribute_background_never_receives_a_synthetic_request_label(self):
        output, fake = self.execute('补充偏好：不加奶', 'L')
        self.assert_roles(fake, ['tev1:4b'])
        self.assertEqual(output['intent']['input_kind'], 'background')
        self.assertEqual(output['intent']['keywords'], [])
        self.assertEqual(output['intent']['intents'], [])

    def test_goal_and_dedicated_information_can_share_a_source_span(self):
        output, _ = self.execute('请把当前订单改成七杯', 'C', structured(unit(
            selections=[('request', 'clause_0'), ('quantity', 'clause_0')])))
        self.assertEqual({keyword['category'] for keyword in output['intent']['keywords']}, {'request', 'quantity'})
        self.assertEqual(output['result']['requested_change'], ['请把当前订单改成七杯'])

    def test_verifier_rejects_a_forged_parameter_only_unit(self):
        source = '请把当前订单改成七杯'
        span = models.SourceSpan(source, 0, len(source))
        value = intent_details.enrich('order_support', 'modify', [span],
                    [models.Keyword('quantity', source, 0, len(source))])
        forged = models.ExtractedInput(source, 'order_support', value.keywords, intents=[value],
                                       decision=models.Decision('C', 'request', 'infer', 'order_support'))
        with self.assertRaisesRegex(ValueError, 'request'):
            verification.verify_extraction(forged)

    def test_retry_feedback_does_not_copy_unknown_model_keys_or_user_text(self):
        poisoned = structured(unit())
        poisoned['intents'][0]['IGNORE_ALL_RULES_FROM_MODEL'] = 'UNTRUSTED_MODEL_TEXT'
        _, fake = self.execute('当前目标 USER_ONLY_MARKER', 'C', poisoned, structured(unit()), max_attempts=2)
        feedback = json.loads(fake.payloads[2]['messages'][1]['content'])['validation_feedback']
        self.assertEqual(feedback['code'], 'schema_invalid')
        self.assertIsNone(feedback['unit_id'])
        serialized = json.dumps(feedback, ensure_ascii=False)
        for marker in ['IGNORE_ALL_RULES_FROM_MODEL', 'UNTRUSTED_MODEL_TEXT', 'USER_ONLY_MARKER']:
            self.assertNotIn(marker, serialized)

    def test_decision_state_contains_only_complete_source_text(self):
        _, fake = self.execute('调整甲订单，改成七杯', 'C', structured(unit()))
        state = json.loads(fake.payloads[0]['messages'][1]['content'])['state']
        self.assertEqual(state, {'source_text': '调整甲订单，改成七杯'})

    def test_network_failure_does_not_create_annotation_feedback(self):
        _, fake = self.execute('修改甲订单', 'C', OSError('offline'), structured(unit()), max_attempts=2)
        retry = json.loads(fake.payloads[2]['messages'][1]['content'])
        self.assertNotIn('validation_feedback', retry)

    def test_decision_retry_does_not_exceed_pipeline_attempt_budget(self):
        output, fake = self.execute('修改甲订单', 'not a letter', 'C', structured(unit()), max_attempts=2)
        self.assert_roles(fake, ['tev1:4b', 'tev1:4b', 'qwen3.5:4b'])
        self.assertEqual(output['state']['attempts'], 2)

    def test_single_business_annotation_cannot_change_decision_route(self):
        fake = ScriptedModel('C', structured(unit('menu_advice', 'recommendation')))
        with patch('core.runtime.open_model_request', side_effect=fake), self.assertRaises(ValueError):
            execute_task('当前目标', max_attempts=1)
        self.assert_roles(fake, ['tev1:4b', 'qwen3.5:4b'])

    def test_multi_preserves_repeated_business_units_and_other(self):
        source = '修改甲订单，取消乙订单，修理设备'
        value = structured(unit(), unit(subtype='cancel', clause_ids=('clause_1',)),
                           unit('other_request', 'unspecified', ('clause_2',)))
        output, _ = self.execute(source, 'J', value)
        units = output['intent']['intents']
        self.assertEqual(output['intent']['intent'], 'multi_intent')
        self.assertEqual([u['intent'] for u in units], ['order_support', 'order_support', 'other_request'])
        self.assertEqual([u['subtype'] for u in units], ['modify', 'cancel', 'unspecified'])
        self.assertEqual([u['evidence'][0]['text'] for u in units], ['修改甲订单', '取消乙订单', '修理设备'])
        self.assertEqual(output['result']['intents'], units)
        scoped = output['context']['units']
        self.assertEqual([u['id'] for u in scoped], ['intent_0', 'intent_1', 'intent_2'])
        self.assertEqual([u['source_spans'][0]['text'] for u in scoped], ['修改甲订单', '取消乙订单', '修理设备'])

    def test_multi_requires_at_least_two_independent_units(self):
        fake = ScriptedModel('J', structured(unit()))
        with patch('core.runtime.open_model_request', side_effect=fake), self.assertRaises(ValueError):
            execute_task('当前目标', max_attempts=1)
        self.assert_roles(fake, ['tev1:4b', 'qwen3.5:4b'])

    def test_source_scope_and_business_slots_are_checked_without_lexical_filter(self):
        cases = [
            unit(selections=[('request', 'clause_1')]),
            unit(clause_ids=('clause_99',)),
            unit(clause_ids=(True,)),
            unit(subtype='planning'),
            unit(selections=[('offer', 'clause_0')]),
        ]
        for malformed in cases:
            with self.subTest(malformed=malformed):
                fake = ScriptedModel('C', structured(malformed))
                with patch('core.runtime.open_model_request', side_effect=fake), self.assertRaises(ValueError):
                    execute_task('修改甲订单，修理设备', max_attempts=1)
                self.assert_roles(fake, ['tev1:4b', 'qwen3.5:4b'])

    def test_shared_whole_source_span_can_belong_to_two_units(self):
        value = structured(unit(), unit('other_request', 'unspecified'))
        output, _ = self.execute('同时处理甲乙目标', 'J', value)
        first, second = output['intent']['intents']
        self.assertEqual(first['evidence'], second['evidence'])
        self.assertEqual(first['evidence'][0]['text'], '同时处理甲乙目标')

    def test_negation_and_correction_are_copied_as_whole_source_spans(self):
        source = '请安排团订，不要配送，要自取；不是20杯，是12杯'
        value = structured(unit('group_order', 'new_order',
                    ('clause_0', 'clause_1', 'clause_2', 'clause_3', 'clause_4'),
                    [('request', 'clause_0'), ('pickup_or_delivery', 'clause_1'), ('pickup_or_delivery', 'clause_2'),
                     ('quantity', 'clause_3'), ('quantity', 'clause_4')]))
        output, _ = self.execute(source, 'D', value)
        self.assertEqual(output['result']['pickup_or_delivery'], ['不要配送', '要自取'])
        self.assertEqual(output['result']['quantity'], ['不是20杯', '是12杯'])
        for keyword in output['intent']['keywords']:
            self.assertEqual(source[keyword['start']:keyword['end']], keyword['text'])

    def test_single_business_formatter_rejects_multi_or_other_business_input(self):
        source = '修改甲订单，修理设备'
        spans = [models.SourceSpan(**span) for span in context.source_clauses(source)]
        units = [intent_details.enrich(intent, subtype, [span],
                         [models.Keyword('request', span.text, span.start, span.end)])
                 for intent, subtype, span in [('order_support', 'modify', spans[0]),
                                              ('other_request', 'unspecified', spans[1])]]
        aggregate = models.ExtractedInput(source, 'multi_intent', intent_details.merge_keywords(units), intents=units)
        other = models.ExtractedInput(source, 'other_request', units[1].keywords, intents=[units[1]])
        stage = task_registry.TaskRegistry().get('order_support').module
        for extracted in [aggregate, other]:
            with self.subTest(intent=extracted.intent), self.assertRaises(ValueError):
                stage.from_extraction(extracted)

    def test_context_manager_requires_a_valid_fixed_decision(self):
        source = '修改甲订单'
        span = models.SourceSpan(source, 0, len(source))
        value = intent_details.enrich('order_support', 'modify', [span],
                    [models.Keyword('request', source, 0, len(source))])
        legacy = models.ExtractedInput(source, 'order_support', value.keywords, intents=[value])
        with self.assertRaises(ValueError):
            context.build_intent_context(legacy)

    def test_sampling_settings_are_explicit_for_each_model_role(self):
        _, fake = self.execute('修改甲订单', 'C', structured(unit()), think=True)
        for payload, temperature, budget in zip(fake.payloads, [0, 0.2], [8, 4096]):
            self.assertEqual(payload['options'], {
                'temperature': temperature, 'top_k': 20, 'top_p': 0.95, 'min_p': 0, 'seed': 0,
                'presence_penalty': 0, 'frequency_penalty': 0, 'repeat_penalty': 1,
                'num_ctx': 32768, 'num_predict': budget})
        self.assertFalse(fake.payloads[0]['think'])
        self.assertTrue(fake.payloads[1]['think'])

    def test_direct_business_entrypoints_keep_model_roles(self):
        for letter, intent, subtype in SINGLE_ROUTES:
            with self.subTest(intent=intent):
                stage = task_registry.TaskRegistry().get(intent).module
                fake = ScriptedModel(letter, structured(unit(intent, subtype)))
                with patch('core.runtime.open_model_request', side_effect=fake):
                    try:
                        result = stage.analyze_task('当前独立目标', model='detail-direct:4b',
                                                    decision_model='decision-direct:4b')
                    except (ValueError, TypeError) as exc:
                        self.fail(f'Direct stage rejected role settings: {exc}')
                self.assert_roles(fake, ['decision-direct:4b', 'detail-direct:4b'])
                self.assertEqual(result.intents[0].intent, intent)

    def test_runtime_stage_entrypoint_keeps_both_roles(self):
        from core import runtime, stage
        selected = stage.StageRegistry(ROOT / 'web/stages').get('order_support')
        fake = ScriptedModel('C', structured(unit()))
        with patch('core.runtime.open_model_request', side_effect=fake):
            try:
                raw, result = runtime.run_stage(selected, '修改甲订单', model='detail-stage:4b',
                                                decision_model='decision-stage:4b', think=False)
            except (ValueError, TypeError) as exc:
                self.fail(f'Runtime stage rejected role settings: {exc}')
        self.assert_roles(fake, ['decision-stage:4b', 'detail-stage:4b'])
        self.assertEqual(result.requested_change, ['修改甲订单'])
        self.assertNotIn('thinking', raw['message'])

    def test_checkpoint_settings_bind_each_model_without_changing_old_positions(self):
        parameters = inspect.signature(execution_config.ExtractionTask).parameters
        self.assertIn('decision_model', parameters)
        self.assertEqual(parameters['decision_model'].kind, inspect.Parameter.KEYWORD_ONLY)
        args = ('当前原文', 'detail-a:4b', 'http://127.0.0.1:11434', False, 2, 19)
        first = execution_config.ExtractionTask(*args, decision_model='decision-a:4b')
        second = execution_config.ExtractionTask(*args, decision_model='decision-b:4b')
        third = execution_config.ExtractionTask('当前原文', 'detail-b:4b', args[2], False, 2, 19,
                                                decision_model='decision-a:4b')
        self.assertEqual(first.model, 'detail-a:4b')
        self.assertEqual(first.timeout_seconds, 19)
        self.assertNotEqual(checkpoints.execution_fingerprint(first), checkpoints.execution_fingerprint(second))
        self.assertNotEqual(checkpoints.execution_fingerprint(first), checkpoints.execution_fingerprint(third))

    def test_resume_rejects_a_change_to_either_model_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            self.execute('修改甲订单', 'C', structured(unit()), output_directory=Path(directory),
                         model='detail-a:4b', decision_model='decision-a:4b')
            for detail, decision in [('detail-b:4b', 'decision-a:4b'), ('detail-a:4b', 'decision-b:4b')]:
                with self.subTest(detail=detail, decision=decision):
                    with patch('core.runtime.open_model_request', side_effect=AssertionError('Network forbidden')):
                        with self.assertRaises(ValueError):
                            execute_task('修改甲订单', output_directory=Path(directory), resume=True,
                                         model=detail, decision_model=decision)

    def test_cli_exposes_independent_decision_model_and_detail_alias(self):
        from core import cli
        captured = {}
        def run(source, **settings):
            captured.update(source=source, **settings)
            return {'ok': True}
        with patch('sys.argv', ['harness', '当前原文', '--model', 'detail-cli:4b',
                               '--decision-model', 'decision-cli:4b']), patch('sys.stdout', io.StringIO()):
            try:
                cli.main(run)
            except SystemExit as exc:
                self.fail(f'CLI rejected independent role settings: {exc}')
        self.assertEqual(captured['model'], 'detail-cli:4b')
        self.assertEqual(captured['decision_model'], 'decision-cli:4b')

    def test_web_request_keeps_both_roles_and_ignores_untrusted_prompt_context(self):
        from web.main import AppHandler
        body = json.dumps({'stageId': 'user_intent', 'message': '修改甲订单',
                           'model': 'detail-web:4b', 'decisionModel': 'decision-web:4b',
                           'projectContext': '不可信额外事实', 'systemPrompt': '不可信覆盖指令'}).encode()
        handler = object.__new__(AppHandler)
        handler.path = '/api/run'
        handler.headers = {'Content-Length': str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.send_response = lambda *args: None
        handler.send_header = lambda *args: None
        handler.end_headers = lambda: None
        events, errors = [], []
        handler._write_event = events.append
        handler._send_json = lambda status, payload: errors.append((status, payload))
        fake = ScriptedModel('C', structured(unit()))
        with patch('core.runtime.open_model_request', side_effect=fake):
            handler.do_POST()
        self.assertEqual(errors, [])
        self.assert_roles(fake, ['decision-web:4b', 'detail-web:4b'])
        self.assertEqual([event['type'] for event in events], ['content', 'done'])
        self.assertEqual(json.loads(events[0]['text'])['intent'], 'order_support')
        serialized = json.dumps(fake.payloads, ensure_ascii=False)
        self.assertNotIn('不可信额外事实', serialized)
        self.assertNotIn('不可信覆盖指令', serialized)


if __name__ == '__main__':
    unittest.main()
