# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bound the memory of a collector process (AD-319)."""

import sys
from typing import Final

# The Python TypeScript collector peaks at 973 MiB of address space on the 907 files of the React UI
# corpus (Linux, 3 runs: 966 to 973 MiB). The limit is about four times that peak (AD-319).
COLLECTOR_MEMORY_LIMIT_BYTES: Final = 4 * 1024**3
_MIB: Final = 1024**2
# The text that Python, Rust, glibc and Node.js write when an allocation fails.
_ALLOCATION_FAILURES: Final = (
    "MemoryError",
    "memory allocation of",
    "out of memory",
    "Cannot allocate memory",
)
_LIMITED_PLATFORMS: Final = ("linux", "win32")


def limit_memory(pid: int, limit_bytes: int) -> str | None:
    """Set RLIMIT_AS of a started Linux collector; return the reason when that fails.

    The host calls this before it writes the request, so the collector does its work under the
    limit. Windows sets the limit in the job of `windows_job.py`. macOS has no reliable
    RLIMIT_AS, so a collector on macOS has no memory limit.
    """
    if sys.platform != "linux":
        return None
    import resource

    soft, _ = resource.getrlimit(resource.RLIMIT_AS)
    value = limit_bytes if soft == resource.RLIM_INFINITY else min(limit_bytes, soft)
    try:
        resource.prlimit(pid, resource.RLIMIT_AS, (value, value))
    except ProcessLookupError:
        # The collector exited before it got its request; its exit status tells why.
        return None
    except OSError as error:
        return f"Could not set the collector memory limit: {error}"
    return None


def exit_message(returncode: int, stderr: str, limit_bytes: int) -> str:
    """The failure text of a collector exit; it names the limit after a failed allocation."""
    message = f"Collector exited {returncode}: {stderr}"
    if sys.platform in _LIMITED_PLATFORMS and any(
        marker in stderr for marker in _ALLOCATION_FAILURES
    ):
        limit = f"{limit_bytes} bytes ({limit_bytes / _MIB:g} MiB)"
        return f"Collector exceeded its memory limit of {limit}. {message}"
    return message
