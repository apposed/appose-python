# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause


"""Shared fixtures for Appose tests."""

from pathlib import Path

import pytest

SIBLING_APPOSE_JAVA = Path("../appose-java/target/classes")


@pytest.fixture
def groovy_class_path(monkeypatch) -> list[str]:
    """
    Class path for Groovy workers: a sibling appose-java build, if present (as
    appose-java's tests do for appose-python, and as CI arranges), else the
    appose-java release fetched by bin/test.sh.
    """
    if not SIBLING_APPOSE_JAVA.is_dir():
        # NB: The released appose-java need not match the appose-python under test.
        monkeypatch.setenv("APPOSE_SKIP_VERSION_CHECK", "1")
        return ["target/dependency/*"]
    # Prefer the sibling's own dependencies, which match its pom.xml, if built
    # (e.g. via mvn dependency:copy-dependencies, as CI does).
    dependencies = SIBLING_APPOSE_JAVA.parent / "dependency"
    if not dependencies.is_dir():
        dependencies = Path("target/dependency")
    return [str(SIBLING_APPOSE_JAVA.resolve()), str(dependencies.resolve() / "*")]
