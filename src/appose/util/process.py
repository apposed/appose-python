# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Utility functions for working with processes.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Callable


def builder(
    working_dir: Path | str | None = None,
    env_vars: dict[str, str] | None = None,
    *command: str,
) -> subprocess.Popen:
    """
    Create a subprocess.Popen object with environment variables applied.

    Args:
        working_dir: Working directory for the process (can be None).
        env_vars: Environment variables to set (can be None or empty).
        command: Command and arguments to execute.

    Returns:
        Configured Popen object ready to start.
    """
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)

    cwd = str(working_dir) if working_dir else None

    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def run(
    cmd: list[str] | subprocess.Popen,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    output_consumer: Callable[[str], None] | None = None,
    error_consumer: Callable[[str], None] | None = None,
) -> int:
    """
    Run a process and captures stdout and stderr, reporting output to consumers.

    Args:
        cmd: Either a list of command arguments or an existing Popen object.
        cwd: Working directory for the command (only used if cmd is a list).
        env: Environment variables to set (only used if cmd is a list).
        output_consumer: Consumer of stdout content.
        error_consumer: Consumer of stderr content.

    Returns:
        Exit code of the process.

    Raises:
        IOError: If an I/O error occurs.
        InterruptedError: If interrupted while reading.
    """
    # Create process if needed
    if isinstance(cmd, list):
        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        working_dir = str(cwd) if cwd else None

        process = subprocess.Popen(
            cmd,
            cwd=working_dir,
            env=process_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    else:
        process = cmd

    main_thread = threading.current_thread()
    io_exception = [None]
    interrupted_exception = [None]

    def read_streams():
        try:
            _read_streams(process, main_thread, output_consumer, error_consumer)
        except IOError as e:
            io_exception[0] = e
        except InterruptedError as e:
            interrupted_exception[0] = e

    output_thread = threading.Thread(target=read_streams, daemon=True)
    output_thread.start()

    exit_code = process.wait()
    output_thread.join()

    if io_exception[0]:
        raise io_exception[0]
    if interrupted_exception[0]:
        raise interrupted_exception[0]

    return exit_code


def _read_streams(
    process: subprocess.Popen,
    main_thread: threading.Thread,
    output: Callable[[str], None] | None,
    error: Callable[[str], None] | None,
) -> None:
    """
    Read stdout and stderr streams from a process, reporting output to consumers.
    Uses separate threads to read each stream concurrently to avoid blocking.

    Args:
        process: The process to read streams from.
        main_thread: The main thread to monitor for interruption.
        output: Consumer of stdout content.
        error: Consumer of stderr content.

    Raises:
        IOError: If an I/O error occurs.
        InterruptedError: If interrupted while reading.
    """
    io_exceptions = []

    def read_stdout():
        try:
            _read_stream(process.stdout, output)
        except IOError as e:
            io_exceptions.append(e)

    def read_stderr():
        try:
            _read_stream(process.stderr, error)
        except IOError as e:
            io_exceptions.append(e)

    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)

    stdout_thread.start()
    stderr_thread.start()

    # Monitor for main thread death while process runs.
    while process.poll() is None and main_thread.is_alive():
        threading.Event().wait(0.05)

    # If main thread died, forcibly terminate the process.
    if process.poll() is None:
        process.kill()

    # Wait for stream reading threads to finish draining output.
    stdout_thread.join()
    stderr_thread.join()

    # Propagate any IOErrors from stream reading.
    if io_exceptions:
        primary = io_exceptions[0]
        for exc in io_exceptions[1:]:
            primary.__context__ = exc
        raise primary


def _read_stream(stream, consumer: Callable[[str], None] | None) -> None:
    """
    Read a single stream until EOF, reporting complete lines and any final partial line.

    Args:
        stream: The input stream to read.
        consumer: Consumer to receive the output.

    Raises:
        IOError: If an I/O error occurs.
    """
    if stream is None:
        return

    for line in stream:
        if consumer:
            consumer(line)
