# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

import appose
from appose.service import TaskStatus

ndarray_inspect = """
task.outputs["rsize"] = data.shm.rsize
task.outputs["size"] = data.shm.size
task.outputs["dtype"] = data.dtype
task.outputs["shape"] = data.shape
task.outputs["sum"] = sum(v for v in data.shm.buf)
"""


def test_ndarray():
    env = appose.system()
    with env.python() as service:
        with appose.SharedMemory(create=True, rsize=2 * 2 * 20 * 25) as shm:
            # Construct the data.
            shm.buf[0] = 123
            shm.buf[456] = 78
            shm.buf[1999] = 210
            data = appose.NDArray("uint16", [2, 20, 25], shm)

            # Run the task.
            task = service.task(ndarray_inspect, {"data": data})
            task.wait_for()

            # Validate the execution result.
            assert TaskStatus.COMPLETE == task.status
            # The requested size is 2*20*25*2=2000, but actual allocated
            # shm size varies by platform; e.g. on macOS it is 16384.
            assert 2 * 20 * 25 * 2 == task.outputs["rsize"]
            assert task.outputs["size"] >= task.outputs["rsize"]
            assert "uint16" == task.outputs["dtype"]
            assert [2, 20, 25] == task.outputs["shape"]
            assert 123 + 78 + 210 == task.outputs["sum"]
