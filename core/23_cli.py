"""Run intent normalization, then the matching business stage; save results only."""
import argparse
import json
from pathlib import Path


def main(run_harness):
    from core import execution_config
    parser = argparse.ArgumentParser(description='完整 Harness：意图 → 业务结果；不保存思考流')
    parser.add_argument('request', help='当前用户请求')
    parser.add_argument('--output', type=Path, help='保存编号 JSON 的新目录；省略则只输出到终端')
    parser.add_argument('--context', type=Path, help='兼容旧参数；纯提取模式不使用项目背景')
    parser.add_argument('--model', default=execution_config.DEFAULT_DETAIL_MODEL,
                        help='详情标注模型；旧model参数兼容为此角色')
    parser.add_argument('--decision-model', default=execution_config.DEFAULT_DECISION_MODEL,
                        help='原生字母决策模型，默认tev1:4b')
    parser.add_argument('--fallback-model', default=execution_config.DEFAULT_FALLBACK_MODEL, help='级联重审/提取模型，默认qwen3:8b')
    parser.add_argument('--confidence-threshold', type=float, default=execution_config.DEFAULT_CONFIDENCE_THRESHOLD, help='所选决策token概率阈值，默认0.8；非校准正确率')
    parser.add_argument('--no-cascade', dest='cascade_enabled', action='store_false', help='关闭自动升级，用于对照')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    parser.add_argument('--think', action='store_true', help='启用模型内部思考，但不保存思考流')
    parser.add_argument('--resume', action='store_true', help='显式恢复相同输入及代码配置的检查点')
    parser.add_argument('--max-attempts', type=int, default=2, help='每条primary/fallback lane的尝试预算，1至3')
    parser.add_argument('--timeout', type=float, default=60, help='单次模型请求超时，最多120秒')
    args = parser.parse_args()
    if args.output and args.output.exists() and not args.resume and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error('输出目录非空，请选择新目录以避免混入旧结果')
    try:
        result = run_harness(args.request, project_context=args.context.read_text(encoding='utf-8') if args.context else None,
                             model=args.model, decision_model=args.decision_model, base_url=args.base_url, think=args.think, output_directory=args.output, resume=args.resume,
                             max_attempts=args.max_attempts, timeout_seconds=args.timeout,
                             fallback_model=args.fallback_model, confidence_threshold=args.confidence_threshold,
                             cascade_enabled=args.cascade_enabled)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f'Harness 运行失败：{type(exc).__name__}: {exc}\n')
