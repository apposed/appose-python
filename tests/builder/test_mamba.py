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

"""End-to-end tests for MambaBuilder."""

from pathlib import Path


from appose.builder import DynamicBuilder
from appose.builder.mamba import MambaBuilder

from tests.test_base import cowsay_and_assert


# Get the path to test resources
TEST_RESOURCES = Path(__file__).parent.parent / "resources" / "envs"


def test_explicit_mamba_builder():
    """Tests explicit mamba builder selection using .builder() method."""
    env = (
        DynamicBuilder(str(TEST_RESOURCES / "cowsay.yml"))
        .builder("mamba")
        .base("target/envs/mamba-cowsay")
        .log_debug()
        .build()
    )

    assert isinstance(env.builder(), MambaBuilder)

    # Verify it actually used mamba by checking for conda-meta directory
    env_base = Path(env.base())
    conda_meta = env_base / "conda-meta"
    assert conda_meta.exists() and conda_meta.is_dir(), (
        "Environment should have conda-meta directory when using mamba builder"
    )

    cowsay_and_assert(env, "yay")
