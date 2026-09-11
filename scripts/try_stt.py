"""Run the voice engine on the console, without tray, window or overlay.

This is the fastest way to tell whether a recognition problem is in the audio
path or in the UI. Downloads the models on first run.

    uv run python scripts/try_stt.py
    uv run python scripts/try_stt.py --devices
    uv run python scripts/try_stt.py --device 3 --no-execute
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from okay_garmin import actions, config as config_module  # noqa: E402
from okay_garmin.engine import VoiceEngine  # noqa: E402
from okay_garmin.logging_setup import setup_logging  # noqa: E402
from okay_garmin.stt.audio import list_input_devices  # noqa: E402

BAR_WIDTH = 28


def print_devices() -> None:
    print("Input devices:")
    for device in list_input_devices():
        marker = " (default)" if device["default"] else ""
        print(f"  [{device['index']:>2}] {device['name']}{marker}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Okay-Garmin engine smoke test")
    parser.add_argument("--devices", action="store_true", help="list microphones and exit")
    parser.add_argument("--device", type=int, default=None, help="input device index")
    parser.add_argument("--meter", action="store_true", help="show a live level meter")
    parser.add_argument(
        "--no-execute",
        action="store_true",
        help="recognise only, never press keys or open files",
    )
    args = parser.parse_args()

    setup_logging(debug=True)

    if args.devices:
        print_devices()
        return 0

    config_module.load_config()
    if args.device is not None:
        cfg = config_module.get_config()
        cfg["input_device"] = args.device
        config_module.set_config(cfg)

    if args.no_execute:
        actions.execute = lambda command: print(  # type: ignore[assignment]
            f"    [dry run] would execute {command.get('type')} {command.get('value')!r}"
        ) or True

    engine = VoiceEngine()

    def on_event(event: dict) -> None:
        kind = event.get("type")
        if kind == "level":
            if args.meter:
                filled = int(event["level"] * BAR_WIDTH)
                bar = "#" * filled + "-" * (BAR_WIDTH - filled)
                sys.stdout.write(f"\r  [{bar}] {event['level']:.2f}")
                sys.stdout.flush()
        elif kind == "state":
            suffix = f"  {event.get('error', '')}".rstrip()
            print(f"\n>> {event['state']}{suffix}")
        elif kind == "wake":
            print("\n** wake word **")
        elif kind == "transcript":
            print(f'   heard: "{event.get("text", "")}"')
            print(f"   match: {event.get('matched')!r}  score={event.get('score')}")
        elif kind == "model_progress":
            print(f"\r   {event['stage']}: {event['progress'] * 100:5.1f}%  {event['message']}", end="")
        elif kind == "executed":
            print(f"   executed {event['command']!r}: {'ok' if event['ok'] else 'FAILED'}")

    engine.subscribe(on_event)

    cfg = config_module.get_config()
    print(f"Wake word : {cfg['wake_word']!r}")
    print(f"Language  : {cfg['stt']['language']}   Whisper: {cfg['stt']['whisper_model']}")
    print(f"Commands  : {[c['command'] for c in cfg['voice_commands']]}")
    print("Ctrl+C to stop.\n")

    engine.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping...")
        engine.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
