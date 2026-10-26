"""喜越农场尾水交互报表：db3 水肥为主，db1 同棚数据为辅。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, time
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from queries import (
    fetch_environment_raw,
    fetch_tail_water_summary,
    fetch_xiyue_irrigation,
    list_environment_devices,
    list_tail_water_devices,
    list_xiyue_sheds,
    list_xiyue_valves,
)
from transform import (
    aggregate_environment_hourly,
    daily_tail_water_means,
    dataframe_to_html_date_merged,
    expand_environment_timeseries,
    prepare_chart_frame,
    prepare_chart_frame_db3,
    to_water_fertilizer_table,
    to_water_fertilizer_table_db3,
    with_dod_delta_display,
)

C_RED = "#c62828"
C_AMBER = "#e6a700"
C_INK = "#1a1f16"
C_MUTED = "#5c6654"
C_LEAF = "#2e7d32"
C_GRID = "#e8ece2"

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#ffffff",
    font=dict(family="PingFang SC, Microsoft YaHei, sans-serif", color=C_INK, size=13),
    margin=dict(l=48, r=16, t=36, b=36),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=12, color=C_INK)),
    hovermode="x unified",
)


def inject_styles() -> None:
    css_path = Path(__file__).with_name("styles.css")
    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def style_axes(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_LAYOUT)
    fig.update_xaxes(showgrid=True, gridcolor=C_GRID, zeroline=False, color=C_MUTED)
    fig.update_yaxes(showgrid=True, gridcolor=C_GRID, zeroline=False, color=C_MUTED)
    return fig


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "水肥记录") -> bytes:
    """导出 Excel（.xlsx）。"""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31] or "Sheet1")
    return buf.getvalue()


st.set_page_config(
    page_title="喜越尾水报表",
    page_icon=None,
    layout="wide",
)
inject_styles()

st.markdown(
    """
    <div class="xy-hero">
      <div>
        <p class="xy-hero-title">喜越农场 · <span class="mark">尾水记录</span></p>
      </div>
      <div class="xy-hero-meta">
        <span class="xy-deco">🌾 ◆ 🌿</span>
        <span class="xy-chip">水肥监测</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=60)
def cached_sheds() -> list[str]:
    return list_xiyue_sheds()


@st.cache_data(ttl=60)
def cached_valves(shed: str) -> list[str]:
    return list_xiyue_valves(shed)


@st.cache_data(ttl=60)
def cached_irrigation(
    shed: str,
    start: date,
    end: date,
    valves: tuple[str, ...] | None,
) -> pd.DataFrame:
    return fetch_xiyue_irrigation(shed, start, end, list(valves) if valves else None)


@st.cache_data(ttl=60)
def cached_env(region: str, start: date, end: date) -> pd.DataFrame:
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end, time.max)
    raw = fetch_environment_raw(region, start_dt, end_dt, limit=8000)
    return aggregate_environment_hourly(expand_environment_timeseries(raw))


@st.cache_data(ttl=60)
def cached_aux_tail(region: str, start: date, end: date) -> pd.DataFrame:
    return fetch_tail_water_summary(region, start, end)


def build_ph_ec_figure(df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        subplot_titles=("pH", "EC (mS/cm)"), vertical_spacing=0.1,
    )
    if not df.empty:
        x = df["irrigation_start_time"]
        fig.add_trace(
            go.Scatter(x=x, y=df["inlet_ph"], name="进水pH", mode="lines+markers",
                       line=dict(color=C_AMBER, width=2), marker=dict(size=6)),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(x=x, y=df["drain_ph"], name="尾水pH", mode="lines+markers",
                       line=dict(color=C_RED, width=2), marker=dict(size=6)),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(x=x, y=df["inlet_ec"], name="进水EC", mode="lines+markers",
                       line=dict(color=C_AMBER, width=2), marker=dict(size=6)),
            row=2, col=1,
        )
        fig.add_trace(
            go.Scatter(x=x, y=df["drain_ec"], name="尾水EC", mode="lines+markers",
                       line=dict(color=C_RED, width=2), marker=dict(size=6)),
            row=2, col=1,
        )
    fig.update_layout(height=460)
    style_axes(fig)
    fig.update_annotations(font=dict(size=13, color=C_INK))
    return fig


