# Appose: multi-language interprocess cooperation with shared memory.
# Copyright (C) 2023 - 2026 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""Tests for library code registered via Service.import_library."""

from __future__ import annotations

import zipfile
from pathlib import Path
from textwrap import dedent

import pytest

import appose
from appose.service import TaskException
from tests.conftest import SIBLING_APPOSE_JAVA
from tests.test_base import maybe_debug

MODELS_LIB = dedent(
    """
    _MODELS: dict[str, str] = {}
    load_count = 0

    def load_model(key: str) -> str:
        global load_count
        load_count += 1
        return key.upper()

    def get_model(key: str) -> str:
        if key not in _MODELS:
            _MODELS[key] = load_model(key)
        return _MODELS[key]

    def run_model(key: str, x: int) -> str:
        return f"{get_model(key)}:{x}"
    """
)


BOOM_LIB = "def boom():\n    raise ValueError('kaboom')\n"

PACKAGE_LIB = {
    "__init__.py": "from .core import double\n",
    "core.py": "def double(x):\n    return 2 * x\n",
    "sub/deep.py": "from ..core import double\nVALUE = double(21)\n",
}
PACKAGE_SCRIPT = (
    "import mypkg\nfrom mypkg.sub import deep\n[mypkg.double(3), deep.VALUE]"
)


def test_library_warm_state():
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        service.import_library("mylib", source=MODELS_LIB)
        for x in range(3):
            task = service.task(
                "import mylib\nmylib.run_model(key, x)", {"key": "a", "x": x}
            ).wait_for()
            assert task.outputs["result"] == f"A:{x}"
        service.task("import mylib\nmylib.run_model('b', 0)").wait_for()
        # Each model was loaded only once, and stayed warm across tasks.
        task = service.task("import mylib\nmylib.load_count").wait_for()
        assert task.outputs["result"] == 2


def test_library_after_start():
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        service.start()
        service.task("1").wait_for()
        service.import_library("mylib", source=MODELS_LIB)
        task = service.task("import mylib\nmylib.run_model('c', 5)").wait_for()
        assert task.outputs["result"] == "C:5"


def test_library_in_init_script():
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        service.import_library("mylib", source=MODELS_LIB).init(
            "import mylib\nmylib.get_model('warm')"
        )
        task = service.task("import mylib\nmylib.load_count").wait_for()
        assert task.outputs["result"] == 1


def test_library_package():
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        service.import_library("mypkg", source=PACKAGE_LIB)
        task = service.task(PACKAGE_SCRIPT).wait_for()
        assert task.outputs["result"] == [6, 42]


def test_library_reregister():
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        service.import_library("mylib", source=MODELS_LIB)
        service.task("import mylib\nmylib.get_model('a')").wait_for()

        # Unchanged source: module state is retained.
        service.import_library("mylib", source=MODELS_LIB)
        task = service.task("import mylib\nmylib.load_count").wait_for()
        assert task.outputs["result"] == 1

        # Changed source: module is reloaded with the new code.
        service.import_library("mylib", source=MODELS_LIB + "\nVERSION = 2\n")
        task = service.task("import mylib\n[mylib.load_count, mylib.VERSION]")
        assert task.wait_for().outputs["result"] == [0, 2]


def test_library_traceback():
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        service.import_library("mylib", source=BOOM_LIB)
        with pytest.raises(TaskException) as e:
            service.task("import mylib\nmylib.boom()").wait_for()
        error = e.value.task.error
        assert error is not None and "<appose>/mylib.py" in error
        assert "raise ValueError('kaboom')" in error


def test_library_path_module(tmp_path):
    lib = tmp_path / "anything.py"
    lib.write_text(MODELS_LIB + BOOM_LIB)
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        service.import_library("mylib", path=lib)
        task = service.task("import mylib\nmylib.run_model('p', 2)").wait_for()
        assert task.outputs["result"] == "P:2"

        # Tracebacks refer to the library's original file.
        with pytest.raises(TaskException) as e:
            service.task("import mylib\nmylib.boom()").wait_for()
        error = e.value.task.error
        assert error is not None and str(lib.resolve()) in error
        assert "raise ValueError('kaboom')" in error


