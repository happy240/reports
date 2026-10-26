"""表格列映射、环境 JSON 解析与聚合。"""
from __future__ import annotations

import html
import json
import re
from datetime import date, timedelta
from typing import Any

import pandas as pd

ADDRESS_RE = re.compile(r"-([A-Za-z]\d+)-(\d+)\s*$")

# 参与「同阀 vs 前一天」对比的列
DOD_METRIC_COLS = ("进水pH值", "进水EC值", "尾水pH值", "尾水EC值", "尾水率(%)")


class HtmlCell:
    """表格单元格：允许嵌入已转义安全的 HTML（用于涨跌标注）。"""

    __slots__ = ("html",)

    def __init__(self, html: str) -> None:
        self.html = html

# 常见环境测点键别名（喜越室内站为 Temperature / RelativeHumidity）
TEMP_KEYS = {"temperature", "temp", "温度", "32", "t"}
HUMIDITY_KEYS = {
    "humidity",
    "relativehumidity",
    "relative_humidity",
    "hum",
    "湿度",
    "35",
    "h",
    "rh",
}


def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return False


def remark_for_row(row: pd.Series) -> str:
    """根据缺测情况生成备注。"""
    notes: list[str] = []
    drain_empty = all(
        _is_missing(row.get(c)) for c in ("drain_ph", "drain_ec", "water_drain_ml")
    )
    inlet_empty = all(_is_missing(row.get(c)) for c in ("inlet_ph", "inlet_ec"))
    if drain_empty and not inlet_empty:
        notes.append("无尾水流出或未测")
    elif drain_empty and inlet_empty:
        notes.append("进水/尾水均未测")
    elif _is_missing(row.get("drain_ph")) or _is_missing(row.get("drain_ec")):
        notes.append("尾水部分未测")
    return "；".join(notes)


def scale_ec_for_display(series: pd.Series) -> pd.Series:
    """库内 EC 多为 µS/cm（如 663），水肥表习惯用 mS/cm（0.663）。"""
    def _one(v: Any) -> Any:
        if _is_missing(v):
            return v
        try:
            num = float(v)
        except (TypeError, ValueError):
            return v
        if abs(num) >= 50:
            return round(num / 1000.0, 3)
        return round(num, 3)

    return series.map(_one)


def scale_ratio_to_percent(series: pd.Series) -> pd.Series:
    """尾水率：>1 视为已是百分比，否则按小数 ×100。"""

    def _one(v: Any) -> Any:
        if _is_missing(v):
            return v
        try:
            num = float(v)
        except (TypeError, ValueError):
            return v
        if abs(num) > 1:
            return round(num, 2)
        return round(num * 100.0, 2)

    return series.map(_one)


def prepare_chart_frame(df: pd.DataFrame, *, scale_ec: bool = True) -> pd.DataFrame:
    """趋势图用：可选 EC÷1000，尾水率为百分比，时间列转 datetime。"""
    if df.empty:
        return df
    out = df.copy()
    if scale_ec:
        for col in ("inlet_ec", "drain_ec"):
            if col in out.columns:
                out[col] = scale_ec_for_display(out[col])
    if "tail_water_ratio" in out.columns:
        out["tail_water_ratio"] = scale_ratio_to_percent(out["tail_water_ratio"])
    if "irrigation_start_time" in out.columns:
        out["irrigation_start_time"] = pd.to_datetime(out["irrigation_start_time"], errors="coerce")
    # db3 常用 record_date 作为横轴回退
    if "report_date" in out.columns:
        out["report_date"] = pd.to_datetime(out["report_date"], errors="coerce").dt.date
    elif "record_date" in out.columns:
        out["report_date"] = pd.to_datetime(out["record_date"], errors="coerce").dt.date
    if "irrigation_start_time" in out.columns:
        # 无开始时间时用日期占位，保证趋势可画
        missing = out["irrigation_start_time"].isna()
        if missing.any() and "report_date" in out.columns:
            out.loc[missing, "irrigation_start_time"] = pd.to_datetime(out.loc[missing, "report_date"])
    return out


