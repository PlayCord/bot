import os

import psutil


def get_ram_usage_mb():
    # Get the current process
    process = psutil.Process(os.getpid())

    # Get memory information for the process
    # rss (Resident Set Size) is the non-swapped physical memory a process has used
    memory_info = process.memory_info()
    rss_bytes = memory_info.rss

    # Convert bytes to megabytes for readability
    rss_mb = rss_bytes / (1024 * 1024)

    return str(round(rss_mb, 2)) + " MB"
