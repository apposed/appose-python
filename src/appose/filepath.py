# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Utility functions for working with files and paths.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import platform


def location(c: type) -> Path | None:
    """
    Gets the path to the module file containing the given class/type.

    Args:
        c: The class/type whose file path should be discerned.

    Returns:
        Path to the file containing the given class, or None if not found.
    """
    try:
        if hasattr(c, "__file__") and c.__file__:
            return Path(c.__file__)
        # Try to get module
        if hasattr(c, "__module__"):
            import sys

            module = sys.modules.get(c.__module__)
            if module and hasattr(module, "__file__") and module.__file__:
                return Path(module.__file__)
    except Exception:
        pass
    return None


def file_type(name: str) -> str:
    """
    Extracts the file extension(s) from a filename.

    Args:
        name: The filename to extract extension from.

    Returns:
        The extension including the dot (e.g., ".txt", ".tar.gz"), or empty string if none.
    """
    pattern = re.compile(r".*?((\.[a-zA-Z0-9]+)+)$")
    match = pattern.match(name)
    if not match:
        return ""
    return match.group(1)


def find_exe(dirs: list[str], exes: list[str]) -> Path | None:
    """
    Finds an executable file by searching for it in a list of directories.

    Args:
        dirs: List of directory paths to search.
        exes: List of executable names/paths to search for.

    Returns:
        Path to the first matching executable found, or None if not found.
    """
    for exe in exes:
        exe_path = Path(exe)
        if exe_path.is_absolute():
            # Candidate is an absolute path; check it directly.
            if platform.is_executable(exe_path):
                return exe_path
        else:
            # Candidate is a relative path; check beneath each given directory.
            for dir_str in dirs:
                candidate = Path(dir_str) / exe
                if platform.is_executable(candidate) and not candidate.is_dir():
                    return candidate
    return None


def move_directory(src_dir: Path, dest_dir: Path, overwrite: bool) -> None:
    """
    Merges the files of the given source directory into the specified destination directory.

    For example, move_directory(foo, bar) would move:
    - foo/a.txt → bar/a.txt
    - foo/b.dat → bar/b.dat
    - foo/subfoo/d.doc → bar/subfoo/d.doc

    Args:
        src_dir: Source directory whose contents will be moved.
        dest_dir: Destination directory into which the source directory's contents will be merged.
        overwrite: If True, overwrite existing destination files; if False, back up source files instead.

    Raises:
        IOError: If the operation fails.
    """
    ensure_directory(src_dir)
    ensure_directory(dest_dir)

    for item in src_dir.iterdir():
        move_file(item, dest_dir, overwrite)

    # Remove the now-empty source directory
    src_dir.rmdir()


def move_file(src_file: Path, dest_dir: Path, overwrite: bool) -> None:
    """
    Moves the given source file to the destination directory,
    creating intermediate destination directories as needed.

    If the destination file already exists, one of two things will happen:
    A) The existing destination file will be renamed as a backup to file.ext.old
       (or file.ext.0.old, file.ext.1.old, etc., if file.ext.old already exists), or
    B) The source file will be renamed as a backup in this manner.

    Which behavior occurs depends on the value of the overwrite flag:
    True to back up the destination file, or False to back up the source file.

    Args:
        src_file: Source file to move.
        dest_dir: Destination directory into which the file will be moved.
        overwrite: If True, "overwrite" the destination file with the source file,
                   backing up any existing destination file first; if False,
                   leave the original destination file in place, instead moving
                   the source file to a backup destination as a "previous" version.

    Raises:
        IOError: If something goes wrong with the needed I/O operations.
    """
    dest_file = dest_dir / src_file.name

    if src_file.is_dir():
        # Create matching destination directory as needed.
        dest_file.mkdir(parents=True, exist_ok=True)
        # Recurse over source directory contents.
        move_directory(src_file, dest_file, overwrite)
        return

    # Source file is not a directory; move it into the destination directory.
    if dest_dir.exists() and not dest_dir.is_dir():
        raise ValueError(f"Non-directory destination path: {dest_dir}")

    dest_dir.mkdir(parents=True, exist_ok=True)

    if dest_file.exists() and not overwrite:
        # Destination already exists, and we aren't allowed to rename it.
        # So we instead rename the source file directly to a backup filename
        # in the destination directory.
        rename_to_backup(src_file, dest_dir)
        return

    # Rename the existing destination file (if any) to a backup file,
    # then move the source file into place.
    rename_to_backup(dest_file)
    src_file.rename(dest_file)


def rename_to_backup(src_file: Path, dest_dir: Path | None = None) -> None:
    """
    Renames the given file to a backup filename.

    The file will be renamed to filename.ext.old, or filename.ext.0.old,
    filename.ext.1.old, etc., if filename.ext.old already exists.

    Args:
        src_file: Source file to rename to a backup.
        dest_dir: Destination directory where the backup file will be created.
                  If None, uses the source file's parent directory.

    Raises:
        IOError: If something goes wrong with the needed I/O operations.
    """
    if not src_file.exists():
        return  # Nothing to back up!

    if dest_dir is None:
        dest_dir = src_file.parent

    prefix = src_file.name
    suffix = "old"
    backup_file = dest_dir / f"{prefix}.{suffix}"

    # Try to find a non-existing backup filename
    for i in range(1000):
        if not backup_file.exists():
            break
        backup_file = dest_dir / f"{prefix}.{i}.{suffix}"

    if backup_file.exists():
        failed_target = dest_dir / f"{prefix}.{suffix}"
        raise OSError(
            f"Too many backup files already exist for target: {failed_target}"
        )

    src_file.rename(backup_file)


def delete_recursively(dir: Path) -> None:
    """
    Deletes a directory and all its contents recursively.
    Properly handles symlinks including broken ones.

    Args:
        dir: The directory to delete.

    Raises:
        IOError: If deletion fails.
    """
    if not dir.exists() and not dir.is_symlink():
        return

    if dir.is_dir() and not dir.is_symlink():
        shutil.rmtree(dir)
    else:
        dir.unlink()


def ensure_directory(file: Path) -> None:
    """
    Checks that the given path is an existing directory, raising an exception if not.

    Args:
        file: The path to check.

    Raises:
        IOError: If the given path does not exist, or is not a directory.
    """
    if not file.exists():
        raise IOError(f"Directory does not exist: {file}")
    if not file.is_file():
        raise IOError(f"Not a directory: {file}")