def prepare_chart_frame_db3(df: pd.DataFrame) -> pd.DataFrame:
    """db3：EC 已是 mS/cm，不再 ÷1000。"""
    return prepare_chart_frame(df, scale_ec=False)


def to_water_fertilizer_table_db3(df: pd.DataFrame) -> pd.DataFrame:
    """db3 水肥表：序号/日期/电磁阀/进尾水 pH·EC/尾水率/备注。"""
    empty_cols = [
        "序号",
        "日期",
        "电磁阀",
        "进水pH值",
        "进水EC值",
        "尾水pH值",
        "尾水EC值",
        "尾水率(%)",
        "备注",
    ]
    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    out = df.copy()
    if "valve" not in out.columns and "address" in out.columns:
        parsed = out["address"].map(lambda a: ADDRESS_RE.search(str(a).strip()) if a else None)
        out["valve"] = parsed.map(lambda m: m.group(2) if m else None)

    def _remark(row: pd.Series) -> str:
        parts: list[str] = []
        raw = row.get("remark")
        if not _is_missing(raw) and str(raw).strip():
            parts.append(str(raw).strip())
        method = row.get("irrigation_method")
        if not _is_missing(method) and str(method).strip():
            parts.append(str(method).strip())
        # 进出水明显缺测
        drain_empty = all(_is_missing(row.get(c)) for c in ("drain_ph", "drain_ec"))
        inlet_empty = all(_is_missing(row.get(c)) for c in ("inlet_ph", "inlet_ec"))
        if drain_empty and not inlet_empty:
            parts.append("无尾水流出或未测")
        elif inlet_empty and drain_empty:
            parts.append("进水/尾水均未测")
        return "；".join(parts)

    if "tail_water_ratio" in out.columns:
        out["tail_water_ratio"] = scale_ratio_to_percent(out["tail_water_ratio"])

    out["备注"] = out.apply(_remark, axis=1)
    out = out.reset_index(drop=True)
    out.insert(0, "序号", range(1, len(out) + 1))

    date_col = "record_date" if "record_date" in out.columns else "report_date"
    rename = {
        date_col: "日期",
        "valve": "电磁阀",
        "inlet_ph": "进水pH值",
        "inlet_ec": "进水EC值",
        "drain_ph": "尾水pH值",
        "drain_ec": "尾水EC值",
        "tail_water_ratio": "尾水率(%)",
    }
    for src, dst in rename.items():
        if src in out.columns:
            out = out.rename(columns={src: dst})
    # 电磁阀展示为「N号」
    if "电磁阀" in out.columns:
        out["电磁阀"] = out["电磁阀"].map(
            lambda v: f"{v}号" if not _is_missing(v) and not str(v).endswith("号") else v
        )

    cols = [c for c in empty_cols if c in out.columns]
    result = out[cols].copy()
    if pd.api.types.is_datetime64_any_dtype(result["日期"]):
        result["日期"] = pd.to_datetime(result["日期"]).dt.date
    else:
        result["日期"] = pd.to_datetime(result["日期"], errors="coerce").dt.date
    return result


def _to_float(v: Any) -> float | None:
    if _is_missing(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_metric_number(col: str, v: float) -> str:
    if col in ("进水pH值", "尾水pH值"):
        return f"{v:.3f}"
    if col in ("进水EC值", "尾水EC值"):
        return f"{v:.3f}"
    if col == "尾水率(%)":
        return f"{v:.1f}"
    return f"{v:.3f}"


def _fmt_delta_pct(prev: float, cur: float) -> str | None:
    """相对前值的变化幅度（百分比）。前值为 0 时无法计算。"""
    if abs(prev) < 1e-12:
        return None
    pct = (cur - prev) / abs(prev) * 100.0
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f}%"


