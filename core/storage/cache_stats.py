"""缓存目录轻量统计，供管理员状态命令展示。"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class CacheStats:
    path: str
    available: bool
    file_count: int = 0
    total_bytes: int = 0
    subdir_count: int = 0
    truncated: bool = False

    @property
    def total_mb(self) -> float:
        return self.total_bytes / (1024 * 1024)


def summarize_cache_dir(
    path: str,
    *,
    max_entries: int = 2000,
    deadline_seconds: float = 2.0,
) -> CacheStats:
    """统计缓存目录占用；条目过多或超时会截断并标记 truncated。"""
    root = str(path or "").strip()
    if not root or not os.path.isdir(root):
        return CacheStats(path=root, available=False)

    stats = CacheStats(path=root, available=True)
    deadline = time.monotonic() + max(0.1, float(deadline_seconds))
    scanned = 0

    for dirpath, dirnames, filenames in os.walk(root):
        if time.monotonic() > deadline:
            stats.truncated = True
            break
        if dirpath != root:
            stats.subdir_count += 1
        for name in filenames:
            scanned += 1
            if scanned > max_entries:
                stats.truncated = True
                break
            try:
                stats.total_bytes += os.path.getsize(os.path.join(dirpath, name))
                stats.file_count += 1
            except OSError:
                continue
        if stats.truncated:
            break
        # 限制深度：只统计缓存一层子目录下的媒体目录
        if dirpath == root:
            dirnames[:] = dirnames

    return stats


def format_cache_stats(stats: Optional[CacheStats]) -> str:
    """把 CacheStats 格式化为状态命令中的一行中文。"""
    if stats is None or not stats.path:
        return "缓存：未配置"
    if not stats.available:
        return f"缓存：不可用 {stats.path}"
    suffix = "（统计不完整）" if stats.truncated else ""
    return (
        f"缓存：可用 {stats.path}"
        f"（约 {stats.total_mb:.0f} MB，{stats.subdir_count} 个子目录）{suffix}"
    )
