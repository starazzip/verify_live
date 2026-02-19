"""外部程序執行器（支援即時寫入 log 與取消）。"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class ProcessRunResult:
    exit_code: int
    cancelled: bool = False


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        time.sleep(0.2)
        if proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run_command_with_live_log(
    *,
    cmd: list[str],
    cwd: Path,
    log_path: Path,
    should_cancel: Optional[Callable[[], bool]] = None,
    poll_interval_sec: float = 0.25,
    append: bool = False,
) -> ProcessRunResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    popen_kwargs = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["preexec_fn"] = os.setsid

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        bufsize=1,
        **popen_kwargs,
    )

    mode = "a" if append else "w"
    with log_path.open(mode, encoding="utf-8") as logfile:
        def _reader() -> None:
            if proc.stdout is None:
                return
            for line in iter(proc.stdout.readline, ""):
                if line == "":
                    break
                logfile.write(line)
                logfile.flush()

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()

        cancelled = False
        while proc.poll() is None:
            if should_cancel and should_cancel():
                cancelled = True
                _terminate_process_tree(proc)
                break
            time.sleep(poll_interval_sec)

        try:
            proc.wait(timeout=8)
        except Exception:
            _terminate_process_tree(proc)
            try:
                proc.wait(timeout=3)
            except Exception:
                pass

        if proc.stdout is not None:
            try:
                proc.stdout.close()
            except Exception:
                pass
        reader.join(timeout=2)

    exit_code = proc.returncode if proc.returncode is not None else (130 if cancelled else -1)
    return ProcessRunResult(exit_code=exit_code, cancelled=cancelled)
