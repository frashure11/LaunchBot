"""Launches configured scripts as detached background processes and keeps
track of which ones are currently running.

Tracking is in-memory only: if the bot process restarts, it forgets about
anything it previously launched (the launched processes themselves keep
running fine, since they're detached into their own session — the bot just
loses the ability to see/stop them until they're re-launched or the OS
process table is consulted some other way). Good enough for v1.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("launchbot.process")


@dataclass
class RunningProcess:
    name: str
    pid: int
    started_at: float
    log_path: Path
    process: subprocess.Popen


class ProcessManager:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._running: dict[str, RunningProcess] = {}

    def is_running(self, name: str) -> bool:
        return self.status(name) is not None

    def status(self, name: str) -> RunningProcess | None:
        proc = self._running.get(name)
        if proc is None:
            return None
        if proc.process.poll() is not None:
            # It finished since we last checked; stop tracking it.
            del self._running[name]
            return None
        return proc

    def launch(self, name: str, command: list[str], cwd: str | None = None) -> RunningProcess:
        if self.is_running(name):
            existing = self._running[name]
            raise RuntimeError(f"{name} is already running (PID {existing.pid})")

        script_path = Path(command[0])
        if not script_path.exists():
            raise RuntimeError(f"script not found: {script_path}")
        if not os.access(script_path, os.X_OK):
            raise RuntimeError(f"script is not executable: {script_path} (run: chmod +x {script_path})")

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        log_path = self.log_dir / f"{name}-{timestamp}.log"

        with log_path.open("wb") as log_file:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # detach into its own session so it survives bot restarts
            )

        running = RunningProcess(
            name=name,
            pid=process.pid,
            started_at=time.time(),
            log_path=log_path,
            process=process,
        )
        self._running[name] = running
        logger.info("Launched %s (PID %s): %s", name, process.pid, command)
        return running

    def stop(self, name: str, timeout: float = 10.0) -> bool:
        """Send SIGTERM (then SIGKILL if needed) to a tracked process group.

        Only meaningful for scripts without a dedicated `stop` script defined
        in commands.yaml — those are handled by launching the stop script
        instead (see bot.py).
        """
        proc = self.status(name)
        if proc is None:
            return False

        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            del self._running[name]
            return False

        try:
            proc.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("%s (PID %s) didn't stop after SIGTERM, sending SIGKILL", name, proc.pid)
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.process.wait(timeout=5)

        del self._running[name]
        logger.info("Stopped %s", name)
        return True
