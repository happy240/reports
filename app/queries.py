"""喜越水肥/尾水查询：db3 为主，db1 为辅。"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

import pandas as pd

from db import db_connection, monitor_connection

FARM_LIKE = "%喜越%"
XIYUE_FARM = "xiyue"
# 弥勒农场-A2-5 → shed=A2, valve=5
ADDRESS_RE = re.compile(r"-([A-Za-z]\d+)-(\d+)\s*$")


def parse_address(address: str | None) -> tuple[str | None, str | None]:
    if not address:
        return None, None
    m = ADDRESS_RE.search(str(address).strip())
    if not m:
        return None, None
    return m.group(1).upper(), m.group(2)


def _read_sql(key: str, sql: str, params: tuple | list | None = None) -> pd.DataFrame:
    with db_connection(key) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _read_monitor_sql(sql: str, params: tuple | list | None = None) -> pd.DataFrame:
    return _read_sql("db1", sql, params)


# ---------- db3 主数据 ----------

def list_xiyue_sheds() -> list[str]:
    """从 address 解析去重棚号。"""
    sql = """
        SELECT DISTINCT address
        FROM farming_irrigation_record
        WHERE farm = %s AND status = 1
          AND address IS NOT NULL AND address <> ''
    """
    sheds: set[str] = set()
    with db_connection("db3") as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (XIYUE_FARM,))
            for row in cur.fetchall():
                shed, _ = parse_address(row["address"])
                if shed:
                    sheds.add(shed)
    return sorted(sheds, key=lambda s: (s[0], int(re.search(r"\d+", s).group()) if re.search(r"\d+", s) else 0))


def list_xiyue_valves(shed: str) -> list[str]:
    sql = """
        SELECT DISTINCT address
        FROM farming_irrigation_record
        WHERE farm = %s AND status = 1
          AND address LIKE %s
    """
    valves: set[str] = set()
    with db_connection("db3") as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (XIYUE_FARM, f"%-{shed}-%"))
            for row in cur.fetchall():
                s, v = parse_address(row["address"])
                if s == shed and v:
                    valves.add(v)
    return sorted(valves, key=lambda x: int(x) if x.isdigit() else x)


def fetch_xiyue_irrigation(
    shed: str,
    start_date: date,
    end_date: date,
    valves: list[str] | None = None,
) -> pd.DataFrame:
    """喜越手填水肥主查询。"""
    params: list[Any] = [XIYUE_FARM, f"%-{shed}-%", start_date, end_date]
    sql = """
        SELECT
            id,
            address,
            region_id,
            record_date,
            crops_type,
            irrigation_method,
            inlet_ph,
            inlet_ec,
            effluent_ph AS drain_ph,
            effluent_ec AS drain_ec,
            effluent_ratio AS tail_water_ratio,
            inlet_water AS water_in_ml,
            effluent_water AS water_drain_ml,
            irrigation_start_time,
            irrigation_end_time,
            remark,
            sn,
            status
        FROM farming_irrigation_record
        WHERE farm = %s
          AND status = 1
          AND address LIKE %s
          AND record_date BETWEEN %s AND %s
        ORDER BY record_date DESC, address ASC, id ASC
    """
    df = _read_sql("db3", sql, params)
    if df.empty:
        return df

    parsed = df["address"].map(lambda a: parse_address(a))
    df["shed"] = parsed.map(lambda x: x[0])
    df["valve"] = parsed.map(lambda x: x[1])
    df = df[df["shed"] == shed].copy()
    if valves:
        valve_set = {str(v) for v in valves}
        df = df[df["valve"].astype(str).isin(valve_set)].copy()
    return df.reset_index(drop=True)


# ---------- db1 辅助 ----------

def list_sheds() -> list[str]:
    """db1 有尾水设备的棚号（辅助）。"""
    sql = """
        SELECT DISTINCT region
        FROM sensor_device
        WHERE farm LIKE %s
          AND type = 'tail_water'
          AND region IS NOT NULL
          AND region <> ''
        ORDER BY region
    """
    with monitor_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (FARM_LIKE,))
            return [r["region"] for r in cur.fetchall()]


def list_tail_water_devices(region: str) -> list[dict[str, Any]]:
    sql = """
        SELECT id, sn, name, region, status, online
        FROM sensor_device
        WHERE farm LIKE %s
          AND type = 'tail_water'
          AND region = %s
        ORDER BY id
    """
    with monitor_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (FARM_LIKE, region))
            return list(cur.fetchall())


def fetch_tail_water_summary(
    region: str,
    start_date: date,
    end_date: date,
    device_ids: list[int] | None = None,
) -> pd.DataFrame:
    """db1 自动尾水汇总（辅助）。"""
    params: list[Any] = [FARM_LIKE, region, start_date, end_date]
    device_filter = ""
    if device_ids:
        placeholders = ",".join(["%s"] * len(device_ids))
        device_filter = f" AND t.device_id IN ({placeholders})"
        params.extend(device_ids)

    sql = f"""
        SELECT
            t.id,
            t.device_id,
            t.device_sn,
            s.name AS device_name,
            s.region AS shed,
            t.report_date,
            t.irrigation_count,
            t.irrigation_start_time,
            t.tail_water_source_time,
            t.packet_count,
            t.water_in_ml,
            t.water_drain_ml,
            t.tail_water_ratio,
            t.inlet_ph,
            t.inlet_ec,
            t.drain_ph,
            t.drain_ec
        FROM tail_water_irrigation_summary t
        JOIN sensor_device s ON s.id = t.device_id
        WHERE s.farm LIKE %s
          AND s.type = 'tail_water'
          AND s.region = %s
          AND t.report_date BETWEEN %s AND %s
          {device_filter}
        ORDER BY t.report_date DESC, t.irrigation_count ASC, t.irrigation_start_time ASC
    """
    return _read_monitor_sql(sql, params)


def list_environment_devices(region: str) -> list[dict[str, Any]]:
    sql = """
        SELECT id, sn, name, region
        FROM sensor_device
        WHERE farm LIKE %s
          AND type = 'environment'
          AND region = %s
        ORDER BY id
    """
    with monitor_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (FARM_LIKE, region))
            return list(cur.fetchall())


def fetch_environment_raw(
    region: str,
    start_dt: datetime,
    end_dt: datetime,
    limit: int = 5000,
) -> pd.DataFrame:
    """同棚环境传感器原始 data JSON（辅助）。"""
    sql = """
        SELECT
            d.device_id,
            s.name AS device_name,
            s.region AS shed,
            d.collect_time,
            d.data
        FROM device_data d
        JOIN sensor_device s ON s.id = d.device_id
        WHERE s.farm LIKE %s
          AND s.type = 'environment'
          AND s.region = %s
          AND d.collect_time BETWEEN %s AND %s
        ORDER BY d.collect_time DESC
        LIMIT %s
    """
    return _read_monitor_sql(sql, (FARM_LIKE, region, start_dt, end_dt, limit))


def sample_environment_keys(region: str, sample_n: int = 20) -> list[str]:
    sql = """
        SELECT d.data
        FROM device_data d
        JOIN sensor_device s ON s.id = d.device_id
        WHERE s.farm LIKE %s
          AND s.type = 'environment'
          AND s.region = %s
          AND d.data IS NOT NULL
        ORDER BY d.collect_time DESC
        LIMIT %s
    """
    keys: set[str] = set()
    with monitor_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (FARM_LIKE, region, sample_n))
            for row in cur.fetchall():
                raw = row["data"]
                if not raw:
                    continue
                try:
                    obj = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(obj, dict):
                        keys.update(str(k) for k in obj.keys())
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
    return sorted(keys, key=lambda x: (len(x), x))
