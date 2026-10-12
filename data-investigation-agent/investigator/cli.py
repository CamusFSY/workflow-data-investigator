import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .loop import run
from .provenance import data_label

GOAL = "上周准时交付率下降，判断是否真的延误，给我可复跑的证据。"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="data-investigator",
        description="Read-only data investigation tools and offline evidence replay. Synthetic data or explicitly allowlisted public snapshots.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("run", help="Run the explicitly scripted demo; no API key or model call")
    demo.add_argument("--fixture", required=True)
    demo.add_argument("--out", required=True, help="New output directory, never overwritten")
    demo.add_argument("--goal", default=GOAL)
    demo.add_argument("--mode", choices=["mock", "live"], default="mock")
    demo.add_argument("--inject-schema-error", action="store_true", help="Mock-only error exercise")
    demo.add_argument("--max-steps", type=int, default=24, help="Maximum model turns (1..40)")
    demo.add_argument("--max-tool-actions", type=int, help="Total tool action cap (1..40); defaults to max-steps")
    demo.add_argument("--max-seconds", type=int, default=60)
    replay = sub.add_parser("replay", help="Verify recorded tool results offline, including errors")
    replay.add_argument("directory")
    inspect = sub.add_parser("inspect", help="Load/inspect a public bundle without a provider")
    inspect.add_argument("--fixture", "--bundle", dest="fixture", required=True)
    inspect.add_argument("--out", required=True)
    check = sub.add_parser("validate", help="Validate a synthetic or allowlisted public CSV bundle locally; no provider")
    check.add_argument("--bundle", required=True)
    recorded = sub.add_parser("investigate", help="Run supplied offline response bodies through real tools; not a live model")
    recorded.add_argument("--bundle", dest="fixture", required=True)
    recorded.add_argument("--responses", required=True, help="Bounded local recording JSON; fixed actions, no network")
    recorded.add_argument("--out", required=True, help="New output directory, never overwritten")
    recorded.add_argument("--goal", help="Defaults to the bundle request.txt")
    recorded.add_argument("--max-steps", type=int, default=24)
    recorded.add_argument("--max-tool-actions", type=int)
    recorded.add_argument("--max-seconds", type=int, default=60)
    recorded.add_argument("--answer-contract", help="Explicit caller-owned shape JSON (<=24000 bytes); no expected answers")
    args = parser.parse_args(argv)
    if args.command == "validate":
        from .bundle import validate_bundle
        try:
            print(json.dumps(validate_bundle(args.bundle), ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            print(json.dumps({"status": "invalid", "provider_calls": 0,
                              "error": {"type": type(exc).__name__, "message": str(exc)}},
                             ensure_ascii=False, indent=2))
            return 2
    if args.command == "replay":
        from .replay import verify
        try:
            verify(args.directory)
        except OSError as exc:
            print(f"REPLAY INPUT ERROR: {exc}", file=sys.stderr)
            return 2
        except (ValueError, AssertionError, KeyError, TypeError) as exc:
            print(f"REPLAY VERIFICATION FAILED: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "inspect":
        from .bundle import prepare_bundle
        from .runtime import Runtime
        try:
            manifest = prepare_bundle(args.fixture, args.out)
            output = Path(args.out).absolute()
            schema = Runtime(output / "input", provenance=manifest["provenance"]).call("schema", "inspect_schema", {})
            (output / "input_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            (output / "schema.json").write_text(json.dumps(schema, indent=2) + "\n")
            print("DATA LOAD ONLY · " + data_label(manifest["provenance"]) + " · no provider / no Agent success claim")
            print(json.dumps(schema, ensure_ascii=False, indent=2))
            return 0 if schema["ok"] else 1
        except Exception as exc:
            print(f"SETUP ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
    if args.command == "run" and args.mode == "live":
        print("LIVE_TRANSPORT_REQUIRED: This CLI has no model transport. Integrate a provider via "
              "ChatCompletionsProvider and explicitly authorize data sharing in your caller. "
              "The CLI does not read credentials or make API calls. See docs/provider-integration.md.",
              file=sys.stderr)
        return 2

    def show(event):
        result = event["result"]
        print(f"\n[{event['evidence_id']}] {event['tool']} "
              f"{'OK' if result['ok'] else 'ERROR'} — {event['public_note']}", flush=True)
        if not result["ok"]:
            print(json.dumps(result["error"], ensure_ascii=False), flush=True)
        elif event["tool"] in {"query", "analyze"}:
            print(json.dumps(result["data"], ensure_ascii=False)[:1000], flush=True)

    try:
        answer_contract = None
        if args.command == "investigate":
            from .bundle import safe_read
            from .evidence import load_answer_contract
            from .recording import RecordedProvider
            if args.answer_contract is not None:
                answer_contract = load_answer_contract(args.answer_contract)
            provider = RecordedProvider(args.responses)
            if args.goal is None:
                source = Path(args.fixture).absolute()
                if any(p.is_symlink() for p in [source, *source.parents]):
                    raise ValueError("Symlink bundle paths are not accepted")
                args.goal = safe_read(source, "request.txt", 65536).decode("utf-8").strip()
            print("=== OFFLINE RECORDED RESPONSES · DATA CLASSIFICATION PENDING VALIDATION · 0 API CALLS ===", flush=True)
            print("Fixed supplied responses exercise real tools; no new model decisions.", flush=True)
        else:
            from .mock import ScriptedMock
            provider = ScriptedMock(args.inject_schema_error)
            print("=== SCRIPTED MOCK · DATA CLASSIFICATION PENDING VALIDATION · 0 API CALLS ===", flush=True)
            print("仅验证工具/反馈/交付闭环；不是模型自主成功证明。", flush=True)
        print("目标：" + args.goal, flush=True)
        outcome = run(args.goal, args.fixture, args.out,
                      provider, args.max_steps, args.max_seconds, show,
                      max_tool_actions=args.max_tool_actions, answer_contract=answer_contract)
    except Exception as exc:
        print(f"SETUP ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print("\n" + data_label(outcome["provenance"]), flush=True)
    print("状态：" + outcome["status"], flush=True)
    if outcome["answer"]:
        for condition in outcome["answer"].get("conditions", []):
            print("适用假设（未经确认）：" + condition, flush=True)
        for question in outcome["answer"]["questions"]:
            print("需确认：" + question, flush=True)
        print(outcome["answer"]["summary"], flush=True)
        if outcome.get("evidence_interface") == "answer_roles_v1":
            print("答案证据：" + str(outcome["answer"].get("answer_evidence_id", "未提供")), flush=True)
            print("支持证据：" + ", ".join(outcome["answer"]["supporting_evidence_ids"]), flush=True)
            print("来源、类型、形状已校验；数值正确性与支持相关性需另行核对。", flush=True)
    print(f"证据交付物：{args.out}/report.html · investigation.ipynb · trace.jsonl", flush=True)
    print(f"复跑：python {args.out}/replay.py", flush=True)
    return 1 if outcome["status"] == "failed" else 0