def with_dod_delta_display(table_df: pd.DataFrame) -> pd.DataFrame:
    """
    为指标列附加相对「同一电磁阀」前序记录的涨跌标注。
    优先对比前一自然日；若无记录则回退到该阀最近一次更早日期。
    """
    if table_df.empty:
        return table_df

    metric_cols = [c for c in DOD_METRIC_COLS if c in table_df.columns]
    if not metric_cols or "电磁阀" not in table_df.columns or "日期" not in table_df.columns:
        return table_df

    work = table_df.copy()
    work["_date"] = pd.to_datetime(work["日期"], errors="coerce").dt.date
    work["_valve"] = work["电磁阀"].astype(str).str.replace("号", "", regex=False)

    # 同阀按日：每日取序号最大的一条作为当日代表值
    by_valve_date: dict[str, dict[date, dict[str, float]]] = {}
    ordered = work.sort_values(["_valve", "_date", "序号"], kind="mergesort")
    for _, row in ordered.iterrows():
        d = row["_date"]
        v = str(row["_valve"])
        if d is None or (isinstance(d, float) and pd.isna(d)):
            continue
        by_valve_date.setdefault(v, {})[d] = {
            c: fv
            for c in metric_cols
            if (fv := _to_float(row[c])) is not None
        }

    def _resolve_prev(valve: str, cur_date: date) -> tuple[date, dict[str, float]] | None:
        series = by_valve_date.get(valve) or {}
        # 1) 严格前一自然日
        day_before = cur_date - timedelta(days=1)
        if day_before in series:
            return day_before, series[day_before]
        # 2) 回退：最近一次更早日期
        earlier = [d for d in series if d < cur_date]
        if not earlier:
            return None
        prev_d = max(earlier)
        return prev_d, series[prev_d]

    display = table_df.copy()
    for col in metric_cols:
        display[col] = display[col].astype(object)
    for idx, row in work.iterrows():
        d = row["_date"]
        v = str(row["_valve"])
        if d is None or (isinstance(d, float) and pd.isna(d)):
            continue
        resolved = _resolve_prev(v, d)
        for col in metric_cols:
            cur = _to_float(row[col])
            if cur is None:
                continue
            base = _fmt_metric_number(col, cur)
            if not resolved:
                display.at[idx, col] = HtmlCell(
                    f'<span class="xy-val">{html.escape(base)}</span>'
                )
                continue
            prev_d, prev_metrics = resolved
            if col not in prev_metrics:
                display.at[idx, col] = HtmlCell(
                    f'<span class="xy-val">{html.escape(base)}</span>'
                )
                continue
            prev_v = prev_metrics[col]
            delta = cur - prev_v
            pct_txt = _fmt_delta_pct(prev_v, cur)
            if pct_txt is None:
                display.at[idx, col] = HtmlCell(
                    f'<span class="xy-metric">'
                    f'<span class="xy-val">{html.escape(base)}</span>'
                    f"</span>"
                )
                continue
            if abs(delta) < 1e-9:
                cls, arrow = "xy-flat", "→"
            elif delta > 0:
                cls, arrow = "xy-up", "↑"
            else:
                cls, arrow = "xy-down", "↓"
            gap = (d - prev_d).days
            tip = (
                f"相对前一天同阀（{prev_d}）绝对变化 {delta:+.4g}"
                if gap == 1
                else f"相对前序同阀（{prev_d}，隔{gap}天）绝对变化 {delta:+.4g}"
            )
            display.at[idx, col] = HtmlCell(
                f'<span class="xy-metric">'
                f'<span class="xy-val">{html.escape(base)}</span>'
                f'<span class="xy-delta {cls}" title="{html.escape(tip)}">'
                f"{arrow}{html.escape(pct_txt)}</span>"
                f"</span>"
            )
    return display


