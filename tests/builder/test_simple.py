###
# #%L
# Appose: multi-language interprocess cooperation with shared memory.
# %%
# Copyright (C) 2023 - 2025 Appose developers.
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

"""End-to-end tests for SimpleBuilder."""

import os
import shutil
from pathlib import Path


from appose.builder import SimpleBuilder

from tests.test_base import assert_complete, maybe_debug


def test_custom():
    """
    Tests fluent chaining from base Builder methods to SimpleBuilder methods.
    This verifies that the recursive generics enable natural method chaining.
    """
    env = (
        SimpleBuilder()
        .env(CUSTOM_VAR="test_value")  # Base Builder method
        .inherit_running_java()  # SimpleBuilder method
        .append_system_path()  # SimpleBuilder method
        .build()
    )

    assert env is not None
    assert env.bin_paths() is not None
    assert len(env.bin_paths()) > 0, (
        "Custom environment should have binary paths configured"
    )
    assert len(env.launch_args()) == 0, (
        "Custom environment should have no special launcher"
    )

    # Verify environment variables are propagated
    assert env.env_vars() is not None
    assert env.env_vars().get("CUSTOM_VAR") == "test_value"

    # Verify inherit_running_java() sets JAVA_HOME if it exists
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        assert env.env_vars().get("JAVA_HOME") == java_home
        # Verify Java bin directory is in bin_paths
        java_bin = str(Path(java_home) / "bin")
        assert java_bin in env.bin_paths(), "Java bin directory should be in bin_paths"

    # Verify that the custom environment can execute Python tasks
    with env.python() as service:
        maybe_debug(service)
        task = service.task("2 + 2")
        task.wait_for()
        assert_complete(task)
        result = task.outputs.get("result")
        assert result == 4

    # Test custom environment with specific base directory
    custom_dir = Path("target/test-custom")
    custom_dir.mkdir(parents=True, exist_ok=True)
    try:
        custom_env = SimpleBuilder().base(custom_dir).append_system_path().build()

        assert custom_env.base() == str(custom_dir.absolute())
        assert custom_env.bin_paths() is not None
    finally:
        if custom_dir.exists():
            shutil.rmtree(custom_dir)

    # Test custom environment with specific binary paths
    path_env = SimpleBuilder().bin_paths("/usr/bin", "/usr/local/bin").build()

    bin_paths = path_env.bin_paths()
    assert "/usr/bin" in bin_paths, "Custom bin_paths should include /usr/bin"
    assert "/usr/local/bin" in bin_paths, (
        "Custom bin_paths should include /usr/local/bin"
    )
