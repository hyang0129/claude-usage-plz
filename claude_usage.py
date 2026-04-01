"""Check Claude Max/Pro usage limits programmatically on Linux.

Works by running the `/usage` command inside an interactive Claude Code
session via a virtual terminal (pexpect + pyte). This is the only reliable
method — there is no public API endpoint for usage data.

Usage as a library:
    from claude_usage import get_usage
    usage = get_usage()                             # default ~/.claude
    usage = get_usage("/home/me/.claude-work")      # specific profile

Usage as a CLI:
    claude-usage                                    # default
    claude-usage --claude-dir ~/.claude-work        # specific profile
    claude-usage --json                             # JSON output
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from typing import Optional

import pexpect
import pyte


@dataclass
class Usage:
    five_hour_pct: Optional[float] = None
    five_hour_resets: Optional[str] = None
    seven_day_pct: Optional[float] = None
    seven_day_resets: Optional[str] = None
    sonnet_week_pct: Optional[float] = None
    sonnet_week_resets: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _find_claude() -> str:
    """Find the claude binary in PATH or VS Code extensions."""
    if shutil.which("claude"):
        return "claude"
    for pattern in [
        os.path.expanduser("~/.vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
        os.path.expanduser("~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
    ]:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    raise FileNotFoundError(
        "claude not found. Install Claude Code or add it to PATH."
    )


def _parse_screen(text: str) -> Usage:
    """Extract usage percentages from the /usage screen output."""
    usage = Usage()
    lines = text.split("\n")

    for i, line in enumerate(lines):
        m = re.search(r"(\d+)%\s*used", line)
        if not m:
            continue
        pct = float(m.group(1))

        # Look backward for context
        ctx = " ".join(lines[max(0, i - 3):i]).lower()

        # Look forward for reset time
        resets = None
        for j in range(i, min(len(lines), i + 3)):
            rm = re.search(r"[Rr]eset[s ]+(.*?)$", lines[j])
            if rm:
                resets = rm.group(1).strip()
                break

        if "session" in ctx and usage.five_hour_pct is None:
            usage.five_hour_pct = pct
            usage.five_hour_resets = resets
        elif "sonnet" in ctx:
            usage.sonnet_week_pct = pct
            usage.sonnet_week_resets = resets
        elif "week" in ctx and usage.seven_day_pct is None:
            usage.seven_day_pct = pct
            usage.seven_day_resets = resets

    return usage


def get_usage(claude_dir: Optional[str] = None, timeout: int = 60) -> Usage:
    """Get current Claude usage by running /usage in a virtual terminal.

    Args:
        claude_dir: Path to the .claude config directory. Defaults to
                    ~/.claude (the standard location). Pass a different
                    path to check a specific profile/account.
        timeout:    Max seconds to wait for claude to start and respond.

    Returns:
        A Usage dataclass with the parsed percentages and reset times.
    """
    claude_bin = _find_claude()

    env = os.environ.copy()
    if claude_dir:
        env["CLAUDE_CONFIG_DIR"] = str(claude_dir)

    screen = pyte.Screen(120, 40)
    stream = pyte.Stream(screen)

    child = pexpect.spawn(
        claude_bin,
        args=["--dangerously-skip-permissions"],
        encoding="utf-8",
        timeout=timeout,
        dimensions=(40, 120),
        env=env,
    )

    def feed():
        try:
            data = child.read_nonblocking(size=4096, timeout=1)
            stream.feed(data)
        except (pexpect.TIMEOUT, pexpect.EOF):
            pass

    def text():
        return "\n".join(screen.display[i].rstrip() for i in range(screen.lines))

    try:
        # Wait for claude to be ready (bypass prompt or direct to input)
        deadline = time.time() + timeout
        accepted = False
        at_prompt = False

        while time.time() < deadline:
            feed()
            t = text()

            # Check if we're already at the prompt (no bypass dialog)
            if not accepted and not at_prompt:
                if "\u276f" in t or "\u2771" in t or "bypass permissions" in t.lower():
                    at_prompt = True
                    break

            # Handle bypass-permissions prompt if it appears
            if ("Yes, I accept" in t or "No, exit" in t) and not accepted:
                child.send("\x1b[B")  # down arrow
                time.sleep(0.3)
                child.send("\r")
                accepted = True
                time.sleep(3)
                continue

            if accepted and not at_prompt:
                if "\u276f" in t or "bypass permissions" in t.lower():
                    at_prompt = True
                    break

            time.sleep(0.5)

        if not at_prompt:
            raise TimeoutError("Timed out waiting for claude prompt")

        feed()

        # Send /usage
        screen.reset()
        for ch in "/usage":
            child.send(ch)
            time.sleep(0.05)
        time.sleep(1)
        feed()
        child.send("\r")

        # Wait for results
        for _ in range(timeout):
            time.sleep(1)
            feed()
            t = text()
            if "%" in t and "used" in t:
                # Give it a moment to finish rendering
                time.sleep(1)
                feed()
                break

        result = _parse_screen(text())

        # Exit
        child.send("\x1b")
        time.sleep(0.3)
        child.sendline("/exit")
        time.sleep(0.5)

        return result

    finally:
        try:
            child.close(force=True)
        except Exception:
            pass


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Check Claude Max/Pro usage limits"
    )
    parser.add_argument(
        "--claude-dir",
        help="Path to .claude config directory (default: ~/.claude)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Output as JSON",
    )
    args = parser.parse_args()

    try:
        usage = get_usage(claude_dir=args.claude_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except TimeoutError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.as_json:
        print(json.dumps(usage.to_dict(), indent=2))
    else:
        if usage.five_hour_pct is not None:
            print(f"Session (5h):     {usage.five_hour_pct:>5.0f}% used", end="")
            if usage.five_hour_resets:
                print(f"  (resets {usage.five_hour_resets})", end="")
            print()
        if usage.seven_day_pct is not None:
            print(f"Week (all):       {usage.seven_day_pct:>5.0f}% used", end="")
            if usage.seven_day_resets:
                print(f"  (resets {usage.seven_day_resets})", end="")
            print()
        if usage.sonnet_week_pct is not None:
            print(f"Week (Sonnet):    {usage.sonnet_week_pct:>5.0f}% used", end="")
            if usage.sonnet_week_resets:
                print(f"  (resets {usage.sonnet_week_resets})", end="")
            print()
        if usage.five_hour_pct is None and usage.seven_day_pct is None:
            print("No usage data found. Is Claude Code installed and logged in?")
            sys.exit(1)


if __name__ == "__main__":
    main()
