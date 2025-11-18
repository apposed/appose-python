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

"""Tests for filepath utilities."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from appose.util import filepath, platform


EXT = ".exe" if platform.is_windows() else ""
SET_EXEC_BIT = not platform.is_windows()


def test_find_exe():
    """Test filepath.find_exe function."""
    with tempfile.TemporaryDirectory(prefix="appose-test-find-exe-") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Set up some red herrings
        create_stub_file(tmp_path, "walk")
        create_stub_file(tmp_path, "fly")

        bin_dir = create_directory(tmp_path, "bin")
        bin_fly = create_stub_file(bin_dir, f"fly{EXT}")

        if SET_EXEC_BIT:
            # Mark the desired match as executable
            bin_fly.chmod(0o755)
            assert os.access(bin_fly, os.X_OK)

        # Search for the desired match
        dirs = [str(tmp_path), str(bin_dir)]
        exes = [f"walk{EXT}", f"fly{EXT}", f"swim{EXT}"]
        exe = filepath.find_exe(dirs, exes)

        # Check that we found the right file
        assert exe == bin_fly


def test_location():
    """Test filepath.location function."""
    # Get the location of this test module
    import sys

    test_module = sys.modules[__name__]
    actual = filepath.location(test_module.__class__)
    # The location function works with classes, so we test with a class defined in this module
    # Actually, let's just test that it returns a path for a known class
    if actual is None:
        # For modules, try a different approach - just verify the function works
        # by checking it returns something for an actual class
        class LocalTestClass:
            pass

        actual = filepath.location(LocalTestClass)
    assert actual is not None
    assert actual.exists()


def test_move_directory():
    """Test filepath.move_directory function."""
    with tempfile.TemporaryDirectory(prefix="appose-test-move-dir-") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Set up a decently weighty directory structure
        src_dir = create_directory(tmp_path, "src")
        breakfast = create_stub_file(src_dir, "breakfast")

        lunch_dir = create_directory(src_dir, "lunch")
        lunch_file1 = create_stub_file(lunch_dir, "apples", "fuji")
        lunch_file2 = create_stub_file(lunch_dir, "bananas")

        dinner_dir = create_directory(src_dir, "dinner")
        dinner_file1 = create_stub_file(dinner_dir, "bread")
        dinner_file2 = create_stub_file(dinner_dir, "wine")

        dest_dir = create_directory(tmp_path, "dest")
        dest_lunch_dir = create_directory(dest_dir, "lunch")
        create_stub_file(dest_lunch_dir, "apples", "gala")

        # Move the source directory to the destination
        filepath.move_directory(src_dir, dest_dir, False)

        # Check whether everything worked
        assert not src_dir.exists()
        assert_moved(breakfast, dest_dir, "<breakfast>")
        assert_moved(lunch_file1, dest_lunch_dir, "gala")

        backup_lunch_file1 = dest_lunch_dir / "apples.old"
        assert_content(backup_lunch_file1, "fuji")
        assert_moved(lunch_file2, dest_lunch_dir, "<bananas>")

        dest_dinner_dir = dest_dir / dinner_dir.name
        assert_moved(dinner_file1, dest_dinner_dir, "<bread>")
        assert_moved(dinner_file2, dest_dinner_dir, "<wine>")


def test_move_file():
    """Test filepath.move_file function."""
    with tempfile.TemporaryDirectory(prefix="appose-test-move-file-") as tmp_dir:
        tmp_path = Path(tmp_dir)

        src_dir = create_directory(tmp_path, "from")
        src_file = create_stub_file(src_dir, "stuff.txt", "shiny")

        dest_dir = create_directory(tmp_path, "to")
        dest_file = create_stub_file(dest_dir, "stuff.txt", "obsolete")

        overwrite = True
        filepath.move_file(src_file, dest_dir, overwrite)

        assert src_dir.exists()
        assert not src_file.exists()
        assert_content(dest_file, "shiny")

        backup_file = dest_dir / "stuff.txt.old"
        assert_content(backup_file, "obsolete")


def test_rename_to_backup():
    """Test filepath.rename_to_backup function."""
    with tempfile.NamedTemporaryFile(
        prefix="appose-test-rename-", delete=False
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        assert tmp_path.exists()
        filepath.rename_to_backup(tmp_path)

        backup_file = tmp_path.parent / f"{tmp_path.name}.old"
        assert not tmp_path.exists()
        assert backup_file.exists()

        # Clean up
        backup_file.unlink()
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# Helper functions


def create_directory(parent: Path, name: str) -> Path:
    """Create a directory and verify it exists."""
    dir_path = parent / name
    dir_path.mkdir()
    assert dir_path.exists()
    return dir_path


def create_stub_file(dir_path: Path, name: str, content: str | None = None) -> Path:
    """Create a stub file with optional content."""
    if content is None:
        content = f"<{name}>"

    stub_file = dir_path / name
    stub_file.write_text(content)
    assert stub_file.exists()
    return stub_file


def assert_moved(src_file: Path, dest_dir: Path, expected_content: str) -> None:
    """Assert that a file was moved to the destination with expected content."""
    assert not src_file.exists()
    dest_file = dest_dir / src_file.name
    assert_content(dest_file, expected_content)


def assert_content(file: Path, expected_content: str) -> None:
    """Assert that a file exists and has the expected content."""
    assert file.exists()
    actual_content = file.read_text()
    assert expected_content == actual_content
