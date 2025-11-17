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

"""End-to-end tests for UvBuilder."""

from pathlib import Path


from appose.builder.uv import UvBuilder

from tests.test_base import cowsay_and_assert


# Get the path to test resources
TEST_RESOURCES = Path(__file__).parent.parent / "resources" / "envs"


def test_uv():
    """Tests building from a requirements.txt file."""
    env = (
        UvBuilder(str(TEST_RESOURCES / "cowsay-requirements.txt"))
        .base("target/envs/uv-cowsay")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), UvBuilder)
    cowsay_and_assert(env, "uv")


def test_uv_builder_api():
    """Tests the programmatic builder API for uv."""
    env = (
        UvBuilder()
        .include("cowsay==6.1")
        .base("target/envs/uv-cowsay-builder")
        .log_debug()
        .build()
    )
    assert isinstance(env.builder(), UvBuilder)
    cowsay_and_assert(env, "fast")


def test_uv_pyproject():
    """Tests building from a pyproject.toml file."""
    env = (
        UvBuilder(str(TEST_RESOURCES / "cowsay-pyproject.toml"))
        .base("target/envs/uv-cowsay-pyproject")
        .log_debug()
        .build()
    )
    cowsay_and_assert(env, "pyproject")
