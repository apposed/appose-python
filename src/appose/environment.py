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

"""
TODO
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from .paths import find_exe
from .service import Service


class Environment:
    def __init__(self, base: Union[Path, str], use_system_path: bool = False):
        self.base = Path(base).absolute()
        self.use_system_path = use_system_path

    def python(self) -> Service:
        """
        Create a Python script service.

        This is a *high level* way to create a service, enabling execution of
        Python scripts asynchronously on its linked process running a
        `python_worker`.

        :return: The newly created service.
        :see: groovy() To create a service for Groovy script execution.
        :raises IOError: If something goes wrong starting the worker process.
        """
        python_exes = [
            "python",
            "python.exe",
            "bin/python",
            "bin/python.exe",
        ]
        return self.service(
            python_exes,
            "-c",
            "import appose.python_worker; appose.python_worker.main()",
        )

    def groovy(
        self,
        class_path: Optional[Sequence[str]] = None,
        jvm_args: Optional[Sequence[str]] = None,
    ) -> Service:
        """
        Create a Groovy script service. Groovy (https://groovy-lang.org/)
        is a script language for the JVM, capable of running Java bytecode
        conveniently and succinctly, as well as downloading and importing
        dependencies dynamically at runtime using its Grape subsystem
        (https://groovy-lang.org/Grape).

        This is a *high level* way to create a service, enabling execution of
        Groovy scripts asynchronously on its linked process running a
        `GroovyWorker`.

        :param class_path:
            Additional classpath elements to pass to the JVM
            via its `-cp` command line option.
        :param jvm_args:
            Command line arguments to pass to the JVM invocation (e.g. `-Xmx4g`).
        :return: The newly created service.
        :see: python() To create a service for Python script execution.
        :raises IOError: If something goes wrong starting the worker process.
        """
        return self.java(
            "org.apposed.appose.GroovyWorker", class_path=class_path, jvm_args=jvm_args
        )

    def java(
        self,
        main_class: str,
        class_path: Optional[Sequence[str]] = None,
        jvm_args: Optional[Sequence[str]] = None,
    ) -> Service:
        # Collect classpath elements into a set, to avoid duplicate entries.
        cp: Dict[str] = {}  # NB: Use dict instead of set to maintain insertion order.

        # TODO: Ensure that the classpath includes Appose and its dependencies.

        # Append any explicitly requested classpath elements.
        for element in class_path:
            cp[element] = None

        # Build up the service arguments.
        args = [
            "-cp",
            os.pathsep.join(cp),
        ]
        if jvm_args is not None:
            args.extend(jvm_args)
        args.append(main_class)

        # Create the service.
        java_exes = [
            "java",
            "java.exe",
            "bin/java",
            "bin/java.exe",
            "jre/bin/java",
            "jre/bin/java.exe",
        ]
        return self.service(java_exes, *args)

    def service(self, exes: Sequence[str], *args) -> Service:
        """
        Create a service with the given command line arguments.

        This is a **low level** way to create a service. It assumes the
        specified executable conforms to the Appose worker process contract,
        meaning it accepts requests on stdin and produces responses on
        stdout, both formatted according to Appose's assumptions.

        :param exes:
            List of executables to try for launching the worker process.
        :param args:
            Command line arguments to pass to the worker process
            (e.g. ["-v", "--enable-everything"]).
        :return: The newly created service.
        :see: groovy() To create a service for Groovy script execution.
        :see: python() To create a service for Python script execution.
        :raises IOError: If something goes wrong starting the worker process.
        """
        if not exes:
            raise ValueError("No executable given")

        dirs: List[str] = (
            os.environ["PATH"].split(os.pathsep)
            if self.use_system_path
            else [self.base]
        )

        exe_file = find_exe(dirs, exes)
        if exe_file is None:
            raise ValueError(f"No executables found amongst candidates: {exes}")

        all_args: List[str] = [str(exe_file)]
        all_args.extend(args)
        return Service(self.base, all_args)


class Builder:
    def __init__(self):
        self.base_dir: Optional[Path] = None
        self.system_path: bool = False
        self.conda_environment_yaml: Optional[Path] = None
        self.java_vendor: Optional[str] = None
        self.java_version: Optional[str] = None

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
