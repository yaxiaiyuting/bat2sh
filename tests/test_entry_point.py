"""统一入口参数路由的回归测试（v1.6.0 阶段 A / Stage 3.5）。"""

from __future__ import annotations

import json
from pathlib import Path

from bat2sh.__main__ import main as entry_main

CLEAN_BAT = "@echo off\necho hello\n"


def make_bat(tmp_path: Path) -> Path:
    path = tmp_path / "demo.bat"
    path.write_text(CLEAN_BAT, encoding="utf-8")
    return path


def test_print_without_cli_routes_to_cli(tmp_path, capsys):
    path = make_bat(tmp_path)
    code = entry_main([str(path), "--print"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("#!/usr/bin/env bash\n")
    assert 'echo "hello"' in out


def test_report_json_without_cli_routes_to_cli(tmp_path, capsys):
    path = make_bat(tmp_path)
    code = entry_main([str(path), "--print", "--report-json"])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.err)
    assert payload["kind"] == "bat"


def test_output_flag_without_cli_routes_to_cli(tmp_path, capsys):
    path = make_bat(tmp_path)
    out_path = tmp_path / "out.sh"
    code = entry_main([str(path), "-o", str(out_path)])
    assert code == 0
    assert out_path.exists()


def test_equals_form_flag_routes_to_cli(tmp_path):
    path = make_bat(tmp_path)
    outdir = tmp_path / "out"
    outdir.mkdir()
    code = entry_main([str(path), "--outdir=" + str(outdir)])
    assert code == 0
    assert (outdir / "demo.sh").exists()


def test_explicit_cli_flag_unchanged(tmp_path, capsys):
    path = make_bat(tmp_path)
    code = entry_main(["--cli", str(path), "--print"])
    assert code == 0
    assert 'echo "hello"' in capsys.readouterr().out


def test_no_args_launches_gui(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_gui(argv):
        calls.append(list(argv))
        return 0

    monkeypatch.setattr("bat2sh.gui.app.run_gui", fake_run_gui)
    assert entry_main([]) == 0
    assert len(calls) == 1


def test_positional_input_launches_gui(tmp_path, monkeypatch):
    path = make_bat(tmp_path)
    calls: list[list[str]] = []

    def fake_run_gui(argv):
        calls.append(list(argv))
        return 0

    monkeypatch.setattr("bat2sh.gui.app.run_gui", fake_run_gui)
    assert entry_main([str(path)]) == 0
    assert len(calls) == 1
    assert str(path) in calls[0]
