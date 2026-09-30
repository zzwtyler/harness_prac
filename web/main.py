"""Dependency-free local web UI for the Qwen task normalizer."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error, request

from core import StageRegistry
from core import execution_config


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "web" / "static"
STAGE_DIR = ROOT / "web" / "stages"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
MAX_REQUEST_BYTES = 128 * 1024
MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
STAGES = StageRegistry(STAGE_DIR)


class AppHandler(BaseHTTPRequestHandler):
    server_version = "IntentWorkbench/1.0"

    def log_message(self, format_string: str, *args: Any) -> None:
        sys.stdout.write(
            f"[{self.log_date_time_string()}] {self.address_string()} "
            f"{format_string % args}\n"
        )

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/api/status":
            self._handle_status()
            return

        if self.path == "/api/stages":
            self._handle_stages()
            return

        route = self.path.split("?", 1)[0]
        if route == "/":
            self._serve_file(STATIC_DIR / "index.html")
            return

        if route.startswith("/static/"):
            relative_path = route.removeprefix("/static/")
            candidate = (STATIC_DIR / relative_path).resolve()
            if STATIC_DIR.resolve() not in candidate.parents:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "文件不存在。"})
                return
            self._serve_file(candidate)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "页面不存在。"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path not in ("/api/chat", "/api/run"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在。"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0

        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "请求内容为空或超过 128 KB。"},
            )
            return

        try:
            incoming = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "请求不是有效 JSON。"})
            return

        message = str(incoming.get("message", "")).strip()
        project_context = str(incoming.get("projectContext", "")).strip()
        model = str(incoming.get("model", execution_config.DEFAULT_DETAIL_MODEL)).strip()
        decision_model = str(incoming.get('decisionModel', execution_config.DEFAULT_DECISION_MODEL)).strip()
        fallback_model = str(incoming.get('fallbackModel', execution_config.DEFAULT_FALLBACK_MODEL)).strip()
        confidence_threshold = incoming.get('confidenceThreshold', execution_config.DEFAULT_CONFIDENCE_THRESHOLD)
        cascade_enabled = incoming.get('cascadeEnabled', True)
        think = bool(incoming.get("think", False))

        try:
            stage = STAGES.get(incoming.get("stageId"))
        except LookupError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": (
                        "无法运行 Harness stage。请检查对应的编号 Python 文件："
                        f"{exc.__class__.__name__}: {exc}"
                    )
                },
            )
            return

        system_prompt = str(incoming.get("systemPrompt", stage.system_prompt)).strip()

        if not message:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "请输入需要分析的任务。"})
            return
        if len(message) > 20_000:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "任务内容不能超过 20,000 字。"})
            return
        if len(project_context) > 8_000:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "项目背景不能超过 8,000 字。"})
            return
        if not MODEL_NAME_PATTERN.fullmatch(model) or not MODEL_NAME_PATTERN.fullmatch(decision_model) or not MODEL_NAME_PATTERN.fullmatch(fallback_model):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "模型名称格式无效。"})
            return
        try:
            execution_config.ExtractionTask(message, model=model, decision_model=decision_model,
                fallback_model=fallback_model, confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
        except (ValueError, PermissionError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {'error': str(exc)})
            return
        if not system_prompt or len(system_prompt) > 12_000:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "System prompt 不能为空或超过 12,000 字。"},
            )
            return

        if stage.runner is not None:
            self._run_extraction(stage, message, model=model, decision_model=decision_model, think=think,
                fallback_model=fallback_model, confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
            return

        self._proxy_chat(
            stage.make_ollama_payload(
                message,
                model=model,
                system_prompt=system_prompt,
                think=think,
                stream=True,
                project_context=project_context,
            )
        )

    def _run_extraction(self, stage, message: str, *, model: str, decision_model: str, think: bool,
                        fallback_model: str, confidence_threshold: float, cascade_enabled: bool) -> None:
        # Validate the complete result before sending any model content to the UI.
        # Background/examples and editable system prompts are not evidence sources.
        try:
            result = stage.runner(message, model=model, decision_model=decision_model, base_url=OLLAMA_BASE_URL, think=think,
                fallback_model=fallback_model, confidence_threshold=confidence_threshold, cascade_enabled=cascade_enabled)
        except (ValueError, TypeError, KeyError) as exc:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": f"提取校验失败：{exc}"})
            return
        except OSError as exc:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": f"模型调用失败：{exc}"})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self._write_event({"type": "content", "text": json.dumps(asdict(result), ensure_ascii=False)})
            self._write_event({"type": "done", "metrics": {}})
        except (BrokenPipeError, ConnectionResetError):
            return

    def _handle_stages(self) -> None:
        try:
            stages = [stage.descriptor() for stage in STAGES.all()]
            self._send_json(HTTPStatus.OK, {"stages": stages})
        except Exception as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": (
                        "无法加载 Harness stages。请检查新增的编号 Python 文件："
                        f"{exc.__class__.__name__}: {exc}"
                    )
                },
            )

    def _handle_status(self) -> None:
        upstream = request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        try:
            with request.urlopen(upstream, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [
                {
                    "name": item.get("name", ""),
                    "capabilities": item.get("capabilities", []),
                }
                for item in payload.get("models", [])
                if item.get("name")
            ]
            self._send_json(HTTPStatus.OK, {"online": True, "models": models})
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "online": False,
                    "models": [],
                    "error": f"无法连接本地 Ollama：{self._friendly_upstream_error(exc)}",
                },
            )

    def _proxy_chat(self, payload: dict[str, Any]) -> None:
        upstream = request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            response = request.urlopen(upstream, timeout=600)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(detail).get("error", detail)
            except json.JSONDecodeError:
                pass
            self._send_json(
                exc.code,
                {"error": f"Ollama 拒绝了请求：{detail}"},
            )
            return
        except (error.URLError, TimeoutError) as exc:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": (
                        "无法连接本地 Ollama。请先运行 `ollama serve`，并确认模型已下载。"
                        f"（{self._friendly_upstream_error(exc)}）"
                    )
                },
            )
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

        try:
            with response:
                for raw_line in response:
                    if not raw_line.strip():
                        continue
                    try:
                        chunk = json.loads(raw_line.decode("utf-8"))
                        message = chunk.get("message", {})
                        thinking = message.get("thinking", "")
                        content = message.get("content", "")

                        if thinking:
                            self._write_event({"type": "thinking", "text": thinking})
                        if content:
                            self._write_event({"type": "content", "text": content})
                        if chunk.get("done"):
                            self._write_event(
                                {
                                    "type": "done",
                                    "metrics": {
                                        "promptTokens": chunk.get("prompt_eval_count"),
                                        "outputTokens": chunk.get("eval_count"),
                                        "durationNs": chunk.get("total_duration"),
                                    },
                                }
                            )
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        self._write_event(
                            {"type": "error", "error": f"无法解析模型流：{exc}"}
                        )
                        break
        except (BrokenPipeError, ConnectionResetError):
            return
        except (error.URLError, TimeoutError) as exc:
            try:
                self._write_event(
                    {
                        "type": "error",
                        "error": f"模型流中断：{self._friendly_upstream_error(exc)}",
                    }
                )
            except (BrokenPipeError, ConnectionResetError):
                return

    def _write_event(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        self.wfile.write(line.encode("utf-8"))
        self.wfile.flush()

    def _serve_file(self, path: Path) -> None:
        if not path.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "文件不存在。"})
            return

        mime_type, _ = mimetypes.guess_type(path.name)
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type", f"{mime_type or 'application/octet-stream'}; charset=utf-8"
        )
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, status: HTTPStatus | int, payload: dict[str, Any]) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    @staticmethod
    def _friendly_upstream_error(exc: BaseException) -> str:
        reason = getattr(exc, "reason", exc)
        return str(reason)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动 Qwen 任务清样前端")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"任务清样已启动：http://{args.host}:{args.port}")
    print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止……")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
