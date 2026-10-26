"""数据库连接：读取 .env 的 db1/db2/db3。密码不做 URL 解码。"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import pymysql

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV = ROOT / ".env"

DEFAULT_DATABASES = {
    "db1": "monitor",
    "db2": "rockai",
    "db3": "agromind",
}


def load_env(path: Path | None = None) -> dict[str, str]:
    env_path = path or Path(os.environ.get("REPORTS_ENV", DEFAULT_ENV))
    result: dict[str, str] = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def parse_mysql_url(url: str, default_database: str) -> dict:
    """解析 mysql:// 连接串。密码保留字面量（含 %3b），不做 unquote。"""
    u = urlparse(url)
    database = (u.path or "/").lstrip("/") or default_database
    return {
        "host": u.hostname,
        "port": u.port or 3306,
        "user": u.username,
        "password": u.password or "",
        "database": database,
    }


def get_db_params(key: str, env_path: Path | None = None) -> dict:
    env = load_env(env_path)
    if key not in env:
        raise KeyError(f"未在 .env 中找到 {key}")
    default_db = DEFAULT_DATABASES.get(key, "mysql")
    return parse_mysql_url(env[key], default_database=default_db)


@contextmanager
def db_connection(key: str, env_path: Path | None = None):
    params = get_db_params(key, env_path)
    conn = pymysql.connect(
        host=params["host"],
        port=params["port"],
        user=params["user"],
        password=params["password"],
        database=params["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        read_timeout=120,
        write_timeout=30,
    )
    try:
        yield conn
    finally:
        conn.close()


def get_monitor_params(env_path: Path | None = None) -> dict:
    return get_db_params("db1", env_path)


@contextmanager
def monitor_connection(env_path: Path | None = None):
    with db_connection("db1", env_path) as conn:
        yield conn
