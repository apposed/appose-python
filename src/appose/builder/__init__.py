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

"""
TODO
"""

from __future__ import annotations

from pathlib import Path

from ..environment import Environment


class Builder:
    """
    TODO
    """

    def __init__(self):
        self.base_dir: Path | None = None
        self.system_path: bool = False
        self.conda_environment_yaml: Path | None = None
        self.java_vendor: str | None = None
        self.java_version: str | None = None

    def build(self):
        # TODO: Build the thing!
        # Hash the state to make a base directory name.
        # - Construct conda environment from condaEnvironmentYaml.
        # - Download and unpack JVM of the given vendor+version.
        # - Populate ${baseDirectory}/jars with Maven artifacts?
        return Environment(self.base_dir, self.system_path)

    def use_system_path(self) -> "Builder":
        self.system_path = True
        return self

    def base(self, directory: Path) -> "Builder":
        self.base_dir: Path = directory
        return self

    # -- Conda --

    def conda(self, environment_yaml: Path) -> "Builder":
        self.conda_environment_yaml: Path = environment_yaml
        return self

    # -- Java --

    def java(self, vendor: str = None, version: str = None) -> "Builder":
        if vendor is not None:
            self.java_vendor: str = vendor
        if version is not None:
            self.java_version: str = version
        return self
