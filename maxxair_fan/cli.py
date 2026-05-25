import argparse
import json
import sys
from pathlib import Path

from maxxair_fan import config, fan
from maxxair_fan import main as app_main
from maxxair_fan.agent import run_agent
from maxxair_fan.backends import (
    FakeIRBackend,
    FakeSensorBackend,
    InMemoryFirebaseBackend,
    build_backends,
    load_fan_units,
)
from maxxair_fan.devtools.replay import load_expected_ir, run_replay_fixture
from maxxair_fan.devtools.tui import LiveTUI, format_iteration_state
from maxxair_fan.fans_config import load_fans_config


def _simulator_backends() -> tuple[FakeSensorBackend, FakeIRBackend, InMemoryFirebaseBackend]:
    log_path = Path(config.FAKE_IR_LOG) if config.FAKE_IR_LOG else None
    sensor_be, ir_be, fb_be = build_backends(
        fake_sensor=FakeSensorBackend.from_config(config.FAKE_SENSOR_TEMP),
        fake_ir=FakeIRBackend(log_path=log_path),
        memory_firebase=InMemoryFirebaseBackend(
            {
                "fans": {
                    "fan1": {
                        "targetTemp": 72.0,
                        "direction": "in",
                    }
                }
            }
        ),
    )
    return sensor_be, ir_be, fb_be  # type: ignore[return-value]


def cmd_run(args: argparse.Namespace) -> int:
    tui = LiveTUI(enabled=args.tui)
    on_iteration = tui if args.tui else None

    try:
        if args.simulator:
            sensor_be, ir_be, fb_be = _simulator_backends()
            app_main.main(
                once=args.once,
                use_lock=not args.once,
                skip_preflight=True,
                sensor_be=sensor_be,
                ir_be=ir_be,
                fb_be=fb_be,
                on_iteration=on_iteration,
            )
        else:
            app_main.main(once=args.once, on_iteration=on_iteration)
    finally:
        tui.close()

    return 0


def cmd_check(_args: argparse.Namespace) -> int:
    _, _, fb_be = build_backends()
    try:
        fan_units = load_fan_units()
    except (FileNotFoundError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    errors = app_main.validate_runtime(fb_be, fan_units)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"OK: runtime preflight passed ({len(fan_units)} fan(s))")
    return 0


def cmd_agent(args: argparse.Namespace) -> int:
    config.configure_logging()
    run_agent(bind=args.bind, port=args.port)
    return 0


def cmd_send_ir(args: argparse.Namespace) -> int:
    _, ir_be, _ = build_backends()
    ok = ir_be.send(args.filename)
    return 0 if ok else 1


def cmd_simulate(args: argparse.Namespace) -> int:
    speed = fan.compute_speed(args.temp, args.target, args.gradient, args.exponent)
    filename = fan.resolve_ir_filename(args.direction, speed)
    diff = args.temp - args.target

    print(f"temp={args.temp}°F target={args.target}°F diff={diff:+.1f}°F")
    print(f"speed={speed}% direction={args.direction} file={filename}")
    print()
    print("Ryder Henry fan curve (around current diff):")

    for delta in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        sample_current = args.target + delta
        sample_speed = fan.compute_speed(sample_current, args.target, args.gradient, args.exponent)
        marker = " <--" if abs(delta - max(diff, 0)) < 0.01 else ""
        print(f"  +{delta:.1f}°F -> {sample_speed:>3}%{marker}")

    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    fixture = json.loads(Path(args.fixture).read_text())
    steps = fixture.get("steps", [])
    interval = config.CHECK_INTERVAL / max(args.rate, 0.001)

    print(f"Replaying {len(steps)} steps (rate={args.rate}x)")

    def print_step(state: dict) -> None:
        print(format_iteration_state({**state, "patch_reason": "replay"}))

    sent, _memory_fb = run_replay_fixture(
        fixture,
        start_now=1000.0,
        step_seconds=interval,
        on_iteration=print_step,
    )

    print()
    print("IR commands sent:", sent)

    expected_path = args.expect
    if expected_path:
        expected = json.loads(Path(expected_path).read_text())
    else:
        expected = load_expected_ir(fixture)

    if expected is not None and sent != expected:
        print(f"ERROR: expected {expected}, got {sent}", file=sys.stderr)
        return 1

    return 0


