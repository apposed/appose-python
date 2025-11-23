# Copyright (C) 2023 - 2025 Appose developers.
# SPDX-License-Identifier: BSD-2-Clause

"""
Utility functions supporting download and unpacking of remote archives.
"""

from __future__ import annotations

import bz2
import os
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError

from .. import __version__


def download(
    name: str,
    url_path: str,
    progress_consumer: Callable[[int, int], None] | None = None,
) -> Path:
    """
    Downloads a file from a URL to a temporary file.

    Args:
        name: Base name for the temporary file.
        url_path: The URL to download from.
        progress_consumer: Optional callback to track download progress (current, total).

    Returns:
        Path to the downloaded temporary file.

    Raises:
        IOError: If download fails.
    """
    from .filepath import file_type

    # Resolve redirects and get final URL
    final_url = redirected_url(url_path)

    # Try to get file extension from final URL (after redirects)
    file_ext = file_type(final_url)
    if not file_ext:
        # Try to extract filename from query parameters (e.g., ?filename=file.tar.bz2)
        parsed = urllib.parse.urlparse(final_url)
        params = urllib.parse.parse_qs(parsed.query)

        # Check for filename in query parameters
        if "response-content-disposition" in params:
            # Parse Content-Disposition header value
            content_disp = params["response-content-disposition"][0]
            # Extract filename from 'filename="..."' or filename*=UTF-8''...
            import re

            match = re.search(
                r'filename[*]?=(?:UTF-8\'\')?["\']?([^"\';&]+)', content_disp
            )
            if match:
                filename = urllib.parse.unquote(match.group(1))
                file_ext = file_type(filename)

        # Fallback to original URL if still no extension
        if not file_ext:
            file_ext = file_type(url_path)

    # Create temporary file with appropriate extension
    fd, temp_path = tempfile.mkstemp(prefix=f"{name}-", suffix=file_ext)
    temp_file = Path(temp_path)

    try:
        file_size = get_file_size(final_url)

        # Download file with progress tracking
        request = urllib.request.Request(
            final_url, headers={"User-Agent": user_agent()}
        )

        with urllib.request.urlopen(request) as response:
            with os.fdopen(fd, "wb") as f:
                chunk_size = 8192
                downloaded = 0

                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break

                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_consumer:
                        progress_consumer(downloaded, file_size)

        # Verify download completed
        if temp_file.stat().st_size < file_size:
            temp_file.unlink(missing_ok=True)
            raise IOError(f"Error downloading {name} from: {url_path}")

        return temp_file

    except Exception as e:
        # Clean up on error
        temp_file.unlink(missing_ok=True)
        raise IOError(f"Failed to download {name} from {url_path}: {e}") from e


def un_bzip2(source: Path, destination: Path) -> None:
    """
    Decompress a bzip2 file into a new file.

    Args:
        source: The .bzip2 file to decompress.
        destination: Destination file where contents will be written.

    Raises:
        FileNotFoundError: If the source file doesn't exist.
        IOError: If decompression fails.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    with bz2.open(source, "rb") as input_file:
        with open(destination, "wb") as output_file:
            shutil.copyfileobj(input_file, output_file)


def unpack(input_file: Path, output_dir: Path) -> None:
    """
    Unpacks an archive file to a directory.

    Supports .tar, .tar.bz2, .tar.gz, and .zip formats.

    Args:
        input_file: The archive file to unpack.
        output_dir: Destination directory for unpacked contents.

    Raises:
        FileNotFoundError: If the input file doesn't exist.
        ValueError: If the archive format is unsupported.
        IOError: If unpacking fails.
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Archive file not found: {input_file}")

    filename = input_file.name.lower()

    if filename.endswith(".tar"):
        un_tar(input_file, output_dir)
    elif filename.endswith(".tar.bz2"):
        un_tar_bz2(input_file, output_dir)
    elif filename.endswith(".tar.gz"):
        un_tar_gz(input_file, output_dir)
    elif filename.endswith(".zip"):
        un_zip(input_file, output_dir)
    else:
        raise ValueError(f"Unsupported archive type for file: {input_file.name}")


