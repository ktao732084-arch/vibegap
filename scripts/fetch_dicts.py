"""下载内置词书到 dicts/(来自 qwerty-learner 开源词库,不随本仓库分发)。

用法:python scripts/fetch_dicts.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

_BASE = "https://raw.githubusercontent.com/RealKai42/qwerty-learner/master/public/dicts/"
# 目标文件名 -> 源文件名候选(上游可能改名,按序尝试)
_BOOKS = {
    "CET6.json": ["CET6_T.json", "CET6.json"],
    "GRE3000.json": ["GRE3000_T.json", "GRE_3000.json", "GRE3000.json"],
}
_TIMEOUT_SEC = 30


def fetch(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SEC) as resp:  # noqa: S310
            return resp.read()
    except OSError:
        return None


def main() -> None:
    dicts_dir = Path(__file__).resolve().parent.parent / "dicts"
    dicts_dir.mkdir(exist_ok=True)
    failed = []
    for target, candidates in _BOOKS.items():
        out = dicts_dir / target
        if out.exists():
            print(f"skip {target} (already exists)")
            continue
        data = None
        for name in candidates:
            data = fetch(_BASE + name)
            if data:
                break
        if data:
            out.write_bytes(data)
            print(f"fetched {target} ({len(data) // 1024} KB)")
        else:
            failed.append(target)
    if failed:
        sys.exit(f"ERROR: failed to fetch {failed}; check network or download manually.")
    print("done. run `python -m vibegap` to import on first start.")


if __name__ == "__main__":
    main()
