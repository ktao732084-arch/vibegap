"""全局常量与用户配置加载。全项目唯一允许出现字面常量的模块(§7.6)。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, fields, replace
from pathlib import Path

logger = logging.getLogger(__name__)

DAEMON_HOST = "127.0.0.1"
DAEMON_PORT = 8765
POPUP_DELAY_SEC = 18       # ARMED → SHOWING 的延迟(防闪弹)
SUMMARY_LINGER_SEC = 2     # 软关闭小结停留时长
SESSION_TTL_MIN = 30       # 孤儿会话清理阈值
ADAPTER_TIMEOUT_SEC = 1    # 钩子上报 HTTP 超时
TICK_INTERVAL_SEC = 1      # 调度器定时脉冲间隔
TOAST_TIMEOUT_SEC = 5      # toast 子进程超时(效果在锁外执行,慢不阻塞事件,见 runtime.py)
LOG_RETENTION_DAYS = 7
SEED_RANGE = 2**31         # 洗牌种子取值上界(同一常量保证 seeded_order 的确定性)

MODE_SEQUENTIAL = "sequential"
MODE_SHUFFLED = "shuffled"
VALID_MODES = (MODE_SEQUENTIAL, MODE_SHUFFLED)

RESULT_PASS = "pass"
RESULT_FAIL = "fail"
RESULT_SKIP = "skip"
VALID_RESULTS = (RESULT_PASS, RESULT_FAIL, RESULT_SKIP)

# 新闻轮播(AIHOT,公开只读 API,要求可识别的非浏览器 UA;/api/public 2026 年底迁移 /api/v1)
NEWS_API_URL = "https://aihot.virxact.com/api/public/items?mode=selected&take=15"
NEWS_USER_AGENT = "WordGap/0.1 (vocab-mini-window; non-browser)"
NEWS_REFRESH_MIN = 30      # 拉取间隔,礼貌轮询
NEWS_HTTP_TIMEOUT_SEC = 8

# 悬浮窗
WINDOW_WIDTH = 390
WINDOW_HEIGHT = 250
WINDOW_TITLE = "WordGap"

DICTS_DIR = Path(__file__).resolve().parent.parent / "dicts"  # 内置词书目录

DATA_DIR = Path.home() / ".wordgap"
DB_PATH = DATA_DIR / "wordgap.db"
LOG_DIR = DATA_DIR / "logs"
CONFIG_PATH = DATA_DIR / "config.json"


@dataclass(frozen=True)
class Settings:
    """运行时可被 ~/.wordgap/config.json 覆盖的配置项。"""

    popup_delay_sec: int = POPUP_DELAY_SEC
    summary_linger_sec: int = SUMMARY_LINGER_SEC
    session_ttl_min: int = SESSION_TTL_MIN
    daemon_port: int = DAEMON_PORT
    daily_goal: int = 50  # 每日目标词数


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    """读用户配置 merge 到默认值;文件缺失或非法值回退默认并警告。"""
    defaults = Settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return defaults
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("config.json unreadable, using defaults: %s", exc)
        return defaults
    if not isinstance(raw, dict):
        logger.warning("config.json is not an object, using defaults")
        return defaults

    result = defaults
    for field in fields(Settings):
        value = raw.get(field.name)
        if value is None:
            continue
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            result = replace(result, **{field.name: value})
        else:
            logger.warning("config item %s invalid (%r), using default", field.name, value)
    return result
