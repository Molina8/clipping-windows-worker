"""Utilidades para ejecutar subprocesos de forma segura.

Proporciona helpers para ejecutar comandos (FFmpeg, FFprobe, etc.)
capturando stdout/stderr y con timeout.
"""

from __future__ import annotations

import asyncio
import shlex
import subprocess
from typing import Sequence

from app.utils.logging import get_logger

logger = get_logger("subprocess")


class CommandError(RuntimeError):
    """Se lanza cuando un comando termina con código de salida != 0."""

    def __init__(self, command: Sequence[str], returncode: int, stderr: str) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"Command failed ({returncode}): {shlex.join(self.command)}\n{stderr}"
        )


def run_command(
    command: Sequence[str],
    *,
    timeout: float | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Ejecuta un comando de forma síncrona y lanza CommandError si falla."""
    logger.debug("running command", command=shlex.join(command))
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandError(command, -1, f"Command timed out after {timeout}s") from exc

    if result.returncode != 0:
        raise CommandError(command, result.returncode, result.stderr)

    return result


async def run_command_async(
    command: Sequence[str],
    *,
    timeout: float | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Ejecuta un comando de forma asíncrona y lanza CommandError si falla."""
    logger.debug("running command (async)", command=shlex.join(command))
    try:
        process = await asyncio.create_subprocess_exec(
            *list(command),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise CommandError(command, -1, f"Command timed out after {timeout}s") from exc

    stdout_text = stdout.decode("utf-8", errors="replace")
    stderr_text = stderr.decode("utf-8", errors="replace")

    if process.returncode != 0:
        raise CommandError(command, process.returncode, stderr_text)

    return subprocess.CompletedProcess(
        args=list(command),
        returncode=process.returncode,
        stdout=stdout_text,
        stderr=stderr_text,
    )
