# claude-usage-plz

Check your Claude Max/Pro usage limits from Linux. No browser, no macOS, no scraping.

```
$ claude-usage
Session (5h):        59% used  (resets 11pm (UTC))
Week (all):          33% used  (resets Apr 7, 3pm (UTC))
Week (Sonnet):       12% used  (resets Apr 7, 5pm (UTC))
```

## Why

There is no API to check Claude usage programmatically ([anthropics/claude-code#9617](https://github.com/anthropics/claude-code/issues/9617)). The `/usage` slash command only works inside interactive sessions. Every existing tool is either macOS-only (menu bar apps) or uses private APIs that break.

This tool runs `/usage` inside a virtual terminal, reads the screen, and parses the output. It works anywhere Claude Code runs.

## Install

```bash
pip install claude-usage-plz
```

Requires Claude Code to be installed via npm and logged in:

```bash
# Install Node.js if needed, then:
npm install -g @anthropic-ai/claude-code
```

> **Note:** On Linux, you must install Claude Code via npm (`npm install -g @anthropic-ai/claude-code`). The VS Code extension bundles its own binary, but it is not on PATH and cannot be relied upon for programmatic use.

## CLI

```bash
# Default (~/.claude)
claude-usage

# Specific profile
claude-usage --claude-dir ~/.claude-work

# JSON output (for scripts)
claude-usage --json
```

```json
{
  "five_hour_pct": 59.0,
  "five_hour_resets": "11pm (UTC)",
  "seven_day_pct": 33.0,
  "seven_day_resets": "Apr 7, 3pm (UTC)",
  "sonnet_week_pct": 12.0,
  "sonnet_week_resets": "Apr 7, 5pm (UTC)"
}
```

## Python API

```python
from claude_usage import get_usage

# Default account
usage = get_usage()
print(f"5h: {usage.five_hour_pct}%, 7d: {usage.seven_day_pct}%")

# Specific account
usage = get_usage("/home/me/.claude-work")

# All fields
usage.five_hour_pct       # float | None
usage.five_hour_resets    # str | None  (e.g. "11pm (UTC)")
usage.seven_day_pct       # float | None
usage.seven_day_resets    # str | None
usage.sonnet_week_pct     # float | None
usage.sonnet_week_resets  # str | None

# As dict/JSON
usage.to_dict()
```

## How it works

1. Spawns `claude --dangerously-skip-permissions` in a virtual PTY ([pexpect](https://pypi.org/project/pexpect/))
2. Accepts the bypass-permissions prompt
3. Sends `/usage` + Enter
4. Reads the rendered TUI screen via [pyte](https://pypi.org/project/pyte/) (terminal emulator)
5. Parses percentages with regex
6. Exits the session

Takes ~15-20 seconds per call. The claude process is closed after each probe.

## Multi-account usage

Pass `--claude-dir` (CLI) or the `claude_dir` argument (Python) to check different accounts:

```python
from claude_usage import get_usage

work = get_usage("/home/me/.claude-profiles/work/.claude")
personal = get_usage("/home/me/.claude-profiles/personal/.claude")

print(f"Work: {work.five_hour_pct}% | Personal: {personal.five_hour_pct}%")
```

## Limitations

- **Linux only** (uses PTY via pexpect; macOS may work but untested)
- **~15-20s per call** (spawns a full claude session)
- **Depends on TUI layout** (may break if Anthropic changes `/usage` output)
- Requires `--dangerously-skip-permissions` (only runs `/usage` and `/exit`)

## License

MIT
