"""下载内置词书到 dicts/(来自 qwerty-learner 开源词库,不随本仓库分发)。

用法:python scripts/fetch_dicts.py
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

_REVISION = "122acd90b4079dd040c28a14356447f6553cff83"
_BASE = f"https://raw.githubusercontent.com/RealKai42/qwerty-learner/{_REVISION}/"
# 发布构建固定到同一上游提交与哈希，避免 master 改名或内容漂移。
_BOOKS = {
    "CET6.json": (
        "public/dicts/CET6_T.json",
        "ed5e76b945b7c7bc567a75d44a6eaeda137c767960121057deab52593e245d6e",
    ),
    "GRE3000.json": (
        "public/dicts/GRE3000_3_T.json",
        "f7702f9751e0543eeab0ea05357b43ad0388750758a8d5435f6ff2f39b742dfe",
    ),
}
_LICENSE = (
    "qwerty-learner-LICENSE",
    "LICENSE",
    "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
)
_TIMEOUT_SEC = 30


def fetch(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SEC) as resp:  # noqa: S310
            return resp.read()
    except OSError:
        return None


def ensure_file(path: Path, source: str, expected_sha256: str) -> bool:
    data = path.read_bytes() if path.exists() else fetch(_BASE + source)
    if data is None or hashlib.sha256(data).hexdigest() != expected_sha256:
        return False
    if not path.exists():
        path.write_bytes(data)
        print(f"fetched {path.name} ({len(data) // 1024} KB)")
    else:
        print(f"skip {path.name} (verified)")
    return True


def main() -> None:
    dicts_dir = Path(__file__).resolve().parent.parent / "dicts"
    dicts_dir.mkdir(exist_ok=True)
    failed = []
    assets = [(target, *details) for target, details in _BOOKS.items()]
    assets.append(_LICENSE)
    for target, source, expected_sha256 in assets:
        if not ensure_file(dicts_dir / target, source, expected_sha256):
            failed.append(target)
    if failed:
        sys.exit(f"ERROR: failed to fetch {failed}; check network or download manually.")
    print("done. run `python -m vibegap` to import on first start.")


if __name__ == "__main__":
    main()
