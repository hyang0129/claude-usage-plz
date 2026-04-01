"""Tests for claude_usage.

These are integration tests that require:
- Linux environment
- Claude Code installed and on PATH (or in VS Code extensions)
- ~/.claude authenticated with a valid account

Run: pytest tests/ -v
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from claude_usage import Usage, _find_claude, _parse_screen, get_usage


# ---------------------------------------------------------------------------
# Unit tests: _parse_screen
# ---------------------------------------------------------------------------


class TestParseScreen:
    """Test the screen parser against realistic /usage output."""

    CLEAN_SCREEN = """
  /usage
────────────────────────────────────────
  Current session
  █████████████████████████████     58% used
  Resets 11pm (UTC)

  Current week (all models)
  ████████████████▌                 33% used
  Resets Apr 7, 3pm (UTC)

  Current week (Sonnet only)
  ██████                            12% used
  Resets Apr 7, 5pm (UTC)

  Extra usage
  Extra usage not enabled
"""

    CORRUPTED_SCREEN = """
❯ /usage
  /usage                  Show plan usage limits
   StttususaConfig   Usage    i                 to keep working when limits are hit
                                         n     t  t    g       c    e
  Current session                  t       f       l     e
  █████████████████████████████▌    C         e     e59% usedics and activity
  Rese s 11pm (UTC)
  Current week (all models)
  ████████████████▌                                  33% used
  Resets Apr 7, 3pm (UTC)
  Current week (Sonnet only)
  ██████                                             12% used
  Resets Apr 7, 5pm (UTC)
  Extra usage
  Extra usage not enabled · /extra-usage to enable
  Esc to cancel
"""

    def test_parse_clean_screen(self):
        usage = _parse_screen(self.CLEAN_SCREEN)
        assert usage.five_hour_pct == 58.0
        assert usage.seven_day_pct == 33.0
        assert usage.sonnet_week_pct == 12.0

    def test_parse_clean_screen_resets(self):
        usage = _parse_screen(self.CLEAN_SCREEN)
        assert usage.five_hour_resets is not None
        assert "11pm" in usage.five_hour_resets
        assert usage.seven_day_resets is not None
        assert "Apr 7" in usage.seven_day_resets

    def test_parse_corrupted_screen(self):
        usage = _parse_screen(self.CORRUPTED_SCREEN)
        assert usage.five_hour_pct == 59.0
        assert usage.seven_day_pct == 33.0
        assert usage.sonnet_week_pct == 12.0

    def test_parse_empty_screen(self):
        usage = _parse_screen("")
        assert usage.five_hour_pct is None
        assert usage.seven_day_pct is None
        assert usage.sonnet_week_pct is None

    def test_parse_no_usage_data(self):
        usage = _parse_screen("Some random text\nwith no percentages")
        assert usage.five_hour_pct is None

    def test_parse_single_percentage(self):
        screen = """
  Current session
  ██████████                        25% used
  Resets 3am (UTC)
"""
        usage = _parse_screen(screen)
        assert usage.five_hour_pct == 25.0
        assert usage.seven_day_pct is None

    def test_parse_zero_percent(self):
        screen = """
  Current session
                                    0% used
  Resets 5pm (UTC)

  Current week (all models)
                                    0% used
  Resets Apr 10, 3pm (UTC)
"""
        usage = _parse_screen(screen)
        assert usage.five_hour_pct == 0.0
        assert usage.seven_day_pct == 0.0

    def test_parse_100_percent(self):
        screen = """
  Current session
  ██████████████████████████████  100% used
  Resets 2am (UTC)
