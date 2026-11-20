import io
import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ─────────────────────────────────────────────────────────────
# 한글 폰트 / 스타일
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR&display=swap');
html, body, [class*="css"] {
   font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="극지식물 생육 대시보드", layout="wide")

# ─────────────────────────────────────────────────────────────
# CSV 읽기 (인코딩 대응)
# ─────────────────────────────────────────────────────────────
@st.cache_data
def read_csv(file):
    """utf-8-sig → cp949 순서로 시도, 실패 시 빈 DataFrame 반환"""
    data = file.getvalue()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except Exception:
            pass
    return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# 열 이름 표준화
# ─────────────────────────────────────────────────────────────
def std_cols(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    rename = {}
    for c in df.columns:
        k = c.lower().replace(" ", "")
        if k in ("time", "categories", "시간", "날짜", "datetime", "date"):
            rename[c] = "time"
        elif k in ("temperature", "온도"):
            rename[c] = "temperature"
        elif k in ("humidity", "습도"):
            rename[c] = "humidity"
        elif k == "ph":
            rename[c] = "ph"
        elif k == "ec":
            rename[c] = "ec"
        elif "생중량" in k:
            rename[c] = "생중량"
        elif "잎" in k:
            rename[c] = "잎 수"
        elif "지상부" in k and "길이" in k:
            rename[c] = "지상부 길이"
        elif "지하부" in k and "길이" in k:
            rename[c] = "지하부 길이"
        elif "지상부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지상부 질량"
        elif "지하부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지하부 질량"
        elif "개체" in k:
            rename[c] = "개체번호"
    df = df.rename(columns=rename)

    # 숫자 변환
    for c in df.columns:
        if c in ("time", "개체번호"):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            num = pd.to_numeric(
                df[c].astype(str).str.replace(",", "")
                .str.extract(r"(-?\d+\.?\d*)")[0],
                errors="coerce",
            )
            if num.notna().mean() >= 0.5:
                df[c] = num

    # 생중량 없으면 계산
    if "생중량" not in df.columns and {"지상부 질량", "지하부 질량"} <= set(df.columns):
        df["생중량"] = df["지상부 질량"] + df["지하부 질량"]

    # 시간 파싱
    if "time" in df.columns:
        t = df["time"].astype(str).str.strip()
        parsed = pd.to_datetime(t, errors="coerce", format="mixed")
        bad = parsed.isna() & t.str.match(r"^\d{8}_\d{1,2}$")
        if bad.any():
            parts = t[bad].str.split("_", expand=True)
            parsed[bad] = pd.to_datetime(parts[0], format="%Y%m%d") + \
                          pd.to_timedelta(parts[1].astype(int), unit="h")
        df["time"] = parsed
    return df


# ─────────────────────────────────────────────────────────────
# 학교명 추출
# ─────────────────────────────────────────────────────────────
def get_school_name(filename):
    base = os.path.splitext(os.path.basename(filename))[0]
    return base.replace("_환경데이터", "").replace("_생육결과데이터", "").strip()


# ─────────────────────────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────────────────────────
st.sidebar.title("📁 데이터 업로드")

env_file = st.sidebar.file_uploader("환경 데이터 CSV", type="csv")
growth_file = st.sidebar.file_uploader("생육 결과 CSV", type="csv")

st.sidebar.markdown("---")
st.sidebar.header("📏 생육 측정 항목")
growth_metrics = st.sidebar.multiselect(
    "비교할 지표 선택 (기본 모두 선택)",
    ["잎 수", "지상부 길이", "지하부 길이", "생중량",
     "지상부 질량", "지하부 질량"],
    default=["잎 수", "지상부 길이", "지하부 길이", "생중량",
             "지상부 질량", "지하부 질량"],
)

st.sidebar.markdown("---")
st.sidebar.info("📌 CSV를 업로드하면 자동으로 분석이 시작됩니다.\n"
                "인코딩(utf-8-sig/cp949)과 열 이름 차이를 자동으로 처리합니다.")


# ─────────────────────────────────────────────────────────────
# 데이터 로딩 (캐싱 + spinner)
# ─────────────────────────────────────────────────────────────
@st.cache_data
def load_data(env_file, growth_file):
    env_df = pd.DataFrame()
    growth_df = pd.DataFrame()
    env_name = ""
    growth_name = ""
    with st.spinner("데이터 로딩 중..."):
        if env_file is not None:
            env_df = std_cols(read_csv(env_file))
            env_name = get_school_name(env_file.name)
        if growth_file is not None:
            growth_df = std_cols(read_csv(growth_file))
            growth_name = get_school_name(growth_file.name)
    return env_df, growth_df, env_name, growth_name


env_df, growth_df, env_name, growth_name = load_data(env_file, growth_file)


# ─────────────────────────────────────────────────────────────
# 탭 구성
# ─────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📖 실험 개요", "🌡️ 환경 데이터", "📊 생육 결과"])


# ═════════════════════════════════════════════════════════════
# 공통 헬퍼: 빈 값 제거 후 최소 개수 체크
# ═════════════════════════════════════════════════════════════
def safe_series(series, min_valid=2):
    """dropna 후 최소 유효 개수 체크, 부족 시 None 반환"""
    s = series.dropna()
    if len(s) < min_valid:
        return None
    return s


# ═════════════════════════════════════════════════════════════
# 공통 헬퍼: 추세선 구하기
# ═════════════════════════════════════════════════════════════
def calc_trendline(x, y):
    """np.polyfit으로 1차 추세선 기울기·절편 계산"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 2:
        return None, None
    slope, intercept = np.polyfit(x, y, 1)
    return slope, intercept


# ═════════════════════════════════════════════════════════════
# 공통 헬퍼: 상관계수
# ═════════════════════════════════════════════════════════════
def safe_corr(x, y):
    """두 시리즈 간 Pearson 상관계수, 유효값 2개 미만 시 None"""
    xs = safe_series(x)
    ys = safe_series(y)
    if xs is None or ys is None:
        return None
    df = pd.concat([xs, ys], axis=1).dropna()
    if len(df) < 2:
        return None
    return df.iloc[:, 0].corr(df.iloc[:, 1])


# ═════════════════════════════════════════════════════════════
# 공통 헬퍼: Plotly 한글 폰트 적용
# ═════════════════════════════════════════════════════════════
def set_korean_font(fig):
    fig.update_layout(
        font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif")
    )
    return fig


# ═════════════════════════════════════════════════════════════
# 공통 헬퍼: CSV 다운로드 버튼
# ═════════════════════════════════════════════════════════════
def download_csv_button(df, label, filename):
    csv_data = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(label, csv_data, file_name=filename,
                       mime="text/csv")


# ═════════════════════════════════════════════════════════════
# 공통 헬퍼: 막대 그래프 (상위·하위 강조)
# ═════════════════════════════════════════════════════════════
def bar_with_highlight(df, x_col, y_col, title,
                       top_n=5, bottom_n=5, color_top="lightgreen",
                       color_mid="steelblue", color_bottom="lightcoral"):
    """평균 막대 그래프: 상위 N개 초록, 하위 N개 분홍, 중간 파랑"""
    d = df[[x_col, y_col]].dropna().copy()
    if len(d) < 2:
        return None
    d = d.sort_values(y_col, ascending=False).reset_index(drop=True)
    fig = go.Figure()
    n = len(d)
    for i, row in d.iterrows():
        if i < top_n:
            color = color_top
        elif i >= n - bottom_n:
            color = color_bottom
        else:
            color = color_mid
        fig.add_bar(
            x=[row[x_col]],
            y=[row[y_col]],
            marker_color=color,
            name=str(row[x_col]),
            showlegend=False,
        )
    fig.update_layout(
        title=title,
        xaxis_title=x_col,
        yaxis_title=y_col,
        height=400,
    )
    set_korean_font(fig)
    return fig


# ═════════════════════════════════════════════════════════════
# 공통 헬퍼: 산점도 + 추세선
# ═════════════════════════════════════════════════════════════
def scatter_with_trend(x, y, x_label, y_label, title, color="steelblue"):
    """산점도 + np.polyfit 추세선"""
    xs = safe_series(x)
    ys = safe_series(y)
    if xs is None or ys is None:
        return None
    df = pd.concat([xs, ys], axis=1).dropna()
    if len(df) < 2:
        return None
    fig = go.Figure()
    fig.add_scatter(
        x=df.iloc[:, 0], y=df.iloc[:, 1],
        mode="markers", marker=dict(color=color, size=8),
        name="데이터",
    )
    slope, intercept = calc_trendline(df.iloc[:, 0], df.iloc[:, 1])
    if slope is not None:
        x_min, x_max = df.iloc[:, 0].min(), df.iloc[:, 0].max()
        x_line = np.linspace(x_min, x_max, 100)
        y_line = slope * x_line + intercept
        fig.add_scatter(
            x=x_line, y=y_line,
            mode="lines", line=dict(color="orange", width=2),
            name=f"추세선 (기울기={slope:.3f})",
        )
    r = safe_corr(x, y)
    if r is not None:
        fig.update_layout(
            title=f"{title}  (상관계수 r = {r:.3f})",
            xaxis_title=x_label,
            yaxis_title=y_label,
            height=400,
        )
    else:
        fig.update_layout(
            title=title,
            xaxis_title=x_label,
            yaxis_title=y_label,
            height=400,
        )
    set_korean_font(fig)
    return fig


# ═════════════════════════════════════════════════════════════
# 공통 헬퍼: 박스플롯
# ═════════════════════════════════════════════════════════════
def boxplot_simple(values, title, y_label, color="steelblue"):
    """단순 박스플롯 (단일 그룹)"""
    s = safe_series(values)
    if s is None:
        return None
    fig = go.Figure()
    fig.add_box(
        y=s.values,
        name=title,
        marker_color=color,
        boxpoints="outliers",
    )
    fig.update_layout(
        title=title,
        yaxis_title=y_label,
        height=400,
        showlegend=False,
    )
    set_korean_font(fig)
    return fig


# ═════════════════════════════════════════════════════════════
# 공통 헬퍼: 요약 표 (환경)
# ═════════════════════════════════════════════════════════════
def env_summary_table(df):
    cols = [c for c in ["temperature", "humidity", "ph", "ec"] if c in df.columns]
    if not cols:
        return None
    rows = []
    for c in cols:
        s = safe_series(df[c], min_valid=1)
        if s is not None:
            rows.append({
                "측정 항목": c,
                "평균": round(s.mean(), 2),
                "최소": round(s.min(), 2),
                "최대": round(s.max(), 2),
                "표준편차": round(s.std(), 2),
            })
    if not rows:
        return None
    return pd.DataFrame(rows)


# ═════════════════════════════════════════════════════════════
# 공통 헬퍼: 일별 시계열
# ═════════════════════════════════════════════════════════════
def daily_timeseries(df, col, title, color="steelblue"):
    """일별 평균 꺾은선 그래프"""
    if "time" not in df.columns or col not in df.columns:
        return None
    d = df[["time", col]].dropna().copy()
    if len(d) < 2:
        return None
    d["date"] = d["time"].dt.date
    daily = d.groupby("date")[col].mean().reset_index()
    if len(daily) < 2:
        return None
    fig = go.Figure()
    fig.add_scatter(
        x=daily["date"], y=daily[col],
        mode="lines+markers",
        line=dict(color=color, width=2),
        marker=dict(size=6),
        name=title,
    )
    fig.update_layout(
        title=title,
        xaxis_title="날짜",
        yaxis_title=col,
        height=350,
    )
    set_korean_font(fig)
    return fig


# ═════════════════════════════════════════════════════════════
# ============================================================
# TAB 1: 실험 개요
# ============================================================
with tab1:
    try:
        st.header("📖 실험 개요")

        # ── 학교명 표시 ──
        school_display = env_name or growth_name or "우리 학교"
        st.subheader(f"🏫 {school_display} 극지식물 연구")

        # ── 연구 배경 및 목적 ──
        st.markdown("""
**연구 배경**
극지식물은 낮은 온도, 건조한 환경, 강한 자외선 등 척박한 조건에서도 살아남는 특별한 식물입니다.
우리 학교에서는 이런 극지식물을 직접 기르며 온도·습도·pH·EC 같은 환경 요인과
잎 수·길이·생중량 같은 생육 지표를 함께 기록하고 있습니다.

**연구 목적**
이 대시보드에서는 우리 학교가 측정한 환경 데이터와 생육 결과 데이터를 바탕으로
* **개체마다 생육이 얼마나 차이 나는지** (평균·표준편차·변동계수)
* **환경 요인과 생육이 어떤 관계가 있는지** (상관계수)
* **잘 자란 개체와 덜 자란 개체의 차이는 무엇인지**

를 알아봅니다.

> 💡 **통계 용어 간단 설명**
> * **평균(mean)**: 모든 값을 더해 개수로 나눈 대표값
> * **표준편차(std)**: 값들이 평균에서 얼마나 흩어져 있는지 나타내는 값
>   (표준편차가 클수록 개체 간 차이가 큼)
> * **변동계수(CV, coefficient of variation)**: 표준편차를 평균으로 나눈 값
>   → 단위가 다른 항목끼리도 흩어진 정도를 비교할 수 있음
> * **상관계수(correlation coefficient, r)**: 두 변수가 함께 어떻게 변하는지 나타냄
>   (−1 ~ +1 사이 값, 0에 가까울수록 관계 약함, +1에 가까울수록 함께 증가)
        """)

        st.markdown("---")

        # ── 데이터 요약 표 ──
        st.subheader("📋 데이터 요약")

        if growth_df.empty and env_df.empty:
            st.info("📁 사이드바에서 CSV 파일을 업로드해주세요.")
        else:
            summary_rows = []

            # 개체 수
            if not growth_df.empty and "개체번호" in growth_df.columns:
                n = growth_df["개체번호"].nunique()
                summary_rows.append({"항목": "총 개체 수", "값": f"{n} 개체"})
            else:
                summary_rows.append({"항목": "총 개체 수", "값": "정보 없음"})

            # 측정 기간 (환경 데이터)
            if not env_df.empty and "time" in env_df.columns:
                times = env_df["time"].dropna()
                if len(times) > 0:
                    start = times.min().strftime("%Y-%m-%d")
                    end = times.max().strftime("%Y-%m-%d")
                    summary_rows.append({"항목": "측정 기간 (환경)", "값": f"{start} ~ {end}"})
                else:
                    summary_rows.append({"항목": "측정 기간 (환경)", "값": "정보 없음"})
            else:
                summary_rows.append({"항목": "측정 기간 (환경)", "값": "환경 CSV 없음"})

            # 측정 항목 (생육)
            if not growth_df.empty:
                measure_cols = [c for c in growth_df.columns
                                if c not in ("개체번호", "time")]
                if measure_cols:
                    summary_rows.append({
                        "항목": "생육 측정 항목",
                        "값": ", ".join(measure_cols)
                    })
                else:
                    summary_rows.append({"항목": "생육 측정 항목", "값": "없음"})
            else:
                summary_rows.append({"항목": "생육 측정 항목", "값": "생육 CSV 없음"})

            st.dataframe(pd.DataFrame(summary_rows), width="stretch")

        st.markdown("---")

        # ── 주요 지표 카드 4개 ──
        st.subheader("📊 주요 지표")

        col1, col2, col3, col4 = st.columns(4)

        # 총 개체수
        if not growth_df.empty and "개체번호" in growth_df.columns:
            n = growth_df["개체번호"].nunique()
            col1.metric("총 개체수", f"{n} 개체")
        else:
            col1.metric("총 개체수", "―")

        # 평균 온도
        if not env_df.empty and "temperature" in env_df.columns:
            t = safe_series(env_df["temperature"], min_valid=1)
            if t is not None:
                col2.metric("평균 온도", f"{t.mean():.1f} °C")
            else:
                col2.metric("평균 온도", "―")
        else:
            col2.metric("평균 온도", "―")

        # 평균 습도
        if not env_df.empty and "humidity" in env_df.columns:
            h = safe_series(env_df["humidity"], min_valid=1)
            if h is not None:
                col3.metric("평균 습도", f"{h.mean():.1f} %")
            else:
                col3.metric("평균 습도", "―")
        else:
            col3.metric("평균 습도", "―")

        # 평균 생중량
        if not growth_df.empty and "생중량" in growth_df.columns:
            gw = safe_series(growth_df["생중량"], min_valid=1)
            if gw is not None:
                col4.metric("평균 생중량", f"{gw.mean():.2f} g")
            else:
                col4.metric("평균 생중량", "―")
        else:
            col4.metric("평균 생중량", "―")

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ═════════════════════════════════════════════════════════════
# ============================================================
# TAB 2: 환경 데이터
# ============================================================
with tab2:
    try:
        st.header("🌡️ 환경 데이터")

        if env_df.empty:
            st.info("📁 사이드바에서 환경 데이터 CSV를 업로드해주세요.")
        else:
            env_available = not env_df.empty

            # ── 환경 요약 표 ──
            st.subheader("📋 환경 요약 (평균 · 최소 · 최대)")
            env_tbl = env_summary_table(env_df)
            if env_tbl is not None and not env_tbl.empty:
                st.dataframe(env_tbl, width="stretch")
            else:
                st.info("표시할 환경 측정 항목(temperature, humidity, ph, ec)이 없습니다.")

            st.markdown("---")

            # ── 날짜별 시계열 ──
            st.subheader("📈 날짜별 환경 변화 (일별 평균)")

            plot_cols = []
            if "temperature" in env_df.columns:
                plot_cols.append(("temperature", "온도 (°C)", "firebrick"))
            if "humidity" in env_df.columns:
                plot_cols.append(("humidity", "습도 (%)", "navy"))

            if plot_cols:
                fig_temp = daily_timeseries(env_df, "temperature", "온도 변화", "firebrick")
                fig_hum = daily_timeseries(env_df, "humidity", "습도 변화", "navy")

                if fig_temp is not None and fig_hum is not None:
                    sub = make_subplots(rows=2, cols=1, subplot_titles=["온도 변화", "습도 변화"])
                    for tr in fig_temp.data:
                        sub.add_trace(tr, row=1, col=1)
                    for tr in fig_hum.data:
                        sub.add_trace(tr, row=2, col=1)
                    sub.update_layout(height=500, showlegend=False)
                    set_korean_font(sub)
                    st.plotly_chart(sub, width="stretch")
                else:
                    for name, unit, color in plot_cols:
                        fig = daily_timeseries(env_df, name, f"{name} 변화", color)
                        if fig is not None:
                            st.plotly_chart(fig, width="stretch")
                        else:
                            st.info(f"{name} 데이터는 표시할 수 없습니다.")
            else:
                st.info("온도·습도 열이 없어 시계열 그래프를 표시할 수 없습니다.")

            # pH·EC 변화 (있을 때만)
            if "ph" in env_df.columns:
                fig_ph = daily_timeseries(env_df, "ph", "pH 변화", "darkgreen")
                if fig_ph is not None:
                    st.plotly_chart(fig_ph, width="stretch")
                else:
                    st.info("pH 데이터는 표시할 수 없습니다.")
            if "ec" in env_df.columns:
                fig_ec = daily_timeseries(env_df, "ec", "EC 변화", "purple")
                if fig_ec is not None:
                    st.plotly_chart(fig_ec, width="stretch")
                else:
                    st.info("EC 데이터는 표시할 수 없습니다.")

            st.markdown("---")

            # ── 원본 테이블 + 다운로드 ──
            with st.expander("📄 환경 데이터 원본 테이블 + CSV 다운로드"):
                st.dataframe(env_df, width="stretch")
                download_csv_button(env_df, "📥 환경 데이터 CSV 다운로드",
                                    f"{env_name}_환경데이터.csv")

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ═════════════════════════════════════════════════════════════
# ============================================================
# TAB 3: 생육 결과
# ============================================================
with tab3:
    try:
        st.header("📊 생육 결과")

        if growth_df.empty:
            st.info("📁 사이드바에서 생육 결과 CSV를 업로드해주세요.")
        else:
            g = growth_df.copy()

            # ── 핵심 결과 카드 ──
            st.subheader("🥇 핵심 결과")

            if "생중량" in g.columns:
                gw = safe_series(g["생중량"], min_valid=1)
                if gw is not None:
                    mean_gw = gw.mean()
                    max_val = gw.max()
                    min_val = gw.min()
                    max_idx = gw.idxmax()
                    min_idx = gw.idxmin()
                    max_id = g.loc[max_idx, "개체번호"] if "개체번호" in g.columns else "?"
                    min_id = g.loc[min_idx, "개체번호"] if "개체번호" in g.columns else "?"

                    col_a, col_b, col_c, col_d = st.columns(4)
                    col_a.metric("평균 생중량", f"{mean_gw:.2f} g")
                    col_b.metric("최대 생중량", f"{max_val:.2f} g\n(개체 {max_id})")
                    col_c.metric("최소 생중량", f"{min_val:.2f} g\n(개체 {min_id})")
                    col_d.metric("개체 간 차이",
                                f"{max_val - min_val:.2f} g\n(최대−최소)")
                else:
                    st.info("생중량 데이터가 충분하지 않습니다.")
            else:
                st.info("생중량(또는 지상부 질량 + 지하부 질량) 열이 없어 핵심 결과를 표시할 수 없습니다.")

            st.markdown("---")

            # ── 개체별 생육 비교 (막대 그래프) ──
            st.subheader("🌿 개체별 생육 비교 (막대 그래프)")

            metric_map = {
                "잎 수": "잎 수",
                "지상부 길이": "지상부 길이",
                "지하부 길이": "지하부 길이",
                "생중량": "생중량",
                "지상부 질량": "지상부 질량",
                "지하부 질량": "지하부 질량",
            }

            # 사용자가 선택한 지표만 표시 (기본값 유지)
            selected = [metric_map[m] for m in growth_metrics if m in metric_map]

            if not selected:
                selected = ["잎 수", "지상부 길이", "지하부 길이", "생중량"]

            for metric in selected:
                if metric not in g.columns:
                    st.info(f"⚠️ '{metric}' 열이 데이터에 없습니다.")
                    continue
                fig = bar_with_highlight(
                    g, "개체번호", metric,
                    f"개체별 {metric}",
                    top_n=5, bottom_n=5,
                )
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.info(f"{metric} 그래프는 표시할 수 없습니다.")

            st.markdown("---")

            # ── 생중량 분포 (박스플롯) ──
            st.subheader("📦 생중량 분포")

            if "생중량" in g.columns:
                s = safe_series(g["생중량"])
                if s is not None:
                    fig_box = boxplot_simple(g["생중량"], "생중량 분포 (박스플롯)", "생중량 (g)")
                    if fig_box is not None:
                        st.plotly_chart(fig_box, width="stretch")

                    # 통계 수치
                    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                    col_s1.metric("평균", f"{s.mean():.2f} g")
                    col_s2.metric("중앙값", f"{s.median():.2f} g")
                    col_s3.metric("표준편차",
                                  f"{s.std():.2f} g\n(값들이 평균에서 얼마나 흩어져 있는지)")
                    col_s4.metric("변동계수(CV)",
                                  f"{s.std()/s.mean()*100:.1f}%\n(단위 다른 항목끼리 비교 가능)")
                else:
                    st.info("생중량 데이터가 충분하지 않습니다.")
            else:
                st.info("생중량 열이 없습니다.")

            # 바이올린 플롯 (선택 사항)
            if "생중량" in g.columns:
                s2 = safe_series(g["생중량"])
                if s2 is not None and len(s2) >= 5:
                    fig_vio = go.Figure()
                    fig_vio.add_violin(
                        y=s2.values,
                        name="생중량",
                        box_visible=True,
                        meanline_visible=True,
                        fillcolor="lightsteelblue",
                    )
                    fig_vio.update_layout(
                        title="생중량 분포 (바이올린 플롯)",
                        yaxis_title="생중량 (g)",
                        height=400,
                        showlegend=False,
                    )
                    set_korean_font(fig_vio)
                    st.plotly_chart(fig_vio, width="stretch")

            st.markdown("---")

            # ── 상관관계 분석 ──
            st.subheader("🔗 상관관계 분석 (산점도 + 추세선)")

            st.markdown("""
**상관계수(r)란?**
두 숫자가 함께 어떻게 변하는지를 −1에서 +1 사이 값으로 나타냅니다.
* r이 **+1에 가까우면**: 한 값이 커질 때 다른 값도 함께 커짐 (양의 상관)
* r이 **−1에 가까우면**: 한 값이 커질 때 다른 값은 작아짐 (음의 상관)
* r이 **0에 가까우면**: 두 값 사이에 뚜렷한 관계가 없음

> 💡 r의 절댓값이 0.7 이상이면 '강한 상관', 0.3~0.7은 '중간 정도',
> 0.3 미만은 '약한 상관'으로 보통 해석합니다. (해석은 연구 목적에 따라 달라질 수 있어요.)
            """)

            pairs = []
            if "잎 수" in g.columns and "생중량" in g.columns:
                pairs.append(("잎 수", "생중량", "잎 수 (장)", "생중량 (g)",
                              "잎 수 vs 생중량"))
            if "지상부 길이" in g.columns and "생중량" in g.columns:
                pairs.append(("지상부 길이", "생중량", "지상부 길이 (mm)",
                              "생중량 (g)", "지상부 길이 vs 생중량"))

            if pairs:
                for x_col, y_col, x_lbl, y_lbl, ttl in pairs:
                    fig_s = scatter_with_trend(
                        g[x_col], g[y_col], x_lbl, y_lbl, ttl
                    )
                    if fig_s is not None:
                        st.plotly_chart(fig_s, width="stretch")
                    else:
                        st.info(f"{ttl} 그래프는 표시할 수 없습니다.")
            else:
                st.info("잎 수·지상부 길이와 생중량을 함께 비교할 수 있는 열이 충분하지 않습니다.")

            st.markdown("---")

            # ── 상위 25% vs 하위 25% 비교 ──
            if "생중량" in g.columns:
                gw = safe_series(g["생중량"])
                if gw is not None and len(gw) >= 4:
                    q75 = gw.quantile(0.75)
                    q25 = gw.quantile(0.25)
                    top_mask = g["생중량"] >= q75
                    bottom_mask = g["생중량"] <= q25

                    top_n = top_mask.sum()
                    bottom_n = bottom_mask.sum()

                    st.subheader("🏆 생중량 상위 25% vs 하위 25% 비교")

                    if top_n > 0 and bottom_n > 0:
                        comp_rows = []
                        comp_rows.append({"그룹": "상위 25% (잘 자란 개체)",
                                          "개체 수": f"{top_n} 개체",
                                          "평균 생중량": f"{g.loc[top_mask, '생중량'].mean():.2f} g"})
                        comp_rows.append({"그룹": "하위 25% (덜 자란 개체)",
                                          "개체 수": f"{bottom_n} 개체",
                                          "평균 생중량": f"{g.loc[bottom_mask, '생중량'].mean():.2f} g"})
                        comp_rows.append({"그룹": "차이",
                                          "개체 수": "",
                                          "평균 생중량":
                                              f"{g.loc[top_mask, '생중량'].mean() - g.loc[bottom_mask, '생중량'].mean():.2f} g"})
                        st.dataframe(pd.DataFrame(comp_rows), width="stretch")

                        # 막대 비교 그래프
                        fig_comp = go.Figure()
                        fig_comp.add_bar(
                            x=["상위 25%", "하위 25%"],
                            y=[g.loc[top_mask, '생중량'].mean(),
                               g.loc[bottom_mask, '생중량'].mean()],
                            marker_color=["lightgreen", "lightcoral"],
                            name="평균 생중량",
                        )
                        fig_comp.update_layout(
                            title="상위 25% vs 하위 25% 평균 생중량 비교",
                            yaxis_title="평균 생중량 (g)",
                            height=350,
                        )
                        set_korean_font(fig_comp)
                        st.plotly_chart(fig_comp, width="stretch")
                    else:
                        st.info("상위/하위 25%를 나눌 만큼 데이터가 충분하지 않습니다.")

            st.markdown("---")

            # ── 원본 테이블 + 다운로드 ──
            with st.expander("📄 생육 데이터 원본 테이블 + CSV 다운로드"):
                st.dataframe(g, width="stretch")
                download_csv_button(g, "📥 생육 데이터 CSV 다운로드",
                                    f"{growth_name}_생육결과데이터.csv")

    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")


# ─────────────────────────────────────────────────────────────
# 푸터
# ─────────────────────────────────────────────────────────────
st.markdown("---")
st.caption("🌱 극지식물 생육 분석 대시보드  |  데이터 기반 탐색 도구 (교육용)")