def un_zip(source: Path, destination: Path) -> None:
    """
    Decompress a zip file into a directory.

    Args:
        source: The .zip file to decompress.
        destination: Destination folder for decompressed contents.

    Raises:
        FileNotFoundError: If the source file doesn't exist.
        IOError: If decompression fails.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    destination.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source, "r") as zip_file:
        for entry in zip_file.infolist():
            output_file = destination / entry.filename

            if entry.is_dir():
                output_file.mkdir(parents=True, exist_ok=True)
            else:
                output_file.parent.mkdir(parents=True, exist_ok=True)

                with zip_file.open(entry) as input_stream:
                    with open(output_file, "wb") as output_stream:
                        shutil.copyfileobj(input_stream, output_stream)

                # Set executable permission if the entry had it
                # ZipInfo external_attr stores Unix permissions in high-order 16 bits
                if (entry.external_attr >> 16) & 0o100:
                    output_file.chmod(output_file.stat().st_mode | 0o100)


def un_tar(input_file: Path, output_dir: Path) -> None:
    """
    Untar an input file into an output directory.

    Args:
        input_file: The input .tar file.
        output_dir: The output directory.

    Raises:
        FileNotFoundError: If the input file doesn't exist.
        IOError: If extraction fails.
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(input_file, "r") as tar:
        tar.extractall(path=output_dir)


def un_tar_gz(input_file: Path, output_dir: Path) -> None:
    """
    Decompress a gzip file and then untar it into a directory.

    Args:
        input_file: The input .tar.gz file.
        output_dir: The output directory.

    Raises:
        FileNotFoundError: If the input file doesn't exist.
        IOError: If extraction fails.
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(input_file, "r:gz") as tar:
        tar.extractall(path=output_dir)


def un_tar_bz2(input_file: Path, output_dir: Path) -> None:
    """
    Decompress a bzip2 file and then untar it into a directory.

    Args:
        input_file: The input .tar.bz2 file.
        output_dir: The output directory.

    Raises:
        FileNotFoundError: If the input file doesn't exist.
        IOError: If extraction fails.
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # For .tar.bz2, first decompress to .tar, then extract
    temp_tar = tempfile.NamedTemporaryFile(suffix=".tar", delete=False)
    temp_tar_path = Path(temp_tar.name)
    temp_tar.close()

    try:
        un_bzip2(input_file, temp_tar_path)
        un_tar(temp_tar_path, output_dir)
    finally:
        temp_tar_path.unlink(missing_ok=True)


def redirected_url(url: str) -> str:
    """
    Follows HTTP redirects to get the final URL.

    This method handles response codes 301, 302, 303, etc.

    Args:
        url: Original URL that may redirect.

    Returns:
        The final redirected URL.

    Raises:
        HTTPError: If the URL is invalid or connection fails.
    """
    try:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent()})
        with urllib.request.urlopen(request) as response:
            # If we got here, either no redirect or urllib already followed it
            return response.url if hasattr(response, "url") else url
    except HTTPError as e:
        # For 3xx codes, try to follow Location header
        if 300 <= e.code < 400:
            location = e.headers.get("Location")
            if location:
                # Handle relative URLs
                if location.startswith("//"):
                    parsed = urllib.parse.urlparse(url)
                    return redirected_url(f"{parsed.scheme}:{location}")
                elif not location.startswith("http"):
                    parsed = urllib.parse.urlparse(url)
                    base = f"{parsed.scheme}://{parsed.netloc}"
                    return redirected_url(urllib.parse.urljoin(base, location))
                else:
                    return redirected_url(location)
        return url
    except Exception:
        return url


def get_file_size(url: str) -> int:
    """
    Get the size of the file stored at the given URL.

    Args:
        url: URL where the file is stored.

    Returns:
        The size of the file in bytes, or 1 if unable to determine.
    """
    try:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent()})
        with urllib.request.urlopen(request) as response:
            # Check for redirects
            if 300 <= response.status < 400:
                final_url = redirected_url(url)
                if final_url != url:
                    return get_file_size(final_url)

            # Get content length
            content_length = response.headers.get("Content-Length")
            if content_length:
                return int(content_length)

            return 1  # Unknown size
    except Exception as e:
        print(f"Unable to connect to {url}: {e}")
        return 1


def user_agent() -> str:
    """
    Generates a User-Agent string for HTTP requests.

    Returns:
        User-Agent string with Python version and platform info.
    """
    import platform
    import sys

    python_version = sys.version.split()[0]
    os_name = platform.system()
    os_version = platform.release()
    os_arch = platform.machine()

    os_info = (
        f"{os_name}-{os_version}-{os_arch}" if os_version else f"{os_name}-{os_arch}"
    )

    return f"Appose/{__version__} (Python {python_version}/{os_info})"
