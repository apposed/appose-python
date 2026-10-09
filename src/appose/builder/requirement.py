# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Which appose-python a builder installs into the environments it builds.

The worker must implement the same major.minor version of Appose as the
service (see the HELLO handshake), so when a builder's caller does not
specify appose explicitly, the builder adds a compatible requirement:

1. The APPOSE_PYTHON_REQUIREMENT environment variable, if set: a local
   directory (installed in editable mode), or a pip requirement.
2. For a release of Appose, e.g. 1.1.2: appose>=1.1,<1.2 from PyPI.
3. For a development version, e.g. 1.1.0.dev0: this very appose-python,
   from wherever it was installed (a local directory, in editable mode, or
   a git commit), so that the worker runs the same code as the service.
   Failing that, the main branch of appose-python on GitHub.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from .._version import __version__

ENV_VAR = "APPOSE_PYTHON_REQUIREMENT"


@dataclass(frozen=True)
class Requirement:
    """
    A pip requirement for appose-python, e.g. "appose>=1.1,<1.2", or
    "appose @ file:///path/to/appose-python" with editable=True.
    """

    spec: str
    editable: bool = False

    def pip_args(self) -> list[str]:
        """The requirement as arguments to pip install."""
        return ["-e", self.spec] if self.editable else [self.spec]


MAIN_BRANCH = Requirement("appose @ git+https://github.com/apposed/appose-python")


def mentions_appose(packages: list[str]) -> bool:
    """
    Whether the given package specs include appose explicitly, in which case
    the caller's choice takes precedence over appose_requirement().
    """
    return any(re.match(r"^appose\b", pkg.strip()) for pkg in packages)


def appose_requirement(version: str = __version__) -> Requirement:
    """
    Determine which appose-python to install into a built environment,
    as described in this module's documentation.

    Args:
        version: The version of Appose in use.

    Returns:
        The requirement to install.
    """
    override = os.environ.get(ENV_VAR, "").strip()
    if override:
        if Path(override).is_dir():
            return _local(Path(override))
        return Requirement(override)

    if _is_release(version):
        major, minor = (int(x) for x in version.split(".")[:2])
        return Requirement(f"appose>={major}.{minor},<{major}.{minor + 1}")

    origin = _origin()
    return MAIN_BRANCH if origin is None else origin


def _is_release(version: str) -> bool:
    """Whether the version is a final release, e.g. 1.1.2 or 1.1.2.post1."""
    return re.fullmatch(r"\d+\.\d+(\.\d+)*(\.post\d+)?", version) is not None


def _local(path: Path) -> Requirement:
    uri = path.resolve().as_uri()
    return Requirement(f"appose @ {uri}", editable=True)


def _origin() -> Requirement | None:
    """
    Where this appose-python was installed from, per its direct_url.json
    (PEP 610), or None if it was installed from an index such as PyPI.
    """
    try:
        text = distribution("appose").read_text("direct_url.json")
    except PackageNotFoundError:
        return None
    if not text:
        return None
    info = json.loads(text)
    url = info.get("url")
    if not url:
        return None
    vcs_info = info.get("vcs_info")
    if vcs_info is not None:
        commit = vcs_info.get("commit_id")
        suffix = f"@{commit}" if commit else ""
        return Requirement(f"appose @ {vcs_info.get('vcs', 'git')}+{url}{suffix}")
    if info.get("dir_info") is not None:
        # NB: Editable, so that the worker sees source edits, as the service does.
        return Requirement(f"appose @ {url}", editable=True)
    return Requirement(f"appose @ {url}")
