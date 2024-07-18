###
# #%L
# Appose: multi-language interprocess cooperation with shared memory.
# %%
# Copyright (C) 2023 Appose developers.
# %%
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# #L%
###

import appose
from appose.service import TaskStatus

ndarray_inspect = """
task.outputs["size"] = data.shm.size
task.outputs["dtype"] = data.dtype
task.outputs["shape"] = data.shape
task.outputs["sum"] = sum(v for v in data.shm.buf)
"""


def test_ndarray():
    env = appose.system()
    with env.python() as service:
        # Construct the data.
        shm = appose.SharedMemory(create=True, size=2 * 2 * 20 * 25)
        shm.buf[0] = 123
        shm.buf[456] = 78
        shm.buf[1999] = 210
        data = appose.NDArray("uint16", [2, 20, 25], shm)

        # Run the task.
        task = service.task(ndarray_inspect, {"data": data})
        task.wait_for()

        # Validate the execution result.
        assert TaskStatus.COMPLETE == task.status
        assert 2 * 20 * 25 * 2 == task.outputs["size"]
        assert "uint16" == task.outputs["dtype"]
        assert [2, 20, 25] == task.outputs["shape"]
        assert 123 + 78 + 210 == task.outputs["sum"]

        # Clean up.
        shm.unlink()