def to_water_fertilizer_table(df: pd.DataFrame) -> pd.DataFrame:
    """转为水肥记录表风格的中文列。"""
    if df.empty:
        return pd.DataFrame(
            columns=[
                "序号",
                "日期",
                "当日第几次灌溉",
                "设备",
                "进水pH值",
                "进水EC值",
                "尾水pH值",
                "尾水EC值",
                "灌溉量(mL)",
                "尾水量(mL)",
                "尾水率(%)",
                "灌溉开始时间",
                "备注",
            ]
        )

    out = df.copy()
    for col in ("inlet_ec", "drain_ec"):
        if col in out.columns:
            out[col] = scale_ec_for_display(out[col])
    if "tail_water_ratio" in out.columns:
        out["tail_water_ratio"] = scale_ratio_to_percent(out["tail_water_ratio"])
    out["备注"] = out.apply(remark_for_row, axis=1)
    out = out.reset_index(drop=True)
    out.insert(0, "序号", range(1, len(out) + 1))

    rename = {
        "report_date": "日期",
        "irrigation_count": "当日第几次灌溉",
        "device_name": "设备",
        "inlet_ph": "进水pH值",
        "inlet_ec": "进水EC值",
        "drain_ph": "尾水pH值",
        "drain_ec": "尾水EC值",
        "water_in_ml": "灌溉量(mL)",
        "water_drain_ml": "尾水量(mL)",
        "tail_water_ratio": "尾水率(%)",
        "irrigation_start_time": "灌溉开始时间",
    }
    cols = ["序号"] + list(rename.values()) + ["备注"]
    result = out.rename(columns=rename)[cols]

    # 日期格式
    if pd.api.types.is_datetime64_any_dtype(result["日期"]):
        result["日期"] = result["日期"].dt.date
    return result


def _fmt_cell(v: Any) -> str:
    if isinstance(v, HtmlCell):
        return v.html
    if _is_missing(v):
        return ""
    if hasattr(v, "isoformat") and not isinstance(v, str):
        try:
            return html.escape(str(v))
        except Exception:
            return html.escape(repr(v))
    text = str(v)
    return html.escape(text)


def dataframe_to_html_date_merged(
    df: pd.DataFrame,
    date_col: str = "日期",
    expanded: bool = False,
) -> str:
    """生成日期列 rowspan 合并的 HTML 表格（同日合并为一个大单元格）。"""
    wrap_cls = "xy-table-wrap is-expanded" if expanded else "xy-table-wrap"
    if df.empty:
        return f'<div class="{wrap_cls}"><p class="xy-table-empty">无记录</p></div>'

    cols = list(df.columns)
    if date_col not in cols:
        raise ValueError(f"缺少日期列: {date_col}")

    # 连续相同日期的起止行
    dates = df[date_col].astype(str).tolist()
    spans: list[int] = []
    i = 0
    n = len(dates)
    while i < n:
        j = i + 1
        while j < n and dates[j] == dates[i]:
            j += 1
        spans.append(j - i)
        spans.extend([0] * (j - i - 1))
        i = j

    other_cols = [c for c in cols if c != date_col]
    # 日期列放在序号之后（若存在序号）
    if "序号" in cols:
        head_cols = ["序号", date_col] + [c for c in other_cols if c != "序号"]
    else:
        head_cols = [date_col] + other_cols

    thead = "".join(f"<th>{html.escape(c)}</th>" for c in head_cols)
    body_rows: list[str] = []
    group_idx = -1
    for i in range(n):
        row = df.iloc[i]
        if spans[i] > 0:
            group_idx += 1
        tds: list[str] = []
        for c in head_cols:
            if c == date_col:
                span = spans[i]
                if span == 0:
                    continue
                tds.append(
                    f'<td class="xy-date-cell" rowspan="{span}">{_fmt_cell(row[c])}</td>'
                )
            else:
                tds.append(f"<td>{_fmt_cell(row[c])}</td>")
        zebra = "xy-row-alt" if group_idx % 2 else ""
        body_rows.append(f'<tr class="{zebra}">' + "".join(tds) + "</tr>")

    return (
        f'<div class="{wrap_cls}">'
        f'<table class="xy-data-table"><thead><tr>{thead}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table></div>'
    )