def test_library_path_package(tmp_path):
    pkg = tmp_path / "pkg"
    for relpath, code in PACKAGE_LIB.items():
        (pkg / relpath).parent.mkdir(parents=True, exist_ok=True)
        (pkg / relpath).write_text(code)
    (pkg / "data.txt").write_text("hello")
    env = appose.system()
    with env.python() as service:
        maybe_debug(service)
        service.import_library("mypkg", path=pkg)

        # Code is snapshotted at registration, not read from disk at import.
        (pkg / "core.py").write_text("def double(x):\n    return 0\n")
        task = service.task(PACKAGE_SCRIPT).wait_for()
        assert task.outputs["result"] == [6, 42]

        # Resources are read from disk on demand, like an installed package.
        task = service.task(
            "import importlib.resources\n"
            "importlib.resources.files('mypkg').joinpath('data.txt').read_text()"
        ).wait_for()
        assert task.outputs["result"] == "hello"


def test_library_invalid_args():
    service = appose.system().python()
    with pytest.raises(ValueError):
        service.import_library("my-lib", source="")
    with pytest.raises(ValueError):
        service.import_library("mylib")
    with pytest.raises(ValueError):
        service.import_library("mylib", path="mylib.py", source="")
    with pytest.raises(TypeError):
        service.import_library("mylib", "mylib.py")  # type: ignore[misc]


def _has_groovy_libraries() -> bool:
    """
    Whether the appose-java used by the groovy_class_path fixture supports
    libraries: a sibling build, or the release fetched by bin/test.sh.
    """
    if SIBLING_APPOSE_JAVA.is_dir():
        return (
            SIBLING_APPOSE_JAVA / "org/apposed/appose/GroovyLibraries.class"
        ).exists()
    for jar in Path("target/dependency").glob("appose-*.jar"):
        with zipfile.ZipFile(jar) as z:
            if "org/apposed/appose/GroovyLibraries.class" in z.namelist():
                return True
    return False


needs_groovy_libraries = pytest.mark.skipif(
    not _has_groovy_libraries(), reason="appose-java lacks GroovyLibraries"
)

MODELS_GROOVY = dedent(
    """
    package mylib
    class Models {
      static final Map<String, String> CACHE = [:]
      static int loadCount = 0
      static String get(String key) {
        CACHE.computeIfAbsent(key) { loadCount++; Util.load(it) }
      }
    }
    """
)
UTIL_GROOVY = (
    "package mylib\nclass Util { static String load(String k) { k.toUpperCase() } }\n"
)


@needs_groovy_libraries
def test_library_groovy(groovy_class_path):
    env = appose.system()
    with env.groovy(class_path=groovy_class_path) as service:
        maybe_debug(service)
        service.import_library(
            "mylib",
            source={
                "mylib/Models.groovy": MODELS_GROOVY,
                "mylib/Util.groovy": UTIL_GROOVY,
            },
        ).init("mylib.Models.get('warm')")
        script = "import mylib.Models\n"
        assert (
            service.task(script + "Models.get('a')").wait_for().outputs["result"] == "A"
        )
        # Each model was loaded only once, and stayed warm across tasks.
        task = service.task(script + "Models.get('a'); Models.loadCount").wait_for()
        assert task.outputs["result"] == 2


@needs_groovy_libraries
def test_library_groovy_quoting(groovy_class_path):
    """Test that awkward characters survive the trip into the worker intact."""
    text = "it's a \\ \"$dollar\" ''' \\u0041 \t line\r\nbreak"
    escaped = (
        text.replace("\\", "\\\\").replace("'", "\\'").replace("$", "\\$")
    ).replace("\r", "\\r")
    env = appose.system()
    with env.groovy(class_path=groovy_class_path) as service:
        maybe_debug(service)
        service.import_library(
            "Text", source=f"class Text {{ static String get() {{ '''{escaped}''' }} }}"
        )
        assert service.task("Text.get()").wait_for().outputs["result"] == text
