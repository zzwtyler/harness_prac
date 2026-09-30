import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_harness import model_responder, respond_to_plan, response
from test_intent_layers import protocol_response, protocol_sequence

ROOT = Path(__file__).resolve().parents[1]


def reply(plan):
    return io.BytesIO(json.dumps({'message': {'content': json.dumps(plan)}, 'done': True}).encode())


class ExecutionTests(unittest.TestCase):
    def engine(self):
        self.assertTrue((ROOT / 'harness/main.py').exists(), '缺少统一执行与恢复入口')
        from harness.main import execute_task
        return execute_task

    def test_intents_are_unnumbered_and_catalog_drives_routing(self):
        self.assertTrue((ROOT / 'core/02_task_classes/index.json').exists(), '缺少独立intent目录与序号配置')
        from core import task_registry as _task_registry
        TaskRegistry = _task_registry.TaskRegistry
        registry = TaskRegistry()
        self.assertEqual(len(registry.all()), 11)
        self.assertEqual(registry.get('group_order').module.__file__, str(ROOT / 'core/02_task_classes/group_order.py'))
        self.assertFalse(list((ROOT / 'core/02_task_classes').glob('[0-9][0-9]_*.py')))
        self.assertFalse((ROOT / '02_group_order.py').exists())

    def test_retries_invalid_selection_then_preserves_only_grounded_result(self):
        execute = self.engine()
        bad = {'intent': 'group_order', 'selections': [{'category': 'request', 'clause_index': 0}, {'category': 'budget', 'clause_index': 99}]}
        good = {'intent': 'group_order', 'selections': [{'category': 'request', 'clause_index': 0}, {'category': 'budget', 'clause_index': 1}]}
        routing = {'input_kind': 'request', 'intents': [{'intent': 'group_order', 'clause_indices': [0, 1]}]}
        bad_detail = {'intents': [{'intent_index': 0, 'subtype': 'new_order', 'selections': bad['selections']}]}
        good_detail = {'intents': [{'intent_index': 0, 'subtype': 'new_order', 'selections': good['selections']}]}
        answers = protocol_sequence(routing, bad_detail, good_detail)
        with patch('core.runtime.open_model_request', side_effect=lambda req, timeout: protocol_response(req, next(answers))):
            output = execute('请安排团订，预算500元', cascade_enabled=False)
        self.assertEqual(output['result']['budget'], ['预算500元'])
        self.assertEqual(output['state']['attempts'], 2)
        self.assertEqual(output['state']['status'], 'completed')
        self.assertTrue(output['verification']['source_grounded'])

    def test_retry_budget_stops_and_persists_failure_state(self):
        execute = self.engine()
        with tempfile.TemporaryDirectory() as tmp:
            with patch('core.runtime.open_model_request', side_effect=OSError('offline')) as network:
                with self.assertRaises(OSError):
                    execute('积分没到', output_directory=Path(tmp), max_attempts=2)
            self.assertEqual(network.call_count, 2)
            state = json.loads((Path(tmp) / '00_run_state.json').read_text())
            self.assertEqual(state['status'], 'failed')
            self.assertEqual(state['attempts'], 2)
            self.assertFalse((Path(tmp) / '08_membership_help.json').exists())

    def test_resume_reuses_checkpoint_without_new_model_call(self):
        execute = self.engine()
        plan = {'intent': 'membership_help', 'selections': [{'category': 'issue', 'clause_index': 0}, {'category': 'request', 'clause_index': 0}]}
        with tempfile.TemporaryDirectory() as tmp:
            with patch('core.runtime.open_model_request', side_effect=model_responder(plan)):
                first = execute('积分没到', output_directory=Path(tmp))
            with patch('core.runtime.open_model_request', side_effect=AssertionError('不应重新调用模型')):
                resumed = execute('积分没到', output_directory=Path(tmp), resume=True)
            self.assertEqual(resumed['result'], first['result'])
            self.assertTrue(resumed['state']['resumed'])
            with self.assertRaises(ValueError):
                execute('换一个请求', output_directory=Path(tmp), resume=True)

    def test_remote_model_and_long_context_rejected_before_network(self):
        execute = self.engine()
        with patch('core.runtime.open_model_request', side_effect=AssertionError('不应发出请求')):
            with self.assertRaises(PermissionError):
                execute('积分没到', base_url='https://example.com')
            with self.assertRaises(ValueError):
                execute('字' * 20001)

    def test_verification_rejects_added_business_fact(self):
        self.engine()
        from core import verification as _verification
        verify_result = _verification.verify_result
        from core import extraction as _extraction
        ExtractedInput = _extraction.ExtractedInput
        from core import task_registry as _task_registry
        TaskRegistry = _task_registry.TaskRegistry
        definition = TaskRegistry().get('store_info')
        with patch('core.runtime.open_model_request', side_effect=model_responder({'intent': 'store_info', 'selections': [{'category': 'request', 'clause_index': 0}]})):
            original = _extraction.extract_user_input('几点营业？')
        result = definition.module.from_extraction(original)
        result.opening_hours = ['8:00']
        with self.assertRaises(ValueError):
            verify_result(original, result, definition)

    def test_result_store_does_not_allow_path_escape(self):
        self.engine()
        from core import state as _state
        ResultStore = _state.ResultStore
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PermissionError):
                ResultStore(Path(tmp)).write('../outside', {'bad': True})

    def test_incomplete_http_response_retries_and_reports_failure(self):
        from http.client import IncompleteRead
        execute = self.engine()
        with tempfile.TemporaryDirectory() as tmp:
            with patch('core.runtime.open_model_request', side_effect=IncompleteRead(b'partial')) as network:
                with self.assertRaises(OSError):
                    execute('积分没到', output_directory=Path(tmp), max_attempts=2)
            self.assertEqual(network.call_count, 2)
            self.assertEqual(json.loads((Path(tmp) / '00_run_state.json').read_text())['status'], 'failed')

    def test_context_checks_serialized_budget_without_truncation(self):
        self.engine()
        from core import context as _context
        prepare_context = _context.prepare_context
        with self.assertRaises(ValueError):
            prepare_context('字' * 10000)

    def test_resume_rejects_tampered_checkpoint(self):
        execute = self.engine()
        with tempfile.TemporaryDirectory() as tmp:
            plan = {'intent': 'membership_help', 'selections': [{'category': 'issue', 'clause_index': 0}, {'category': 'request', 'clause_index': 0}]}
            with patch('core.runtime.open_model_request', side_effect=model_responder(plan)):
                execute('积分没到', output_directory=Path(tmp))
            checkpoint = Path(tmp) / '01_user_intent.json'
            value = json.loads(checkpoint.read_text())
            value['intent'] = 'store_info'
            checkpoint.write_text(json.dumps(value))
            with patch('core.runtime.open_model_request', side_effect=AssertionError('不应调用模型')):
                with self.assertRaises(ValueError):
                    execute('积分没到', output_directory=Path(tmp), resume=True)

    def test_unauthorized_tool_is_denied(self):
        self.engine()
        from core import permissions as _permissions
        require = _permissions.require
        with self.assertRaises(PermissionError):
            require('shell.exec')

    def test_symlink_result_is_not_followed(self):
        self.engine()
        from core import state as _state
        ResultStore = _state.ResultStore
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'outside.json').write_text('original')
            (root / '01_user_intent.json').symlink_to(root / 'outside.json')
            with self.assertRaises(PermissionError):
                ResultStore(root).write('01_user_intent', {'new': True})
            self.assertEqual((root / 'outside.json').read_text(), 'original')

if __name__ == '__main__':
    unittest.main()
