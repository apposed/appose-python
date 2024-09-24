###
# #%L
# Appose: multi-language interprocess cooperation with shared memory.
# %%
# Copyright (C) 2023 - 2024 Appose developers.
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
from importlib.metadata import entry_points
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
            "python3",
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
        if class_path is not None:
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


class BuildHandler(ABC):
    @abstractmethod
    def include(self, content: str, scheme: Optional[str]) -> bool:
        pass

    @abstractmethod
    def channel(self, name: str, location: Optional[str]) -> bool:
        pass


class Builder:

    def __init__(self):
        self.config: dict[str, list[str]] = {}
        self.progress_subscribers = []
        self.output_subscribers = []
        self.error_subscribers = []

        self.include_system_path = False
        self.scheme = "conda"

        self.handlers = []
        for entry_point in entry_points(group='appose.build-handlers'):
            handler_class = entry_point.load()
            self.handlers.append(handler_class())

    def subscribe_progress(self, subscriber) -> "Builder":
        """
        Register a callback method to be invoked when progress happens
        during environment building.

        :param subscriber: Party to inform when build progress happens.
        :return: This Builder instance, for fluent-style programming.
        """
        progress_subscribers.add(subscriber)
        return self

    def subscribe_output(self, subscriber) -> "Builder":
        """
        Register a callback method to be invoked to report
        output messages during environment building.

        :param subscriber: Party to inform when output happens.
        :return: This Builder instance, for fluent-style programming.
        """
        output_subscribers.add(subscriber)
        return self

    def subscribe_error(self, subscriber) -> "Builder":
        """
        Register a callback method to be invoked to report
        error messages during environment building.

        :param subscriber: Party to inform when errors happen.
        :return: This Builder instance, for fluent-style programming.
        """
        error_subscribers.add(subscriber)
        return self

    def log_debug(self) -> "Builder":
        """
        Shorthand for subscribeProgress, subscribeOutput, and
        subscribeError calls registering subscribers that emit their
        arguments to stdout. Useful for debugging environment
        construction, e.g. complex environments with many conda packages.
        
        :return: This {@code Builder} instance, for fluent-style programming.
        """
        reset = "\u001b[0m";
        yellow = "\u001b[0;33m";
        red = "\u001b[0;31m";
        return subscribeProgress(
            lambda title, cur, max: printf("%s: %d/%d\n", title, cur, max)
        ).subscribeOutput(
            lambda msg: printf("%s%s%s", yellow, "." if msg.isEmpty() else msg, reset)
        ).subscribeError(
            lambda msg: printf("%s%s%s", red, "." if msg.isEmpty() else msg, reset)
        )

    def use_system_path(self) -> "Builder":
        self.include_system_path = True
        return self


    def scheme(scheme: str) -> "Builder":
        """
        Set the scheme to use with subsequent channel(name) and
        include(content) directives.

        :param scheme: TODO
        :return: This Builder instance, for fluent-style programming.
        """
        self.scheme = scheme;
        return this;

    def file(file_or_path: Union[str, Path], scheme: str = None) -> "Builder":
        """
        TODO
        
        @return This {@code Builder} instance, for fluent-style programming.
        """
        return file(new File(filePath), scheme);
    }

    def file(file: Path) -> "Builder":
        """
        TODO
        
        @return This {@code Builder} instance, for fluent-style programming.
        """
        return file(file, file.getName());
    }

    def file(file: Path, scheme: str) -> "Builder":
        """
        TODO
        
        @return This {@code Builder} instance, for fluent-style programming.
        """
        byte[] bytes = Files.readAllBytes(file.toPath());
        return include(new String(bytes), scheme);
    }

    def channel(name: str) -> "Builder":
        """
        Register a channel that provides components of the environment,
        according to the currently configured scheme ("conda" by default).
        <p>
        For example, {@code channel("bioconda")} registers the {@code bioconda}
        channel as a source for conda packages.
        </p>
        
        @param name The name of the channel to register.
        @return This {@code Builder} instance, for fluent-style programming.
        @see #channel(String, String)
        @see #scheme(String)
        """
        return channel(name, scheme);
    }

    def channel(name: str, location: str) -> "Builder":
        """
        Register a channel that provides components of the environment.
        How to specify a channel is implementation-dependent. Examples:
        
        <ul>
          <li>{@code channel("bioconda")} -
            to register the {@code bioconda} channel as a source for conda packages.</li>
          <li>{@code channel("scijava", "maven:https://maven.scijava.org/content/groups/public")} -
            to register the SciJava Maven repository as a source for Maven artifacts.</li>
        </ul>
        
        @param name The name of the channel to register.
        @param location The location of the channel (e.g. a URI), or {@code null} if the
                         name alone is sufficient to unambiguously identify the channel.
        @return This {@code Builder} instance, for fluent-style programming.
        @throws IllegalArgumentException if the channel is not understood by any of the available build handlers.
        """
        # Pass the channel directive to all handlers.
        if handle(lambda handler: handler.channel(name, location)): return this
        # None of the handlers accepted the directive.
        raise ValueError(f"Unsupported channel: {name} {'' if location is None else '='}{location}")

    def include(content: str, scheme: str = None) -> "Builder":
        """
        Register content to be included within the environment.
        How to specify the content is implementation-dependent. Examples:
        <ul>
          <li>{@code include("cowsay", "pypi")} -
            Install {@code cowsay} from the Python package index.</li>
          <li>{@code include("openjdk=17")} -
            Install {@code openjdk} version 17 from conda-forge.</li>
          <li>{@code include("bioconda::sourmash")} -
            Specify a conda channel explicitly using environment.yml syntax.</li>
          <li>{@code include("org.scijava:parsington", "maven")} -
            Install the latest version of Parsington from Maven Central.</li>
          <li>{@code include("org.scijava:parsington:2.0.0", "maven")} -
            Install Parsington 2.0.0 from Maven Central.</li>
          <li>{@code include("sc.fiji:fiji", "maven")} -
            Install the latest version of Fiji from registered Maven repositories.</li>
          <li>{@code include("zulu:17", "jdk")} -
            Install version 17 of Azul Zulu OpenJDK.</li>
          <li>{@code include(yamlString, "environment.yml")} -
            Provide the literal contents of a conda {@code environment.yml} file,
            indicating a set of packages to include.
        </ul>
        <p>
        Note that content is not actually fetched or installed until
        {@link #build} is called at the end of the builder chain.
        </p>
        
        @param content The content (e.g. a package name, or perhaps the contents of an environment
                        configuration file) to include in the environment, fetching if needed.
        @param scheme The type of content, which serves as a hint for how to interpret
                       the content in some scenarios; see above for examples.
        @return This {@code Builder} instance, for fluent-style programming.
        @throws IllegalArgumentException if the include directive is not understood by any of the available build handlers.
        """
        # Pass the include directive to all handlers.
        if (handle(handler -> handler.include(content, scheme))) return this;
        # None of the handlers accepted the directive.
        raise ValueError(f"Unsupported '{scheme}' content: {content}");




    def build(self, ):
        # TODO: Build the thing!
        # Hash the state to make a base directory name.
        # - Construct conda environment from condaEnvironmentYaml.
        # - Download and unpack JVM of the given vendor+version.
        # - Populate ${baseDirectory}/jars with Maven artifacts?

        for handler in self.handlers:
            handler.include("myContent", "myScheme");
        return Environment(self.base_dir, self.system_path)

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