def cmd_dump_state(_args: argparse.Namespace) -> int:
    print("MaxxAir Fan — resolved configuration")
    print(f"  MAXXAIR_BACKEND={config.MAXXAIR_BACKEND}")
    print(f"  SENSOR_BACKEND={config.SENSOR_BACKEND or '(default)'}")
    print(f"  IR_BACKEND={config.IR_BACKEND or '(default)'}")
    print(f"  FIREBASE_BACKEND={config.FIREBASE_BACKEND or '(default)'}")
    print(f"  FIREBASE_URL={config.FIREBASE_URL or '(unset)'}")
    print(f"  FANS_CONFIG={config.FANS_CONFIG or '(legacy single-fan env)'}")
    print(f"  FAN_NODE={config.FAN_NODE}")
    print(f"  IR_DIR={config.IR_DIR}")
    print(f"  IR_DEVICE={config.IR_DEVICE or '(default)'}")
    print(f"  SENSOR_PATH={config.SENSOR_PATH_OVERRIDE or '(auto-detect)'}")
    print(f"  LOCK_FILE={config.LOCK_FILE}")
    print(f"  CHECK_INTERVAL={config.CHECK_INTERVAL}")
    print(f"  AGENT_BIND={config.AGENT_BIND}")
    print(f"  AGENT_PORT={config.AGENT_PORT}")
    print(f"  AGENT_TOKEN={'(set)' if config.AGENT_TOKEN else '(unset)'}")

    try:
        specs = load_fans_config()
    except (FileNotFoundError, ValueError) as exc:
        print(f"  Fan registry error: {exc}")
        specs = []

    if specs:
        print(f"  Fans ({len(specs)}):")
        for spec in specs:
            if spec.is_local:
                local = spec.local
                sensor_path = local.sensor_path if local else None
                ir_device = local.ir_device if local else None
                print(
                    f"    - {spec.id}: local firebase={spec.firebase_node} "
                    f"sensor={sensor_path or '(auto)'} ir={ir_device or '(default)'}"
                )
            else:
                print(
                    f"    - {spec.id}: remote firebase={spec.firebase_node} "
                    f"agent={spec.agent_url}"
                )

    if config.IR_DIR.exists():
        ir_files = sorted(p.name for p in config.IR_DIR.glob("*.ir"))
        suffix = "..." if len(ir_files) > 5 else ""
        print(f"  IR files ({len(ir_files)}): {', '.join(ir_files[:5])}{suffix}")
    else:
        print(f"  IR_DIR missing: {config.IR_DIR}")

    if config.LOCK_FILE.exists():
        try:
            content = config.LOCK_FILE.read_text().strip()
            print(f"  Lock file present: {config.LOCK_FILE} -> {content}")
        except OSError:
            print(f"  Lock file present: {config.LOCK_FILE}")
    else:
        print(f"  Lock file: not held ({config.LOCK_FILE})")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maxxair_fan",
        description="MaxxAir fan Pi controller CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run the control loop")
    run_parser.add_argument(
        "--simulator",
        action="store_true",
        help="Use fake sensor/IR/memory Firebase",
    )
    run_parser.add_argument("--once", action="store_true", help="Run one iteration and exit")
    run_parser.add_argument("--tui", action="store_true", help="Show live status line on stderr")
    run_parser.set_defaults(func=cmd_run)

    check_parser = sub.add_parser("check", help="Validate Pi runtime preflight checks")
    check_parser.set_defaults(func=cmd_check)

    agent_parser = sub.add_parser("agent", help="Run edge HTTP agent for remote Pi hardware")
    agent_parser.add_argument(
        "--bind",
        default=config.AGENT_BIND,
        help=f"Bind address (default: {config.AGENT_BIND})",
    )
    agent_parser.add_argument(
        "--port",
        type=int,
        default=config.AGENT_PORT,
        help=f"Listen port (default: {config.AGENT_PORT})",
    )
    agent_parser.set_defaults(func=cmd_agent)

    send_parser = sub.add_parser("send-ir", help="Send a single IR code file")
    send_parser.add_argument("filename", help="IR filename, e.g. fan_on_in_50.ir")
    send_parser.set_defaults(func=cmd_send_ir)

    sim_parser = sub.add_parser("simulate", help="Compute speed for a temp/target without hardware")
    sim_parser.add_argument("--temp", type=float, required=True)
    sim_parser.add_argument("--target", type=float, default=72.0)
    sim_parser.add_argument("--direction", choices=("in", "out"), default="in")
    sim_parser.add_argument("--gradient", type=float, default=config.GRADIENT_DEGREES)
    sim_parser.add_argument("--exponent", type=float, default=config.EXPONENT_VALUE)
    sim_parser.set_defaults(func=cmd_simulate)

    replay_parser = sub.add_parser("replay", help="Replay a temperature fixture through the loop")
    replay_parser.add_argument("fixture", help="Path to replay JSON fixture")
    replay_parser.add_argument("--rate", type=float, default=1.0, help="Time acceleration factor")
    replay_parser.add_argument("--expect", help="Optional JSON file with expected IR command list")
    replay_parser.set_defaults(func=cmd_replay)

    dump_parser = sub.add_parser("dump-state", help="Print resolved configuration")
    dump_parser.set_defaults(func=cmd_dump_state)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
