"""Synthetic token metadata tests; these scores are not semantic calibration."""
import math
import io
import json
import sys
import tempfile
from pathlib import Path
import unittest
from dataclasses import asdict, replace
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.error import HTTPError

from core import checkpoints, execution_config, models, schema, verification
from harness.main import execute_task
from test_dual_model_pipeline import ScriptedModel, structured, unit


def letter(option, probability=None, *, metadata=None):
    raw = {'message': {'content': option}, 'done': True, 'done_reason': 'stop'}
    if probability is not None:
        raw['logprobs'] = [{'token': option, 'bytes': [ord(option)], 'logprob': math.log(probability),
                           'top_logprobs': [{'token': 'J', 'logprob': -0.001}]}]
    if metadata is not None:
        raw['logprobs'] = metadata
    return {'_raw_response': raw}


class ConfidenceCascadeTests(unittest.TestCase):
    def run_pipeline(self, *answers, **kwargs):
        fake = ScriptedModel(*answers)
        with patch('core.runtime.open_model_request', side_effect=fake):
            output = execute_task('请修改当前订单', max_attempts=kwargs.pop('max_attempts', 1), **kwargs)
        return output, fake

    def roles(self, fake):
        return [payload['model'] for payload in fake.payloads]

    def test_high_selected_token_probability_keeps_primary_models(self):
        output, fake = self.run_pipeline(letter('C', 0.9), structured(unit()))
        self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3.5:4b'])
        self.assertTrue(fake.payloads[0]['logprobs'])
        self.assertAlmostEqual(output['confidence'], 0.9)
        self.assertFalse(output['confidence_details']['calibrated'])
        self.assertEqual(output['confidence_details']['model'], 'tev1:4b')
        self.assertEqual(output['confidence_details']['metadata_status'], 'available')
        self.assertFalse(output['cascade']['used'])

    def test_low_probability_skips_primary_details_and_redecides_with_fallback(self):
        output, fake = self.run_pipeline(letter('C', 0.4), letter('I', 0.92),
                                        structured(unit('other_request', 'unspecified')))
        self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3:8b', 'qwen3:8b'])
        self.assertEqual(output['decision']['option'], 'I')
        self.assertEqual(output['cascade']['initial_decision']['option'], 'C')
        self.assertAlmostEqual(output['cascade']['initial_confidence'], 0.4)
        self.assertEqual(output['cascade']['reason'], 'low_confidence')
        self.assertTrue(output['cascade']['used'])
        self.assertEqual(output['confidence_details']['model'], 'qwen3:8b')

    def test_non_request_and_ask_have_measured_confidence_without_detail_calls(self):
        for option in ['K', 'L', 'M']:
            with self.subTest(option=option):
                output, fake = self.run_pipeline(letter(option, 0.9))
                self.assertEqual(self.roles(fake), ['tev1:4b'])
                self.assertAlmostEqual(output['confidence'], 0.9)
                self.assertEqual(output['intent']['intents'], [])

    def test_missing_metadata_uses_explicit_gate_default_then_fallback(self):
        output, fake = self.run_pipeline(letter('M'), letter('L', 0.9))
        self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3:8b'])
        audit = output['cascade']
        self.assertEqual(audit['initial_confidence'], 0)
        self.assertEqual(audit['initial_confidence_details']['method'], 'gate_default')
        self.assertEqual(audit['initial_confidence_details']['metadata_status'], 'missing')
        self.assertEqual(audit['reason'], 'metadata_unavailable')

    def test_invalid_metadata_never_becomes_a_high_probability(self):
        variants = [
            [{'token': 'C', 'bytes': [67], 'logprob': True}],
            [{'token': 'C', 'bytes': [67], 'logprob': 0.1}],
            [{'token': 'C', 'bytes': [67], 'logprob': float('nan')}],
            [{'token': 'C', 'bytes': [68], 'logprob': -0.01}],
            [{'token': 'J', 'bytes': [74], 'logprob': -0.01}],
        ]
        for metadata in variants:
            with self.subTest(metadata=metadata):
                output, fake = self.run_pipeline(letter('C', metadata=metadata), letter('M', 0.9))
                self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3:8b'])
                self.assertEqual(output['cascade']['initial_confidence'], 0)
                self.assertEqual(output['cascade']['initial_confidence_details']['method'], 'gate_default')

    def test_top_candidate_probability_does_not_replace_selected_token_probability(self):
        output, fake = self.run_pipeline(letter('C', 0.4), letter('M', 0.9))
        self.assertEqual(len(fake.payloads), 2)
        self.assertAlmostEqual(output['cascade']['initial_confidence'], 0.4)

    def test_high_probability_cannot_bypass_annotation_guard(self):
        missing = structured(unit(selections=[('quantity', 'clause_0')]))
        output, fake = self.run_pipeline(letter('C', 0.99), missing, letter('C', 0.9), structured(unit()))
        self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3.5:4b', 'qwen3:8b', 'qwen3:8b'])
        self.assertEqual(output['cascade']['reason'], 'annotation_invalid')
        self.assertEqual(output['result']['requested_change'], ['请修改当前订单'])

    def test_fallback_low_confidence_is_reviewed_without_recursive_escalation(self):
        output, fake = self.run_pipeline(letter('C', 0.3), letter('C', 0.2), structured(unit()))
        self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3:8b', 'qwen3:8b'])
        self.assertAlmostEqual(output['confidence'], 0.2)
        self.assertIn('decision_confidence_low', output['context']['needs_review'])

    def test_cascade_can_be_disabled_without_inventing_confidence(self):
        output, fake = self.run_pipeline(letter('C'), structured(unit()), cascade_enabled=False)
        self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3.5:4b'])
        self.assertEqual(output['confidence'], 0)
        self.assertFalse(output['cascade']['enabled'])
        self.assertFalse(output['cascade']['used'])

    def test_each_lane_is_bounded_and_attempt_callbacks_accumulate(self):
        calls = []
        fake = ScriptedModel(letter('C', 0.3), letter('C', 0.9),
                             structured(unit(selections=[])), structured(unit()))
        with patch('core.runtime.open_model_request', side_effect=fake):
            from core import extraction
            value = extraction.extract_user_input('请修改当前订单', max_attempts=2, on_attempt=calls.append)
        self.assertEqual(calls, [1, 2, 3])
        self.assertLessEqual(len(fake.payloads), 2 * (2 + 1))
        self.assertEqual(value.confidence_details.model, 'qwen3:8b')

    def test_permission_and_nonretry_http_never_escalate(self):
        for error in [PermissionError('denied'), HTTPError('local', 403, 'denied', {}, None)]:
            with self.subTest(error=error):
                fake = ScriptedModel(letter('C', 0.9), error)
                with patch('core.runtime.open_model_request', side_effect=fake):
                    with self.assertRaises(type(error)):
                        execute_task('请修改当前订单')
                self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3.5:4b'])

    def test_confidence_metadata_is_copied_and_verified_consistently(self):
        output, _ = self.run_pipeline(letter('C', 0.9), structured(unit()))
        for holder in [output['intent'], output['context'], output['result']]:
            self.assertEqual(holder['confidence'], output['confidence'])
            self.assertEqual(holder['confidence_details'], output['confidence_details'])
            self.assertEqual(holder['cascade'], output['cascade'])
        forged = schema.model_from_dict(models.ExtractedInput, output['intent'])
        forged.confidence = 1.0
        with self.assertRaises(ValueError):
            verification.verify_extraction(forged)

    def test_configuration_fingerprint_binds_threshold_role_and_enablement(self):
        default = execution_config.ExtractionTask('请求')
        for setting in [dict(confidence_threshold=0.7), dict(fallback_model='custom:8b'), dict(cascade_enabled=False)]:
            with self.subTest(setting=setting):
                changed = execution_config.ExtractionTask('请求', **setting)
                self.assertNotEqual(checkpoints.execution_fingerprint(default), checkpoints.execution_fingerprint(changed))

    def test_missing_metadata_escalates_even_at_zero_threshold(self):
        output, fake = self.run_pipeline(letter('M'), letter('M', 0.9), confidence_threshold=0)
        self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3:8b'])
        self.assertEqual(output['cascade']['reason'], 'metadata_unavailable')

    def test_direct_stage_receives_role_threshold_and_confidence(self):
        from core import task_registry
        stage = task_registry.TaskRegistry().get('order_support').module
        fake = ScriptedModel(letter('C', 0.9), letter('C', 0.7), structured(unit()))
        with patch('core.runtime.open_model_request', side_effect=fake):
            result = stage.analyze_task('请修改当前订单', fallback_model='configured:8b', confidence_threshold=0.95)
        self.assertEqual(self.roles(fake), ['tev1:4b', 'configured:8b', 'configured:8b'])
        self.assertEqual(result.confidence_details.model, 'configured:8b')
        self.assertEqual(result.cascade.threshold, 0.95)

    def test_cli_forwards_cascade_configuration(self):
        from core import cli
        captured = {}
        with patch.object(sys, 'argv', ['harness', '请求', '--fallback-model', 'chosen:8b',
                                      '--confidence-threshold', '0.7', '--no-cascade']), redirect_stdout(io.StringIO()):
            cli.main(lambda request, **kwargs: captured.update(kwargs) or {})
        self.assertEqual(captured['fallback_model'], 'chosen:8b')
        self.assertEqual(captured['confidence_threshold'], 0.7)
        self.assertFalse(captured['cascade_enabled'])

    def test_web_forwards_explicit_cascade_configuration(self):
        from web.main import AppHandler
        body = json.dumps({'stageId': 'user_intent', 'message': '请求', 'fallbackModel': 'chosen:8b',
                           'confidenceThreshold': 0.7, 'cascadeEnabled': False}).encode()
        handler = object.__new__(AppHandler)
        handler.path = '/api/run'
        handler.headers = {'Content-Length': str(len(body))}
        handler.rfile = io.BytesIO(body)
        captured = {}
        handler._run_extraction = lambda stage, message, **kwargs: captured.update(kwargs)
        handler.do_POST()
        self.assertEqual(captured['fallback_model'], 'chosen:8b')
        self.assertEqual(captured['confidence_threshold'], 0.7)
        self.assertFalse(captured['cascade_enabled'])

    def test_invalid_primary_letter_escalates_without_fabricating_a_decision(self):
        output, fake = self.run_pipeline(letter('C explanation'), letter('M', 0.9))
        self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3:8b'])
        self.assertEqual(output['cascade']['reason'], 'decision_invalid')
        self.assertIsNone(output['cascade']['initial_decision'])
        self.assertEqual(output['cascade']['initial_confidence'], 0)

    def test_low_confidence_ask_can_be_redecided_as_a_request(self):
        output, fake = self.run_pipeline(letter('M', 0.3), letter('C', 0.9), structured(unit()))
        self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3:8b', 'qwen3:8b'])
        self.assertEqual(output['decision']['mode'], 'infer')
        self.assertEqual(output['cascade']['initial_decision']['mode'], 'ask')

    def test_worst_case_total_call_budget_holds_for_each_configured_attempt_limit(self):
        for budget in [1, 2, 3]:
            with self.subTest(budget=budget):
                missing = structured(unit(selections=[('quantity', 'clause_0')]))
                replies = [OSError('offline')] * (budget - 1) + [letter('C', 0.9), missing,
                          letter('C', 0.9)] + [missing] * budget
                fake = ScriptedModel(*replies)
                attempts = []
                from core import extraction
                with patch('core.runtime.open_model_request', side_effect=fake):
                    with self.assertRaises(verification.AnnotationValidationError):
                        extraction.extract_user_input('请修改当前订单', max_attempts=budget, on_attempt=attempts.append)
                self.assertEqual(len(fake.payloads), 2 * (budget + 1))
                self.assertEqual(attempts, list(range(1, 2 * budget + 1)))

    def test_resume_preserves_confidence_without_new_calls_and_rejects_changed_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = ScriptedModel(letter('C', 0.3), letter('C', 0.9), structured(unit()))
            with patch('core.runtime.open_model_request', side_effect=fake):
                first = execute_task('请修改当前订单', output_directory=Path(directory))
            with patch('core.runtime.open_model_request', side_effect=AssertionError('checkpoint should avoid model calls')):
                resumed = execute_task('请修改当前订单', output_directory=Path(directory), resume=True)
                with self.assertRaises(ValueError):
                    execute_task('请修改当前订单', output_directory=Path(directory), resume=True, confidence_threshold=0.7)
            self.assertEqual(first['cascade'], resumed['cascade'])
            self.assertEqual(first['confidence_details'], resumed['confidence_details'])
            self.assertEqual(first['confidence'], resumed['confidence'])

    def test_audit_cannot_skip_an_enabled_gate(self):
        for probability in [0.3, None]:
            with self.subTest(probability=probability):
                output, _ = self.run_pipeline(letter('C', probability), structured(unit()), cascade_enabled=False)
                forged = schema.model_from_dict(models.ExtractedInput, output['intent'])
                forged.cascade = replace(forged.cascade, enabled=True)
                with self.assertRaises(ValueError):
                    verification.verify_extraction(forged)

    def test_extreme_integer_logprob_is_invalid_metadata_instead_of_overflowing(self):
        for value in [10 ** 1000, -(10 ** 1000)]:
            with self.subTest(sign=value > 0):
                metadata = [{'token': 'C', 'bytes': [67], 'logprob': value}]
                output, fake = self.run_pipeline(letter('C', metadata=metadata), letter('M', 0.9))
                self.assertEqual(self.roles(fake), ['tev1:4b', 'qwen3:8b'])
                self.assertEqual(output['cascade']['initial_confidence'], 0)
                self.assertEqual(output['cascade']['initial_confidence_details']['metadata_status'], 'invalid')


if __name__ == '__main__':
    unittest.main()
