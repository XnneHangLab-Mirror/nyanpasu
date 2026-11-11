from __future__ import annotations

import asyncio
import json
import os
import subprocess

import pytest

from nyanpasu.safe_files import open_regular_file
from tests.test_control_tools import agent as agent, record_root

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows native filesystem and PowerShell")


@pytest.mark.parametrize("relative", ["C:note", "\\note", "note:stream", "note.", "note "])
def test_windows_reader_rejects_path_aliases(tmp_path, relative):
    with pytest.raises(ValueError):
        with open_regular_file(tmp_path, relative):
            pytest.fail("accepted an alias")


def test_windows_reader_pins_directories_and_file_until_close(tmp_path):
    root = tmp_path / "root"
    folder = root / "nested"
    folder.mkdir(parents=True)
    target = folder / "note"
    target.write_text("allowed")
    with open_regular_file(root, "nested/note") as stream:
        for path in (root, folder, target):
            with pytest.raises(OSError):
                path.rename(path.with_name(path.name + "-moved"))
        assert stream.read() == b"allowed"
    target.rename(folder / "moved")
    folder.rename(root / "moved")


@pytest.mark.parametrize("at_root", [False, True])
def test_windows_reader_rejects_junctions(tmp_path, at_root):
    private = tmp_path / "private"
    private.mkdir()
    (private / "note").write_text("secret")
    root = tmp_path / "root"
    link = root if at_root else root / "nested"
    if not at_root:
        root.mkdir()
    subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(private)], check=True, capture_output=True)
    try:
        with pytest.raises(OSError, match="reparse"):
            with open_regular_file(root, "note" if at_root else "nested/note"):
                pytest.fail("followed a junction")
    finally:
        link.rmdir()


def test_windows_reader_preserves_missing_file_exception(tmp_path):
    with pytest.raises(FileNotFoundError):
        with open_regular_file(tmp_path, "missing"):
            pytest.fail("opened missing file")


@pytest.mark.anyio
async def test_windows_control_command_runs_in_powershell(agent):
    task = record_root(agent, "powershell-root")
    try:
        async with agent.control.turn(task.task_id) as control:
            command = next(line for line in control.prompt.splitlines() if line.startswith("Pipe a JSON"))
            command = command.split("request to: ", 1)[1]
            proc = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                '\'{"action":"inspect"}\' | ' + command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            output, error = await asyncio.wait_for(proc.communicate(), 15)
            assert proc.returncode == 0, error.decode(errors="replace")
            assert json.loads(output) == []
    finally:
        agent.store.mark_task_failed(task.task_id, "test finished")
