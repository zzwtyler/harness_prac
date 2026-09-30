"""Exercise the new stage boundary and same-named class modules."""
import json
import unittest
from dataclasses import asdict
from unittest.mock import patch

from core import models as _models
ExtractedInput = _models.ExtractedInput
Intent = _models.Intent
from core import paths as _paths
ROOT = _paths.ROOT
execution_sources = _paths.execution_sources
from core import schema as _schema
model_json_schema = _schema.model_json_schema
from core import task_loader as _task_loader
load_task = _task_loader.load_task
from test_harness import response, model_responder
from typing import get_args


class StageBoundaryTests(unittest.TestCase):
    def test_all_intent_types_feed_matching_task_without_another_model_call(self):
        first = load_task(ROOT / 'core/01_user_intent.py')
        second = load_task(ROOT / 'core/02_task.py')
        intent_catalog = json.loads((ROOT / 'core/01_user_intent_classes/index.json').read_text())
        task_catalog = json.loads((ROOT / 'core/02_task_classes/index.json').read_text())
        self.assertEqual({entry['id'] for entry in intent_catalog}, set(get_args(Intent)))
        self.assertEqual({entry['id'] for entry in task_catalog}, set(get_args(Intent)))
        for entry in intent_catalog:
            with self.subTest(intent=entry['id']):
                plan = {'intent': entry['id'], 'selections': [{'category': 'request', 'clause_index': 0}]}
                with patch('core.runtime.open_model_request', side_effect=model_responder(plan)) as network:
                    intent = first.normalize_task('请帮我处理')
                    self.assertEqual(type(intent).__name__, entry['model'])
                    self.assertIsInstance(intent, ExtractedInput)
                    task = second.build_task(intent)
                    self.assertEqual(network.call_count, 1 if entry['id'] == 'no_intent' else 2)
                self.assertEqual(task.source_text, intent.source_text)
                self.assertEqual(asdict(task)['keywords'], asdict(intent)['keywords'])
                # Resolve hints after loading the same filename in the task directory.
                schema = model_json_schema(type(intent))
                self.assertEqual(schema['properties']['intent']['enum'], [entry['id']])

    def test_same_named_intent_and_task_modules_have_distinct_namespaces(self):
        intent = load_task(ROOT / 'core/01_user_intent_classes/group_order.py')
        task = load_task(ROOT / 'core/02_task_classes/group_order.py')
        self.assertNotEqual(intent.__name__, task.__name__)
        self.assertIn('intent', model_json_schema(intent.GroupOrderIntent)['properties'])
        self.assertIn('budget', model_json_schema(task.GroupOrderLead)['properties'])

    def test_task_stage_rejects_invalid_input_without_calling_model(self):
        second = load_task(ROOT / 'core/02_task.py')
        with patch('core.runtime.open_model_request', side_effect=AssertionError('阶段02不应调用模型')):
            with self.assertRaises(ValueError):
                second.build_task(ExtractedInput('请帮我处理', 'unknown', []))

    def test_checkpoint_fingerprint_covers_both_stages_and_class_catalogs(self):
        sources = {str(path.relative_to(ROOT)) for path in execution_sources()}
        for name in ('core/01_user_intent.py', 'core/02_task.py', 'harness/main.py',
                     'core/01_user_intent_classes/index.json', 'core/02_task_classes/index.json',
                     'core/01_user_intent_classes/group_order.py', 'core/02_task_classes/group_order.py'):
            self.assertIn(name, sources)


if __name__ == '__main__':
    unittest.main()
