"""Check that every translation key is defined, used, and present in all languages.

A missing key renders as the raw key in the interface, which is easy to ship by
accident. Run this after touching the UI.

    uv run python scripts/check_i18n.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

# Keys built at runtime from a prefix plus a value, so they never appear
# literally in the markup or the scripts.
DYNAMIC_PREFIXES = (
    "state.",
    "type.",
    "ph.",
    "pos.",
    "media.",
    "spotify.",
)


def load_bundles() -> dict[str, dict]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((WEB / "i18n").glob("*.json"))
    }


def used_keys() -> set[str]:
    keys: set[str] = set()

    # Anything shaped like a key, so helpers that take one as a plain argument
    # (field("commands.phrase", ...)) count as a use too.
    key_shape = re.compile(r'"([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)"')

    for path in WEB.glob("*.html"):
        if path.name.startswith("_"):
            continue  # generated preview files
        html = path.read_text(encoding="utf-8")
        keys |= set(re.findall(r'data-i18n(?:-ph|-title)?="([^"]+)"', html))

    for path in (WEB / "js").glob("*.js"):
        source = path.read_text(encoding="utf-8")
        keys |= set(key_shape.findall(source))

    for path in (ROOT / "src").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        keys |= set(re.findall(r'strings\.get\(\s*f?"([^"{]+)"', source))

    return keys


def main() -> int:
    bundles = load_bundles()
    if not bundles:
        print("No translation bundles found", file=sys.stderr)
        return 1

    languages = sorted(bundles)
    reference = set(bundles[languages[0]])
    problems = 0

    # 1. every language defines the same keys
    for language in languages[1:]:
        missing = reference - set(bundles[language])
        extra = set(bundles[language]) - reference
        if missing:
            problems += 1
            print(f"{language}.json is missing: {sorted(missing)}")
        if extra:
            problems += 1
            print(f"{language}.json has extra keys: {sorted(extra)}")

    # 2. every key the UI asks for is defined
    used = used_keys()
    undefined = {
        key
        for key in used
        if key not in reference and not any(key.startswith(p) for p in DYNAMIC_PREFIXES)
    }
    if undefined:
        problems += 1
        print(f"Used but not defined: {sorted(undefined)}")

    # 3. anything defined and never referenced is dead weight
    unused = {
        key
        for key in reference
        if key not in used and not any(key.startswith(p) for p in DYNAMIC_PREFIXES)
    }
    if unused:
        print(f"Defined but unused (harmless): {sorted(unused)}")

    if problems:
        print(f"\n{problems} problem(s) found")
        return 1

    print(f"OK -- {len(reference)} keys across {', '.join(languages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
