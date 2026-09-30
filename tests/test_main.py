import json
import tempfile
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from core import StageRegistry
from core import schema as _schema
model_from_dict = _schema.model_from_dict
from web.main import AppHandler, ROOT, STAGE_DIR


class _BytesReader:
    def __init__(self, value: bytes):
        self.value = value

    def read(self, length: int) -> bytes:
        return self.value[:length]


class StageRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = StageRegistry(STAGE_DIR)

    def test_user_intent_stage_is_the_web_source_of_truth(self) -> None:
        stage = self.registry.get("user_intent")
        schema = stage.output_schema

        self.assertEqual(list(schema["properties"]), ["source_text", "intent", "keywords", "input_kind", "intents", "decision",
                                                    "confidence", "confidence_details", "cascade",
                                                    "manual_review_required", "review_reasons"])
        self.assertIn("group_order", schema["properties"]["intent"]["enum"])
        self.assertIn("start", schema["properties"]["keywords"]["items"]["properties"])

    def test_stage_builds_ollama_payload(self) -> None:
        stage = self.registry.get()
        payload = stage.make_ollama_payload("做一个响应式网页")

        self.assertEqual(payload["model"], "qwen3.5:4b")
        self.assertTrue(payload["think"])
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["messages"][0]["content"], stage.system_prompt)
        self.assertEqual(payload["messages"][1]["content"], "做一个响应式网页")
        self.assertEqual(payload["format"], stage.output_schema)

    def test_project_context_is_sent_as_background_before_stage_input(self) -> None:
        stage = self.registry.get()
        payload = stage.make_ollama_payload(
            "继续编写任务规划 Stage",
            project_context="项目：本地 Qwen Harness。现有 Stage 01。",
        )
        content = payload["messages"][1]["content"]

        self.assertIn("仅供理解当前任务", content)
        self.assertIn("项目：本地 Qwen Harness。现有 Stage 01。", content)
        self.assertTrue(content.endswith("【当前阶段输入：请以此为当前要处理的任务】\n继续编写任务规划 Stage"))

    def test_model_validates_nested_result(self) -> None:
        stage = self.registry.get()
        result = model_from_dict(stage.model_type, {
            "source_text": "预算500元", "intent": "group_order",
            "keywords": [{"category": "budget", "text": "预算500元", "start": 0, "end": 6}],
        })
        self.assertEqual(result.keywords[0].category, "budget")
        self.assertEqual(asdict(result)["source_text"], "预算500元")

    def test_task_file_does_not_contain_web_stage_configuration(self) -> None:
        source = (ROOT / "core/01_user_intent.py").read_text(encoding="utf-8")

        self.assertNotIn("HarnessStage", source)
        self.assertNotIn("presentation=", source)
        self.assertNotIn("examples=", source)
        self.assertIn("def normalize_task", source)

    def test_registry_hot_reloads_changed_stage_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "02_demo.py"
            path.write_text(self._demo_stage("第一版"), encoding="utf-8")
            registry = StageRegistry(Path(directory))
            self.assertEqual(registry.get().title, "第一版")

            time.sleep(0.002)
            path.write_text(self._demo_stage("第二版"), encoding="utf-8")
            self.assertEqual(registry.get().title, "第二版")

    def test_stages_endpoint_turns_broken_module_into_json_error(self) -> None:
        handler = object.__new__(AppHandler)
        captured = {}

        def capture(status, payload):
            captured.update(status=status, payload=payload)

        handler._send_json = capture
        with patch("web.main.STAGES.all", side_effect=SyntaxError("bad stage")):
            handler._handle_stages()

        self.assertEqual(captured["status"], 500)
        self.assertIn("SyntaxError", captured["payload"]["error"])
        self.assertIn("编号 Python 文件", captured["payload"]["error"])

    def test_run_endpoint_turns_broken_stage_into_json_error(self) -> None:
        body = b'{"stageId":"broken","message":"hello","model":"qwen3:4b"}'
        handler = object.__new__(AppHandler)
        handler.path = "/api/run"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = _BytesReader(body)
        captured = {}
        handler._send_json = lambda status, payload: captured.update(status=status, payload=payload)

        with patch("web.main.STAGES.get", side_effect=ImportError("broken import")):
            handler.do_POST()

        self.assertEqual(captured["status"], 500)
        self.assertIn("ImportError", captured["payload"]["error"])

    def test_run_endpoint_rejects_oversized_project_context(self) -> None:
        body = ("{\"message\":\"hello\",\"projectContext\":\"" + "x" * 8001 + "\"}").encode()
        handler = object.__new__(AppHandler)
        handler.path = "/api/run"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = _BytesReader(body)
        captured = {}
        handler._send_json = lambda status, payload: captured.update(status=status, payload=payload)

        handler.do_POST()

        self.assertEqual(captured["status"], 400)
        self.assertIn("项目背景不能超过", captured["payload"]["error"])

    def test_web_extraction_ignores_background_and_prompt_override(self) -> None:
        from test_harness import response, respond_to_plan, model_responder
        body = json.dumps({"stageId": "membership_help", "message": "积分没到", "projectContext": "北京24小时到账", "systemPrompt": "编造规则"}).encode()
        handler = object.__new__(AppHandler)
        handler.path = "/api/run"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = _BytesReader(body)
        handler.send_response = lambda *a: None
        handler.send_header = lambda *a: None
        handler.end_headers = lambda: None
        events = []
        handler._write_event = events.append
        sent = []
        def upstream(req, timeout):
            sent.append(json.loads(req.data))
            return respond_to_plan(req, {"intent": "membership_help", "selections": [
                {"category": "issue", "clause_index": 0}, {"category": "request", "clause_index": 0}]})
        with patch('core.runtime.open_model_request', side_effect=upstream):
            handler.do_POST()
        result = json.loads(events[0]['text'])
        self.assertEqual(result['issue'], ['积分没到'])
        self.assertEqual(result['policy'], [])
        self.assertNotIn('北京', json.dumps(sent, ensure_ascii=False))
        self.assertNotIn('编造规则', json.dumps(sent, ensure_ascii=False))
        self.assertEqual([event['type'] for event in events], ['content', 'done'])

    def test_web_invalid_selection_returns_error_without_content(self):
        from test_harness import response, respond_to_plan, model_responder
        body = b'{"stageId":"store_info","message":"hello"}'
        handler = object.__new__(AppHandler)
        handler.path = '/api/run'
        handler.headers = {'Content-Length': str(len(body))}
        handler.rfile = _BytesReader(body)
        captured = {}
        handler._send_json = lambda status, payload: captured.update(status=status, payload=payload)
        with patch('core.runtime.open_model_request', side_effect=model_responder({'intent': 'store_info', 'selections': [{'category': 'location', 'clause_index': 9}]})):
            handler.do_POST()
        self.assertEqual(captured['status'], 422)

    @staticmethod
    def _demo_stage(title: str) -> str:
        return f'''\
from dataclasses import dataclass
from core import HarnessStage, SchemaModel, schema_field
@dataclass
class Demo(SchemaModel):
    value: str = schema_field(description="demo")
STAGE = HarnessStage(id="demo", order=2, title="{title}", description="demo", model_type=Demo, system_prompt="中文")
'''


if __name__ == "__main__":
    unittest.main()