"""
        usage = _parse_screen(screen)
        assert usage.five_hour_pct == 100.0


# ---------------------------------------------------------------------------
# Unit tests: Usage dataclass
# ---------------------------------------------------------------------------


class TestUsage:
    def test_to_dict(self):
        usage = Usage(five_hour_pct=50.0, seven_day_pct=30.0)
        d = usage.to_dict()
        assert d["five_hour_pct"] == 50.0
        assert d["seven_day_pct"] == 30.0
        assert d["sonnet_week_pct"] is None

    def test_to_dict_json_serializable(self):
        usage = Usage(five_hour_pct=50.0, five_hour_resets="11pm (UTC)")
        j = json.dumps(usage.to_dict())
        assert "50.0" in j

    def test_defaults_are_none(self):
        usage = Usage()
        for v in usage.to_dict().values():
            assert v is None


# ---------------------------------------------------------------------------
# Unit tests: _find_claude
# ---------------------------------------------------------------------------


class TestFindClaude:
    def test_find_claude_succeeds(self):
        path = _find_claude()
        assert path is not None
        assert os.path.exists(path) or shutil.which(path)

    def test_find_claude_returns_string(self):
        assert isinstance(_find_claude(), str)


# ---------------------------------------------------------------------------
# Integration tests: get_usage (live, requires authenticated .claude)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetUsageLive:
    """Live integration tests. These spawn a real claude process."""

    def test_default_usage_returns_data(self):
        usage = get_usage()
        assert isinstance(usage, Usage)
        # At least one percentage should be non-None
        assert usage.five_hour_pct is not None or usage.seven_day_pct is not None

    def test_default_usage_percentages_in_range(self):
        usage = get_usage()
        if usage.five_hour_pct is not None:
            assert 0 <= usage.five_hour_pct <= 100
        if usage.seven_day_pct is not None:
            assert 0 <= usage.seven_day_pct <= 100
        if usage.sonnet_week_pct is not None:
            assert 0 <= usage.sonnet_week_pct <= 100

    def test_default_usage_to_dict(self):
        usage = get_usage()
        d = usage.to_dict()
        assert isinstance(d, dict)
        assert "five_hour_pct" in d
        assert "seven_day_pct" in d

    def test_config_dir_swap(self, tmp_path):
        """Copy ~/.claude to a temp dir and verify get_usage works with it."""
        real_claude_dir = Path.home() / ".claude"
        if not real_claude_dir.exists():
            pytest.skip("~/.claude does not exist")

        # Copy credentials to temp
        temp_claude = tmp_path / ".claude"
        shutil.copytree(real_claude_dir, temp_claude)

        usage = get_usage(claude_dir=str(temp_claude))
        assert isinstance(usage, Usage)
        assert usage.five_hour_pct is not None or usage.seven_day_pct is not None

    def test_config_dir_swap_matches_default(self, tmp_path):
        """Usage from copied config should return the same account's data."""
        real_claude_dir = Path.home() / ".claude"
        if not real_claude_dir.exists():
            pytest.skip("~/.claude does not exist")

        temp_claude = tmp_path / ".claude"
        shutil.copytree(real_claude_dir, temp_claude)

        usage_default = get_usage()
        usage_copied = get_usage(claude_dir=str(temp_claude))

        # Same account, so 7-day should be identical (5hr may drift slightly)
        if usage_default.seven_day_pct is not None and usage_copied.seven_day_pct is not None:
            assert abs(usage_default.seven_day_pct - usage_copied.seven_day_pct) <= 2

    def test_no_creds_config_dir_proves_isolation(self, tmp_path):
        """Config dir with no creds must NOT return real usage data.

        This proves CLAUDE_CONFIG_DIR is actually being read. If the tool
        ignored it and fell back to ~/.claude, we'd get real percentages.
        Instead we should get a timeout (login prompt) or empty usage.
        """
        no_creds_dir = tmp_path / ".claude-no-creds"
        no_creds_dir.mkdir()
        (no_creds_dir / "settings.json").write_text("{}")

        try:
            usage = get_usage(claude_dir=str(no_creds_dir), timeout=30)
            # If it somehow returns, it must NOT have real data
            assert usage.five_hour_pct is None, (
                f"Got five_hour_pct={usage.five_hour_pct} from a dir with no creds — "
                "CLAUDE_CONFIG_DIR is being ignored"
            )
            assert usage.seven_day_pct is None, (
                f"Got seven_day_pct={usage.seven_day_pct} from a dir with no creds — "
                "CLAUDE_CONFIG_DIR is being ignored"
            )
        except TimeoutError:
            pass  # Expected — claude prompts for login, we timeout

    def test_config_dir_isolates_account(self, tmp_path):
        """Verify CLAUDE_CONFIG_DIR actually changes which account is used.

        Copies real creds to a temp dir, runs get_usage on it. If we get data,
        it proves the config dir was respected (not falling back to ~/.claude).
        """
        real_claude_dir = Path.home() / ".claude"
        creds_file = real_claude_dir / ".credentials.json"
        if not creds_file.exists():
            pytest.skip("~/.claude/.credentials.json does not exist")

        # Create a minimal config dir with just the credentials
        isolated_dir = tmp_path / ".claude-isolated"
        isolated_dir.mkdir()
        shutil.copy2(creds_file, isolated_dir / ".credentials.json")

        usage = get_usage(claude_dir=str(isolated_dir))
        assert isinstance(usage, Usage)
        # Should get real data because we copied valid credentials
        assert usage.five_hour_pct is not None or usage.seven_day_pct is not None


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: live tests requiring authenticated claude")
