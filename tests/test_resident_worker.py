# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for LazyEnvironment and ResidentWorker.
"""

from __future__ import annotations

from appose import BuildListener, LazyEnvironment, ResidentWorker
from appose.builder import SimpleBuilder

PID = "import os\ntask.outputs['pid'] = os.getpid()"


def test_workers_share_environment(tmp_path):
    env = LazyEnvironment(
        "test-resident", SimpleBuilder().base(tmp_path).append_system_path()
    )
    builds = []
    failures = []

    class Listener(BuildListener):
        def build_started(self, env_name):
            builds.append(env_name)

        def build_finished(self, env_name, error):
            failures.append(error)

    env.add_build_listener(Listener())

    with (
        ResidentWorker(env, lambda e: e.python()) as a,
        ResidentWorker(env, lambda e: e.python()) as b,
    ):
        pid_a = pid(a)
        pid_b = pid(b)
        assert builds == ["test-resident"]
        assert failures == [None]
        assert pid_a != pid_b

        # Each worker stays resident across tasks.
        assert pid_a == pid(a)

        # A killed worker is replaced on its next task.
        a.kill()
        assert pid_a != pid(a)
        assert len(builds) == 1


def pid(worker: ResidentWorker) -> int:
    return int(worker.task(PID).wait_for().outputs["pid"])