def build_ratio_volume_figure(df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        subplot_titles=("尾水率 (%)", "水量"), vertical_spacing=0.1,
    )
    if not df.empty:
        x = df["irrigation_start_time"]
        fig.add_trace(
            go.Scatter(x=x, y=df["tail_water_ratio"], name="尾水率(%)", mode="lines+markers",
                       line=dict(color=C_RED, width=2), marker=dict(size=6, color=C_RED)),
            row=1, col=1,
        )
        if "water_in_ml" in df.columns:
            fig.add_trace(go.Bar(x=x, y=df["water_in_ml"], name="灌溉量", marker_color=C_AMBER), row=2, col=1)
        if "water_drain_ml" in df.columns:
            fig.add_trace(go.Bar(x=x, y=df["water_drain_ml"], name="尾水量", marker_color=C_RED), row=2, col=1)
    fig.update_layout(height=440, barmode="group")
    style_axes(fig)
    fig.update_annotations(font=dict(size=13, color=C_INK))
    fig.update_yaxes(title_text="%", row=1, col=1)
    return fig


def build_daily_means_figure(daily: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not daily.empty:
        x = daily["report_date"]
        palette = {
            "inlet_ph": C_AMBER, "drain_ph": C_RED,
            "inlet_ec": "#f0c040", "drain_ec": "#8b1e1e",
            "tail_water_ratio": C_LEAF,
        }
        labels = {
            "inlet_ph": "进水pH", "drain_ph": "尾水pH",
            "inlet_ec": "进水EC", "drain_ec": "尾水EC",
            "tail_water_ratio": "尾水率(%)",
        }
        for col, name in labels.items():
            if col in daily.columns:
                fig.add_trace(
                    go.Scatter(
                        x=x, y=daily[col], name=name, mode="lines+markers",
                        line=dict(color=palette[col], width=2), marker=dict(size=6),
                    )
                )
    fig.update_layout(height=340)
    style_axes(fig)
    return fig


def build_env_figure(env_df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        subplot_titles=("温度 (°C)", "湿度 (%)"), vertical_spacing=0.1,
    )
    if not env_df.empty:
        colors = [C_AMBER, C_RED, C_LEAF, C_INK]
        for i, (device_name, g) in enumerate(env_df.groupby("device_name")):
            g = g.sort_values("collect_time")
            c = colors[i % len(colors)]
            fig.add_trace(
                go.Scatter(x=g["collect_time"], y=g["temperature"], name=f"{device_name}·温",
                           mode="lines", line=dict(color=c, width=1.8)),
                row=1, col=1,
            )
            fig.add_trace(
                go.Scatter(x=g["collect_time"], y=g["humidity"], name=f"{device_name}·湿",
                           mode="lines", line=dict(color=c, width=1.8, dash="dot")),
                row=2, col=1,
            )
    fig.update_layout(height=420)
    style_axes(fig)
    fig.update_annotations(font=dict(size=13, color=C_INK))
    return fig


# ---------- 侧栏 ----------
with st.sidebar:
    st.markdown("### 筛选")
    st.markdown('<div class="xy-side-label">农场</div>', unsafe_allow_html=True)
    st.markdown("**喜越农场**")

    try:
        sheds = cached_sheds()
    except Exception as e:
        st.error(f"db3 连接失败：{e}")
        st.stop()

    if not sheds:
        st.warning("db3 无喜越棚号")
        st.stop()

    default_shed = "A2" if "A2" in sheds else ("A3" if "A3" in sheds else sheds[0])
    st.markdown('<div class="xy-side-label">棚号</div>', unsafe_allow_html=True)
    shed = st.radio(
        "棚号",
        sheds,
        index=sheds.index(default_shed),
        horizontal=True,
        label_visibility="collapsed",
    )

    st.markdown('<div class="xy-side-label">日期</div>', unsafe_allow_html=True)
    today = date.today()
    default_start = today - timedelta(days=13)
    date_range = st.date_input(
        "日期范围",
        value=(default_start, today),
        max_value=today + timedelta(days=1),
        label_visibility="collapsed",
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range  # type: ignore[misc]

    valves = cached_valves(shed)
    st.markdown('<div class="xy-side-label">电磁阀</div>', unsafe_allow_html=True)
    valve_labels = [f"{v}号" for v in valves]
    selected_valve_labels = st.multiselect(
        "电磁阀",
        options=valve_labels,
        default=valve_labels,
        label_visibility="collapsed",
    )
    selected_valves = tuple(
        lb.replace("号", "") for lb in selected_valve_labels
    )

    show_aux = st.checkbox("辅助参考 (db1)", value=True)
    refresh = st.button("刷新", use_container_width=True)

if refresh:
    cached_sheds.clear()
    cached_valves.clear()
    cached_irrigation.clear()
    cached_env.clear()
    cached_aux_tail.clear()

if valves and not selected_valves:
    st.warning("请选择电磁阀")
    st.stop()

try:
    raw_df = cached_irrigation(
        shed, start_date, end_date,
        selected_valves if selected_valves else None,
    )
except Exception as e:
    st.error(f"db3 查询失败：{e}")
    st.stop()

table_df = to_water_fertilizer_table_db3(raw_df)
display_df = with_dod_delta_display(table_df)

# 辅助数据（失败不阻断）
aux_env_devs: list = []
aux_env_df = pd.DataFrame()
aux_tail_df = pd.DataFrame()
aux_env_err = None
aux_tail_err = None
if show_aux:
    try:
        aux_env_devs = list_environment_devices(shed)
    except Exception as e:
        aux_env_err = str(e)
    try:
        if aux_env_devs:
            aux_env_df = cached_env(shed, start_date, end_date)
    except Exception as e:
        aux_env_err = str(e)
    try:
        if list_tail_water_devices(shed):
            aux_tail_df = cached_aux_tail(shed, start_date, end_date)
    except Exception as e:
        aux_tail_err = str(e)

m1, m2, m3, m4 = st.columns(4)
m1.metric("记录", len(table_df))
m2.metric("电磁阀", len(valves))
date_col = "record_date" if "record_date" in raw_df.columns else None
if not raw_df.empty and date_col:
    m3.metric("区间", f"{raw_df[date_col].min()} → {raw_df[date_col].max()}")
else:
    m3.metric("区间", "—")
aux_hint = []
if show_aux:
    if not aux_env_df.empty:
        aux_hint.append(f"环境{len(aux_env_df)}")
    if not aux_tail_df.empty:
        aux_hint.append(f"自动尾水{len(aux_tail_df)}")
m4.metric("辅助", " · ".join(aux_hint) if aux_hint else "—")

sec_l, sec_r = st.columns([5, 2])
with sec_l:
    st.markdown(
        f'<div class="xy-section"><span class="dot"></span>{shed}棚 · 水肥记录</div>',
        unsafe_allow_html=True,
    )
with sec_r:
    if "table_expanded" not in st.session_state:
        st.session_state.table_expanded = False
    toggle_label = "收起表格" if st.session_state.table_expanded else "展开表格"
    if st.button(toggle_label, key="btn_toggle_table", use_container_width=True):
        st.session_state.table_expanded = not st.session_state.table_expanded
        st.rerun()

st.markdown(
    dataframe_to_html_date_merged(
        display_df, date_col="日期", expanded=st.session_state.table_expanded,
    ),
    unsafe_allow_html=True,
)

c_csv, c_xlsx, _ = st.columns([1, 1, 3])
export_stem = f"xiyue_irrigation_{shed}_{start_date}_{end_date}"
with c_csv:
    st.download_button(
        "导出 CSV",
        data=table_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{export_stem}.csv",
        mime="text/csv",
        use_container_width=True,
    )
with c_xlsx:
    st.download_button(
        "导出 Excel",
        data=dataframe_to_excel_bytes(table_df, sheet_name=f"{shed}棚"),
        file_name=f"{export_stem}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

st.markdown(
    '<div class="xy-section"><span class="dot"></span>趋势</div>',
    unsafe_allow_html=True,
)

if raw_df.empty:
    st.warning("无记录")
else:
    chart_df = prepare_chart_frame_db3(raw_df).sort_values("irrigation_start_time")
    tab1, tab2, tab3 = st.tabs(["pH / EC", "尾水率 · 水量", "日均"])
    with tab1:
        st.plotly_chart(build_ph_ec_figure(chart_df), use_container_width=True)
    with tab2:
        st.plotly_chart(build_ratio_volume_figure(chart_df), use_container_width=True)
    with tab3:
        daily = daily_tail_water_means(prepare_chart_frame_db3(raw_df))
        st.plotly_chart(build_daily_means_figure(daily), use_container_width=True)

# ---------- 辅助参考 ----------
has_aux = (not aux_env_df.empty) or (not aux_tail_df.empty) or aux_env_err or aux_tail_err
if show_aux and has_aux:
    st.markdown(
        f'<div class="xy-section"><span class="dot"></span>辅助参考 · db1 · {shed}棚</div>',
        unsafe_allow_html=True,
    )
    with st.expander("同棚环境 / 自动尾水", expanded=True):
        if aux_env_err:
            st.caption(f"环境：{aux_env_err}")
        elif not aux_env_devs:
            st.caption("同棚无环境设备")
        elif aux_env_df.empty:
            st.caption("所选日期无环境数据")
        else:
            st.plotly_chart(build_env_figure(aux_env_df), use_container_width=True)

        if aux_tail_err:
            st.caption(f"自动尾水：{aux_tail_err}")
        elif aux_tail_df.empty:
            st.caption("同棚无自动尾水汇总")
        else:
            aux_table = to_water_fertilizer_table(aux_tail_df)
            st.markdown(
                dataframe_to_html_date_merged(aux_table, date_col="日期", expanded=False),
                unsafe_allow_html=True,
            )
            aux_chart = prepare_chart_frame(aux_tail_df).sort_values("irrigation_start_time")
            st.plotly_chart(build_ph_ec_figure(aux_chart), use_container_width=True)
