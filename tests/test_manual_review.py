"""Handoff policy tests; frozen payload hashes use only synthetic HTTP replies."""
import hashlib
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from core import context, intent_details, models, schema, task_registry, verification
from harness.main import execute_task
from test_confidence_cascade import letter
from test_dual_model_pipeline import ScriptedModel, structured, unit


TEV = 'd78390d3c4da4c00bea563f2f166be32d9863e543250525ffff3e19d63dab7fd'
PRIMARY = 'af1caecaaee14f952f85d69c76f896c176fb77774af839cb41c319a3de9107ae'
FALLBACK_DECISION = '44fa3dc34c7b432dd9e99ed12e56d4733358fd17b1959913699f171d6d5a6f32'
FALLBACK_DETAIL = '25f7a9e6b5384fe3a605da4d90dfa2fce7f3da8f963085df1baba07d0899fbdf'
FALLBACK_RETRY = 'c63eef745c543bf2987295c3362a15948811e43c16bc4cc36e3f59ecd6b4d975'


class ManualReviewTests(unittest.TestCase):
    def run_pipeline(self, *answers, **kwargs):
        fake = ScriptedModel(*answers)
        captured = []
        def upstream(req, timeout):
            captured.append(hashlib.sha256(req.data).hexdigest())
            return fake(req, timeout)
        with patch('core.runtime.open_model_request', side_effect=upstream):
            output = execute_task('请修改当前订单', max_attempts=kwargs.pop('max_attempts', 1), **kwargs)
        return output, captured

    def assert_policy_copies(self, output, required, reasons):
        for holder in [output, output['intent'], output['context'], output['result']]:
            self.assertIs(holder['manual_review_required'], required)
            self.assertEqual(holder['review_reasons'], reasons)

    def test_high_confidence_is_not_forced_to_human_by_generic_diagnostics(self):
        output, _ = self.run_pipeline(letter('C', 0.9), structured(unit()))
        self.assert_policy_copies(output, False, [])
        saved = output['context']['units'][0]
        self.assertIn('semantic_verification_not_performed', saved['needs_review'])
        self.assertIn('not_observed_requires_review', saved['needs_review'])
        self.assertIn('business_verification_pending', saved['needs_review'])
        self.assertEqual(output['context']['status'], 'ready')

    def test_final_fallback_low_confidence_requires_human(self):
        output, _ = self.run_pipeline(letter('C', 0.3), letter('C', 0.2), structured(unit()))
        self.assert_policy_copies(output, True, ['decision_confidence_low'])
        self.assertEqual(output['context']['status'], 'needs_human_review')
        self.assertEqual(output['decision']['mode'], 'infer')

    def test_initial_low_confidence_does_not_force_human_after_high_fallback(self):
        output, _ = self.run_pipeline(letter('C', 0.3), letter('C', 0.9), structured(unit()))
        self.assert_policy_copies(output, False, [])
        self.assertTrue(output['cascade']['used'])

    def test_disabled_cascade_uses_final_score_and_actual_threshold(self):
        output, _ = self.run_pipeline(letter('C', 0.7), structured(unit()),
                                      confidence_threshold=0.75, cascade_enabled=False)
        self.assert_policy_copies(output, True, ['decision_confidence_low'])

    def test_missing_metadata_requires_human_even_at_zero_threshold(self):
        output, _ = self.run_pipeline(letter('M'), letter('M'), confidence_threshold=0)
        self.assert_policy_copies(output, True, ['decision_confidence_metadata_unavailable'])
        self.assertEqual(output['context']['status'], 'needs_human_review')
        self.assertEqual(output['decision']['mode'], 'ask')
        self.assertEqual(output['context']['clarification_question'], '请说明你当前希望处理的目标。')

    def test_high_ask_and_non_request_keep_their_existing_states(self):
        for option, status in [('M', 'needs_clarification'), ('L', 'no_intent'), ('K', 'no_intent')]:
            with self.subTest(option=option):
                output, _ = self.run_pipeline(letter(option, 0.9))
                self.assert_policy_copies(output, False, [])
                self.assertEqual(output['context']['status'], status)

    def test_score_at_threshold_is_not_low(self):
        output, _ = self.run_pipeline(letter('C', 0.8), structured(unit()))
        self.assert_policy_copies(output, False, [])

    def test_legacy_extraction_without_metadata_is_conservatively_reviewed(self):
        source = '请修改当前订单'
        span = models.SourceSpan(source, 0, len(source))
        selected = intent_details.enrich('order_support', 'modify', [span],
                    [models.Keyword('request', source, 0, len(source))])
        extracted = models.ExtractedInput(source, 'order_support', selected.keywords, intents=[selected],
                                          decision=models.DECISIONS['C'])
        verification.verify_extraction(extracted)
        self.assertTrue(extracted.manual_review_required)
        self.assertEqual(extracted.review_reasons, ['decision_confidence_metadata_unavailable'])
        self.assertEqual(context.build_intent_context(extracted)['status'], 'needs_human_review')

    def test_manual_flag_and_reasons_cannot_be_forged_or_used_as_source_facts(self):
        output, _ = self.run_pipeline(letter('C', 0.3), structured(unit()), cascade_enabled=False)
        for required, reasons in [(False, ['decision_confidence_low']), (True, []),
                                  (True, ['semantic_verification_not_performed'])]:
            with self.subTest(required=required, reasons=reasons):
                data = dict(output['intent'], manual_review_required=required, review_reasons=reasons)
                with self.assertRaises(ValueError):
                    verification.verify_extraction(schema.model_from_dict(models.ExtractedInput, data))
        extracted = schema.model_from_dict(models.ExtractedInput, output['intent'])
        definition = task_registry.TaskRegistry().get('order_support')
        result = definition.module.from_extraction(extracted)
        verification.verify_result(extracted, result, definition)
        result.manual_review_required = False
        with self.assertRaises(ValueError):
            verification.verify_result(extracted, result, definition)

    def test_resume_preserves_handoff_without_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            first, _ = self.run_pipeline(letter('C', 0.3), letter('C', 0.2), structured(unit()),
                                         output_directory=Path(directory))
            with patch('core.runtime.open_model_request', side_effect=AssertionError('no model calls during resume')):
                resumed = execute_task('请修改当前订单', output_directory=Path(directory), resume=True, max_attempts=1)
            self.assert_policy_copies(resumed, True, ['decision_confidence_low'])
            self.assertEqual(first['result'], resumed['result'])

    def test_every_model_request_body_matches_the_prechange_bytes(self):
        missing = structured(unit(selections=[('quantity', 'clause_0')]))
        scenarios = [
            ({}, [letter('C', .9), structured(unit())], [TEV, PRIMARY]),
            ({}, [letter('C', .3), letter('C', .9), structured(unit())], [TEV, FALLBACK_DECISION, FALLBACK_DETAIL]),
            ({}, [letter('C', .3), letter('C', .2), structured(unit())], [TEV, FALLBACK_DECISION, FALLBACK_DETAIL]),
            ({}, [letter('M', .9)], [TEV]), ({}, [letter('L', .9)], [TEV]),
            ({'cascade_enabled': False}, [letter('C', .3), structured(unit())], [TEV, PRIMARY]),
            ({'cascade_enabled': False}, [letter('C'), structured(unit())], [TEV, PRIMARY]),
            ({'confidence_threshold': 0}, [letter('M'), letter('M', .9)], [TEV, FALLBACK_DECISION]),
            ({}, [letter('C', .8), structured(unit())], [TEV, PRIMARY]),
            ({'max_attempts': 2}, [letter('C', .9), missing, letter('C', .9), missing, structured(unit())],
             [TEV, PRIMARY, FALLBACK_DECISION, FALLBACK_DETAIL, FALLBACK_RETRY]),
        ]
        for settings, answers, expected in scenarios:
            with self.subTest(settings=settings, expected=expected):
                _, captured = self.run_pipeline(*answers, **settings)
                self.assertEqual(captured, expected)


if __name__ == '__main__':
    unittest.main()