def parse_device_data_json(raw: Any) -> dict[str, float]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return {}
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(obj, dict):
        return {}
    parsed: dict[str, float] = {}
    for k, v in obj.items():
        try:
            parsed[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return parsed


def infer_metric_keys(available_keys: list[str]) -> dict[str, str | None]:
    """从可用键中推断温度、湿度对应键。"""
    lower_map = {k.lower(): k for k in available_keys}
    temp = None
    hum = None
    for lk, orig in lower_map.items():
        if lk in TEMP_KEYS or lk.startswith("temp"):
            temp = orig
            break
    for lk, orig in lower_map.items():
        if lk in HUMIDITY_KEYS or "humid" in lk:
            hum = orig
            break
    # 数字键常见约定：32=温度, 35=湿度（与 device_data 注释一致）
    if temp is None and "32" in available_keys:
        temp = "32"
    if hum is None and "35" in available_keys:
        hum = "35"
    return {"temperature": temp, "humidity": hum}


def expand_environment_timeseries(
    raw_df: pd.DataFrame,
    temp_key: str | None = None,
    humidity_key: str | None = None,
) -> pd.DataFrame:
    """将环境 device_data 展开为温度/湿度长表（按小时聚合用）。"""
    if raw_df.empty:
        return pd.DataFrame(
            columns=[
                "device_id",
                "device_name",
                "shed",
                "collect_time",
                "temperature",
                "humidity",
            ]
        )

    if temp_key is None or humidity_key is None:
        # 从首批非空样本推断
        sample_keys: list[str] = []
        for raw in raw_df["data"].head(30):
            sample_keys.extend(parse_device_data_json(raw).keys())
        inferred = infer_metric_keys(sorted(set(sample_keys)))
        temp_key = temp_key or inferred["temperature"]
        humidity_key = humidity_key or inferred["humidity"]

    rows: list[dict[str, Any]] = []
    for _, r in raw_df.iterrows():
        metrics = parse_device_data_json(r["data"])
        rows.append(
            {
                "device_id": r["device_id"],
                "device_name": r["device_name"],
                "shed": r["shed"],
                "collect_time": r["collect_time"],
                "temperature": metrics.get(temp_key) if temp_key else None,
                "humidity": metrics.get(humidity_key) if humidity_key else None,
            }
        )
    df = pd.DataFrame(rows)
    df["collect_time"] = pd.to_datetime(df["collect_time"])
    return df


def aggregate_environment_hourly(env_df: pd.DataFrame) -> pd.DataFrame:
    if env_df.empty:
        return env_df
    df = env_df.copy()
    df["hour"] = df["collect_time"].dt.floor("h")
    grouped = (
        df.groupby(["device_id", "device_name", "shed", "hour"], as_index=False)
        .agg(temperature=("temperature", "mean"), humidity=("humidity", "mean"))
        .rename(columns={"hour": "collect_time"})
    )
    return grouped.sort_values("collect_time")


def daily_tail_water_means(df: pd.DataFrame) -> pd.DataFrame:
    """按日平均进水/尾水指标，便于趋势图。"""
    if df.empty:
        return df
    work = df.copy()
    if "report_date" not in work.columns and "record_date" in work.columns:
        work["report_date"] = work["record_date"]
    cols = [
        "inlet_ph",
        "inlet_ec",
        "drain_ph",
        "drain_ec",
        "tail_water_ratio",
        "water_in_ml",
        "water_drain_ml",
    ]
    present = [c for c in cols if c in work.columns]
    if "report_date" not in work.columns or not present:
        return pd.DataFrame()
    g = (
        work.groupby("report_date", as_index=False)[present]
        .mean(numeric_only=True)
        .sort_values("report_date")
    )
    return g
