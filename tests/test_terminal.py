import os
import sys

import pexpect


def test_actual_terminal_quit_restores_screen_and_preserves_home(tmp_path):
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "XDG_DATA_HOME": str(tmp_path / "home/data"),
        "XDG_CONFIG_HOME": str(tmp_path / "home/config"),
        "TERM": "xterm-256color",
    }
    env.pop("CODEX_HOME", None)
    child = pexpect.spawn(
        sys.executable,
        ["-m", "codex_den"],
        env=env,
        encoding="utf-8",
        dimensions=(36, 110),
        timeout=15,
    )
    try:
        child.expect("No workspaces here yet")
        child.send("q")
        child.expect(pexpect.EOF)
        output = child.before
        child.close()
        assert child.exitstatus == 0
        assert "\x1b[?1049l" in output
        assert not (tmp_path / "home").exists()
    finally:
        if child.isalive():
            child.terminate(force=True)


def test_plain_terminal_menu_works_without_escape_codes_or_state(tmp_path):
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "XDG_DATA_HOME": str(tmp_path / "home/data"),
        "XDG_CONFIG_HOME": str(tmp_path / "home/config"),
        "NO_COLOR": "1",
    }
    env.pop("CODEX_HOME", None)
    child = pexpect.spawn(
        sys.executable, ["-m", "codex_den", "--plain"], env=env, encoding="utf-8", timeout=10
    )
    try:
        child.expect("Codex Den")
        child.expect("den>")
        child.sendline("q")
        child.expect(pexpect.EOF)
        child.close()
        assert child.exitstatus == 0
        assert not (tmp_path / "home").exists()
    finally:
        if child.isalive():
            child.terminate(force=True)


def test_real_terminal_settings_dropdown_escape_and_restoration(tmp_path):
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "XDG_DATA_HOME": str(tmp_path / "home/data"),
        "XDG_CONFIG_HOME": str(tmp_path / "home/config"),
        "TERM": "xterm-256color",
    }
    env.pop("CODEX_HOME", None)
    child = pexpect.spawn(
        sys.executable,
        ["-m", "codex_den"],
        env=env,
        encoding="utf-8",
        dimensions=(24, 80),
        timeout=30,
    )
    try:
        child.expect("No workspaces here yet")
        child.send("s")
        child.expect("Useful defaults first")
        child.send("\r")  # Expand the first settings picker.
        child.expect("User defaults")
        child.send("\x1b")
        # Tab moves within settings after closing only the picker.
        child.send("\t")
        child.send("\x1b")
        child.expect("No workspaces here yet")
        child.send("q")
        child.expect(pexpect.EOF)
        output = child.before
        child.close()
        assert child.exitstatus == 0
        assert "\x1b[?1049l" in output
        assert not (tmp_path / "home").exists()
    finally:
        if child.isalive():
            child.terminate(force=True)
