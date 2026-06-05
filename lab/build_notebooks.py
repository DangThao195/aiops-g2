from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "lab"
NOTEBOOKS = LAB / "notebooks"
PLOTS = LAB / "plots"
RESULTS = LAB / "results"
DATA = ROOT / "g2-data" / "g2"
METRICS = DATA / "metrics"
LOGS = DATA / "logs"


def cell_markdown(source: str) -> dict:
    clean = textwrap.dedent(source).strip()
    return {"cell_type": "markdown", "metadata": {}, "source": clean.splitlines(True)}


def cell_code(source: str) -> dict:
    clean = textwrap.dedent(source).strip()
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": clean.splitlines(True),
    }


def cell_image(title: str, filename: str) -> dict:
    return cell_markdown(f"**{title}**\n\n![{title}](../plots/{filename})")


def write_notebook(path: Path, cells: list[dict]) -> None:
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8")


def format_time_axis(ax, interval: int = 3) -> None:
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.tick_params(axis="x", labelrotation=0, labelsize=8, labelbottom=True)


def load_metrics() -> dict[str, pd.DataFrame]:
    services = {}
    for path in sorted(METRICS.glob("*.csv")):
        service = path.stem
        df = pd.read_csv(path)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        services[service] = df
    services["cart-service"]["memory_pct"] = (
        100
        * services["cart-service"]["memory_usage_bytes"]
        / services["cart-service"]["memory_limit_bytes"]
    )
    services["cart-service"]["restart_delta"] = (
        services["cart-service"]["container_restart_count"].diff().fillna(0)
    )
    return services


def save_eda_plots() -> None:
    services = load_metrics()

    fig, ax = plt.subplots(figsize=(13, 5))
    for name, df in services.items():
        if "http_requests_per_sec" in df:
            ax.plot(df["timestamp"], df["http_requests_per_sec"], label=name, linewidth=1)
    ax.set_title("Request rate theo service")
    ax.set_ylabel("requests/sec")
    ax.grid(True, alpha=0.25)
    ax.legend(ncol=3, fontsize=8)
    format_time_axis(ax)
    fig.tight_layout()
    fig.savefig(PLOTS / "01_eda_request_rates.png", dpi=160)
    plt.close(fig)

    cart = services["cart-service"]
    fig, axes = plt.subplots(4, 1, figsize=(13, 10), sharex=True)
    axes[0].plot(cart["timestamp"], cart["memory_pct"], color="#1f77b4")
    axes[0].axhline(70, color="#d62728", linestyle="--", linewidth=1)
    axes[0].set_ylabel("memory %")
    axes[1].plot(cart["timestamp"], cart["jvm_gc_pause_ms_avg"], color="#9467bd")
    axes[1].axhline(100, color="#d62728", linestyle="--", linewidth=1)
    axes[1].set_ylabel("GC ms")
    axes[2].plot(cart["timestamp"], cart["http_p99_latency_ms"], color="#ff7f0e")
    axes[2].set_ylabel("p99 ms")
    axes[3].plot(cart["timestamp"], cart["http_5xx_rate"], color="#d62728")
    axes[3].bar(cart["timestamp"], cart["restart_delta"] * 5, width=0.015, color="#111111", alpha=0.45)
    axes[3].set_ylabel("5xx / restart")
    for ax in axes:
        ax.grid(True, alpha=0.25)
        format_time_axis(ax)
    fig.suptitle("Cart-service: memory, GC, latency, 5xx và restart")
    fig.tight_layout()
    fig.savefig(PLOTS / "01_eda_cart_core_metrics.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(
        services["api-gateway"]["timestamp"],
        services["api-gateway"]["cart_upstream_error_rate"],
        label="api-gateway cart_upstream_error_rate",
    )
    ax.plot(
        services["order-service"]["timestamp"],
        services["order-service"]["upstream_timeout_rate"],
        label="order upstream_timeout_rate",
    )
    ax.plot(
        services["payment-service"]["timestamp"],
        services["payment-service"]["upstream_timeout_rate"],
        label="payment upstream_timeout_rate",
    )
    ax.axhline(5, color="#888888", linestyle="--", linewidth=1)
    ax.set_title("Downstream/upstream failures sau khi cart-service bất ổn")
    ax.set_ylabel("rate %")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    format_time_axis(ax)
    fig.tight_layout()
    fig.savefig(PLOTS / "01_eda_downstream_failures.png", dpi=160)
    plt.close(fig)

    product = services["product-service"]
    fig, axes = plt.subplots(3, 1, figsize=(13, 8), sharex=True)
    axes[0].plot(product["timestamp"], product["http_p99_latency_ms"], color="#ff7f0e")
    axes[0].axhline(100, color="#d62728", linestyle="--", linewidth=1)
    axes[0].set_ylabel("p99 ms")
    axes[1].plot(product["timestamp"], product["http_5xx_rate"], color="#d62728")
    axes[1].axhline(5, color="#d62728", linestyle="--", linewidth=1)
    axes[1].set_ylabel("5xx %")
    axes[2].plot(product["timestamp"], product["cpu_usage_percent"], color="#2ca02c")
    axes[2].axhline(60, color="#d62728", linestyle="--", linewidth=1)
    axes[2].set_ylabel("CPU %")
    for ax in axes:
        ax.grid(True, alpha=0.25)
        format_time_axis(ax)
    fig.suptitle("Product-service early suspicious signal")
    fig.tight_layout()
    fig.savefig(PLOTS / "01_eda_product_service_anomaly.png", dpi=160)
    plt.close(fig)


def save_anomaly_plots() -> None:
    services = load_metrics()
    cart = services["cart-service"]

    def rolling_z(series: pd.Series, window: int = 120) -> pd.Series:
        baseline = series.shift(1).rolling(window=window, min_periods=60)
        return (series - baseline.mean()) / baseline.std()

    fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=True)
    metrics = [
        ("memory_pct", "memory %"),
        ("jvm_gc_pause_ms_avg", "GC pause ms"),
        ("http_p99_latency_ms", "p99 latency ms"),
    ]
    for ax, (metric, label) in zip(axes, metrics):
        z = rolling_z(cart[metric].astype(float))
        ax.plot(cart["timestamp"], z, color="#1f77b4", linewidth=1)
        ax.axhline(3, color="#d62728", linestyle="--", linewidth=1)
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.25)
        format_time_axis(ax)
    fig.suptitle("Rolling Z-score trên các metric chính của cart-service")
    fig.tight_layout()
    fig.savefig(PLOTS / "02_metric_rolling_z_cart.png", dpi=160)
    plt.close(fig)

    if_path = RESULTS / "isolation_forest_cart_anomalies.csv"
    if if_path.exists():
        first_if = pd.read_csv(if_path)["first_anomaly_timestamp"].iloc[0]
    else:
        first_if = "2026-06-01T18:04:30Z"

    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(cart["timestamp"], cart["memory_pct"], label="memory %", color="#1f77b4")
    ax2 = ax.twinx()
    ax2.plot(cart["timestamp"], cart["jvm_gc_pause_ms_avg"], label="GC pause", color="#9467bd", alpha=0.75)
    ax.axvline(pd.to_datetime(first_if, utc=True), color="#111111", linestyle="--", label="Isolation Forest first anomaly")
    ax.axhline(70, color="#d62728", linestyle=":", linewidth=1)
    ax.set_title("Isolation Forest anomaly đặt trên memory và GC của cart-service")
    ax.set_ylabel("memory %")
    ax2.set_ylabel("GC pause ms")
    ax.grid(True, alpha=0.25)
    format_time_axis(ax)
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(PLOTS / "02_metric_isolation_forest_cart.png", dpi=160)
    plt.close(fig)


def load_log_events(path: Path) -> pd.DataFrame:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            rows.append(event)
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def save_log_plots() -> None:
    cart = load_log_events(LOGS / "cart-service.log.jsonl")
    order = load_log_events(LOGS / "order-service.log.jsonl")

    cart["hour"] = cart["timestamp"].dt.floor("h")
    level_hour = cart.groupby(["hour", "level"]).size().unstack(fill_value=0)
    fig, ax = plt.subplots(figsize=(13, 5))
    level_hour.plot(kind="area", stacked=True, ax=ax, linewidth=0)
    ax.set_title("Cart-service log volume theo level")
    ax.set_ylabel("log count/hour")
    ax.grid(True, alpha=0.25)
    format_time_axis(ax)
    fig.tight_layout()
    fig.savefig(PLOTS / "03_log_cart_levels_by_hour.png", dpi=160)
    plt.close(fig)

    patterns = {
        "cache eviction": "ProductCatalogCache eviction failed",
        "GC warning": "GC overhead limit warning",
        "slow response": "Slow response detected",
        "OOM imminent": "OutOfMemoryError imminent",
        "OOMKilled": "Container OOMKilled",
    }
    fig, ax = plt.subplots(figsize=(13, 6))
    for label, needle in patterns.items():
        matched = cart[cart["message"].str.contains(re.escape(needle), regex=True)]
        counts = matched.set_index("timestamp").resample("30min").size()
        ax.plot(counts.index, counts.values, label=label, linewidth=1.4)
    ax.set_title("Cart-service log template counts theo bucket 30 phút")
    ax.set_ylabel("count/30min")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    format_time_axis(ax)
    fig.tight_layout()
    fig.savefig(PLOTS / "03_log_cart_template_spikes.png", dpi=160)
    plt.close(fig)

    order_patterns = {
        "cart timeout": "Cart service timeout",
        "cart returned 5xx": "Cart service returned 5xx",
    }
    fig, ax = plt.subplots(figsize=(13, 5))
    for label, needle in order_patterns.items():
        matched = order[order["message"].str.contains(re.escape(needle), regex=True)]
        counts = matched.set_index("timestamp").resample("30min").size()
        ax.plot(counts.index, counts.values, label=label, linewidth=1.4)
    ax.set_title("Order-service log patterns liên quan tới cart-service")
    ax.set_ylabel("count/30min")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    format_time_axis(ax)
    fig.tight_layout()
    fig.savefig(PLOTS / "03_log_order_cart_failures.png", dpi=160)
    plt.close(fig)

    numeric = cart[
        cart["message"].str.contains(
            "ProductCatalogCache|OutOfMemoryError|OOMKilled", regex=True
        )
    ].copy()
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    if "cache_size_mb" in numeric:
        cache = numeric.dropna(subset=["cache_size_mb"]).set_index("timestamp")["cache_size_mb"]
        cache_30m = cache.resample("30min").agg(["median", "max"])
        axes[0].plot(cache_30m.index, cache_30m["median"], label="median cache_size_mb", color="#1f77b4")
        axes[0].plot(cache_30m.index, cache_30m["max"], label="max cache_size_mb", color="#ff7f0e")
        axes[0].axhline(1800, color="#d62728", linestyle="--", linewidth=1, label="~1.8 GB")
        axes[0].set_ylabel("cache MB")
        axes[0].legend(fontsize=8)
    if "heap_used_mb" in numeric:
        heap = numeric.dropna(subset=["heap_used_mb"]).set_index("timestamp")["heap_used_mb"]
        heap_30m = heap.resample("30min").agg(["median", "max"])
        axes[1].plot(heap_30m.index, heap_30m["median"], label="median heap_used_mb", color="#9467bd")
        axes[1].plot(heap_30m.index, heap_30m["max"], label="max heap_used_mb", color="#d62728")
        axes[1].axhline(2048, color="#111111", linestyle="--", linewidth=1, label="2 GB limit")
        axes[1].set_ylabel("heap MB")
        axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(True, alpha=0.25)
        format_time_axis(ax)
    fig.suptitle("Cart-service cache_size_mb và heap_used_mb từ log")
    fig.tight_layout()
    fig.savefig(PLOTS / "03_log_cart_cache_heap_fields.png", dpi=160)
    plt.close(fig)


def save_timeline_plots() -> None:
    timeline = pd.read_csv(RESULTS / "incident_timeline.csv")
    timeline["timestamp_dt"] = pd.to_datetime(timeline["timestamp"], utc=True, format="mixed")
    service_y = {name: idx for idx, name in enumerate(timeline["service"].unique())}
    timeline["y"] = timeline["service"].map(service_y)

    fig, ax = plt.subplots(figsize=(13, 6))
    ax.scatter(timeline["timestamp_dt"], timeline["y"], s=80, color="#1f77b4")
    for _, row in timeline.iterrows():
        ax.text(row["timestamp_dt"], row["y"] + 0.08, row["evidence"], fontsize=7, rotation=25, ha="left")
    ax.set_yticks(list(service_y.values()), list(service_y.keys()))
    ax.set_title("Cross-signal incident timeline")
    ax.grid(True, axis="x", alpha=0.25)
    format_time_axis(ax)
    fig.tight_layout()
    fig.savefig(PLOTS / "04_incident_cross_signal_timeline.png", dpi=160)
    plt.close(fig)

    first_anomaly = (
        timeline.sort_values("timestamp_dt")
        .groupby("service", as_index=False)
        .first()[["service", "timestamp", "evidence", "timestamp_dt"]]
        .rename(columns={"evidence": "meaning"})
    )
    first_anomaly["timestamp_dt"] = pd.to_datetime(first_anomaly["timestamp"], utc=True, format="mixed")
    start = first_anomaly["timestamp_dt"].min()
    first_anomaly["hours_since_first"] = (first_anomaly["timestamp_dt"] - start).dt.total_seconds() / 3600
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(first_anomaly["service"], first_anomaly["hours_since_first"], color="#4c78a8")
    ax.set_xlabel("giờ sau signal đầu tiên")
    ax.set_title("Xếp hạng first anomaly theo service")
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(PLOTS / "04_service_first_anomaly_ranking.png", dpi=160)
    plt.close(fig)


def notebook_01() -> list[dict]:
    return [
        cell_markdown(
            """
            # 01 - EDA Metrics

            Mục tiêu notebook này là đọc toàn bộ metrics, kiểm tra chất lượng dữ liệu, hiểu schema từng service, và vẽ các metric chính trước khi chạy anomaly detector.

            Trong bài này, chúng ta phân tích **metrics trước** vì metrics là tín hiệu định lượng theo thời gian. Metrics giúp trả lời hai câu hỏi đầu:

            - **WHEN**: anomaly bắt đầu từ khi nào?
            - **WHERE**: service nào có dấu hiệu bất thường trước?
            """
        ),
        cell_code(
            """
            from pathlib import Path
            import pandas as pd
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates

            def find_project_root():
                cwd = Path.cwd().resolve()
                for candidate in [cwd, *cwd.parents]:
                    if (candidate / "g2-data" / "g2").exists():
                        return candidate
                raise FileNotFoundError("Cannot find project root containing g2-data/g2")

            ROOT = find_project_root()
            DATA = ROOT / "g2-data" / "g2"
            METRICS = DATA / "metrics"
            PLOTS = ROOT / "lab" / "plots"
            PLOTS.mkdir(parents=True, exist_ok=True)

            def format_time_axis(ax, interval=3):
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=interval))
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
                ax.tick_params(axis="x", labelrotation=0, labelsize=8, labelbottom=True)

            def load_all_metrics():
                loaded = {}
                for path in sorted(METRICS.glob("*.csv")):
                    df = pd.read_csv(path)
                    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                    loaded[path.stem] = df
                return loaded

            def ensure_services():
                if "services" not in globals() or not services:
                    return load_all_metrics()
                return services

            services = load_all_metrics()

            sorted(services)
            """
        ),
        cell_markdown("## 1.1 Kiểm tra schema và số dòng"),
        cell_code(
            """
            services = ensure_services()

            overview = []
            for service, df in services.items():
                overview.append({
                    "service": service,
                    "rows": len(df),
                    "columns": ", ".join(df.columns),
                    "start": df["timestamp"].min(),
                    "end": df["timestamp"].max(),
                    "nulls": int(df.isna().sum().sum()),
                    "unique_timestamps": df["timestamp"].nunique(),
                })
            pd.DataFrame(overview)
            """
        ),
        cell_markdown("## 1.2 Kiểm tra gap timestamp"),
        cell_code(
            """
            services = ensure_services()

            gaps = []
            for service, df in services.items():
                diffs = df["timestamp"].diff()
                bad = df[diffs > pd.Timedelta(seconds=30)]
                for idx, row in bad.iterrows():
                    prev = df.loc[idx - 1, "timestamp"]
                    missing = int((row["timestamp"] - prev).total_seconds() / 30) - 1
                    gaps.append({
                        "service": service,
                        "gap_start_after": prev,
                        "next_timestamp": row["timestamp"],
                        "missing_30s_points": missing,
                    })
            pd.DataFrame(gaps)
            """
        ),
        cell_markdown(
            """
            Kết quả cho thấy tất cả file metrics đều thiếu 60 điểm từ `11:30Z` đến `11:59:30Z`. Gap này cần ghi vào report, nhưng không che mất failure window chính vì incident rõ nhất xảy ra từ sau `14:00Z`.
            """
        ),
        cell_markdown("## 1.3 Thống kê min/median/mean/max từng metric"),
        cell_code(
            """
            services = ensure_services()

            rows = []
            for service, df in services.items():
                for col in df.columns:
                    if col == "timestamp":
                        continue
                    rows.append({
                        "service": service,
                        "metric": col,
                        "min": df[col].min(),
                        "median": df[col].median(),
                        "mean": df[col].mean(),
                        "max": df[col].max(),
                        "max_at": df.loc[df[col].idxmax(), "timestamp"],
                    })
            metric_summary = pd.DataFrame(rows)
            metric_summary
            """
        ),
        cell_markdown("## 1.4 Request rate theo service"),
        cell_code(
            """
            services = ensure_services()

            fig, ax = plt.subplots(figsize=(13, 5))
            for name, df in services.items():
                if "http_requests_per_sec" in df:
                    ax.plot(df["timestamp"], df["http_requests_per_sec"], label=name, linewidth=1)
            ax.set_title("Request rate theo service")
            ax.set_ylabel("requests/sec")
            ax.grid(True, alpha=0.25)
            ax.legend(ncol=3, fontsize=8)
            format_time_axis(ax)
            fig.tight_layout()
            fig.savefig(PLOTS / "01_eda_request_rates.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Request rate theo service", "01_eda_request_rates.png"),
        cell_markdown("## 1.5 Cart-service core metrics"),
        cell_code(
            """
            services = ensure_services()

            cart = services["cart-service"].copy()
            cart["memory_pct"] = 100 * cart["memory_usage_bytes"] / cart["memory_limit_bytes"]
            cart["restart_delta"] = cart["container_restart_count"].diff().fillna(0)

            fig, axes = plt.subplots(4, 1, figsize=(13, 10), sharex=True)
            axes[0].plot(cart["timestamp"], cart["memory_pct"], color="#1f77b4")
            axes[0].axhline(70, color="#d62728", linestyle="--", linewidth=1)
            axes[0].set_ylabel("memory %")
            axes[1].plot(cart["timestamp"], cart["jvm_gc_pause_ms_avg"], color="#9467bd")
            axes[1].axhline(100, color="#d62728", linestyle="--", linewidth=1)
            axes[1].set_ylabel("GC ms")
            axes[2].plot(cart["timestamp"], cart["http_p99_latency_ms"], color="#ff7f0e")
            axes[2].set_ylabel("p99 ms")
            axes[3].plot(cart["timestamp"], cart["http_5xx_rate"], color="#d62728")
            axes[3].bar(cart["timestamp"], cart["restart_delta"] * 5, width=0.015, color="#111111", alpha=0.45)
            axes[3].set_ylabel("5xx/restart")
            for ax in axes:
                ax.grid(True, alpha=0.25)
                format_time_axis(ax)
            fig.suptitle("Cart-service: memory, GC, latency, 5xx và restart")
            fig.tight_layout()
            fig.savefig(PLOTS / "01_eda_cart_core_metrics.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Cart-service core metrics", "01_eda_cart_core_metrics.png"),
        cell_markdown(
            """
            Nhìn EDA ban đầu, `cart-service` có chuỗi rất đáng nghi: latency tăng trước, GC tăng, memory tăng, sau đó mới đến restart và 5xx. Đây là dấu hiệu của resource pressure, không chỉ là lỗi HTTP đơn thuần.
            """
        ),
        cell_markdown("## 1.6 Downstream failures"),
        cell_code(
            """
            services = ensure_services()

            fig, ax = plt.subplots(figsize=(13, 5))
            ax.plot(services["api-gateway"]["timestamp"], services["api-gateway"]["cart_upstream_error_rate"], label="gateway cart_upstream_error_rate")
            ax.plot(services["order-service"]["timestamp"], services["order-service"]["upstream_timeout_rate"], label="order upstream_timeout_rate")
            ax.plot(services["payment-service"]["timestamp"], services["payment-service"]["upstream_timeout_rate"], label="payment upstream_timeout_rate")
            ax.set_title("Downstream/upstream failures sau khi cart-service bất ổn")
            ax.set_ylabel("rate %")
            ax.grid(True, alpha=0.25)
            ax.legend(fontsize=8)
            format_time_axis(ax)
            fig.tight_layout()
            fig.savefig(PLOTS / "01_eda_downstream_failures.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Downstream failures", "01_eda_downstream_failures.png"),
        cell_markdown("## 1.7 Product-service early suspicious signal"),
        cell_code(
            """
            services = ensure_services()

            product = services["product-service"]
            fig, axes = plt.subplots(3, 1, figsize=(13, 8), sharex=True)
            axes[0].plot(product["timestamp"], product["http_p99_latency_ms"], color="#ff7f0e")
            axes[0].axhline(100, color="#d62728", linestyle="--", linewidth=1)
            axes[0].set_ylabel("p99 ms")
            axes[1].plot(product["timestamp"], product["http_5xx_rate"], color="#d62728")
            axes[1].axhline(5, color="#d62728", linestyle="--", linewidth=1)
            axes[1].set_ylabel("5xx %")
            axes[2].plot(product["timestamp"], product["cpu_usage_percent"], color="#2ca02c")
            axes[2].axhline(60, color="#d62728", linestyle="--", linewidth=1)
            axes[2].set_ylabel("CPU %")
            for ax in axes:
                ax.grid(True, alpha=0.25)
                format_time_axis(ax)
            fig.suptitle("Product-service early suspicious signal")
            fig.tight_layout()
            fig.savefig(PLOTS / "01_eda_product_service_anomaly.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Product-service early suspicious signal", "01_eda_product_service_anomaly.png"),
        cell_markdown(
            """
            `product-service` có anomaly sớm khoảng `03:03Z`. Tuy nhiên ở bước EDA ta chỉ gọi đây là **early suspicious signal / possible trigger**, chưa gọi là root cause vì chưa có log/trace chứng minh quan hệ trực tiếp với cart.
            """
        ),
    ]


def notebook_02() -> list[dict]:
    return [
        cell_markdown(
            """
            # 02 - Metric Anomaly Detection

            Notebook này dùng detector registry để tránh chọn thuật toán theo cảm tính cho từng incident.

            Luồng chính:

            1. `metric_detector_map`: map metric family với detector phù hợp.
            2. Baseline IQR và EWMA là detector chính vì data-driven hơn fixed threshold.
            3. Threshold chỉ dùng như operational confirmation/severity rule.
            4. Isolation Forest dùng làm supporting multivariate detector.
            """
        ),
        cell_code(
            """
            from pathlib import Path
            import numpy as np
            import pandas as pd
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler

            def find_project_root():
                cwd = Path.cwd().resolve()
                for candidate in [cwd, *cwd.parents]:
                    if (candidate / "g2-data" / "g2").exists():
                        return candidate
                raise FileNotFoundError("Cannot find project root containing g2-data/g2")

            ROOT = find_project_root()
            DATA = ROOT / "g2-data" / "g2"
            METRICS = DATA / "metrics"
            PLOTS = ROOT / "lab" / "plots"
            RESULTS = ROOT / "lab" / "results"
            PLOTS.mkdir(parents=True, exist_ok=True)
            RESULTS.mkdir(parents=True, exist_ok=True)

            def format_time_axis(ax, interval=3):
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=interval))
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
                ax.tick_params(axis="x", labelrotation=0, labelsize=8, labelbottom=True)

            def load_metric(name):
                df = pd.read_csv(METRICS / f"{name}.csv")
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                return df

            cart = load_metric("cart-service")
            cart["memory_pct"] = 100 * cart["memory_usage_bytes"] / cart["memory_limit_bytes"]
            cart["restart_delta"] = cart["container_restart_count"].diff().fillna(0)
            """
        ),
        cell_markdown("## 2.1 Detector registry"),
        cell_code(
            """
            metric_detector_map = {
                "cpu_usage_percent": ["baseline_iqr", "ewma"],
                "memory_pct": ["baseline_iqr", "ewma"],
                "jvm_gc_pause_ms_avg": ["baseline_iqr", "ewma"],
                "http_p99_latency_ms": ["baseline_iqr", "ewma", "rolling_iqr"],
                "http_5xx_rate": ["baseline_iqr", "rolling_iqr"],
                "upstream_timeout_rate": ["baseline_iqr", "rolling_iqr"],
                "cart_upstream_error_rate": ["baseline_iqr", "rolling_iqr"],
                "product_upstream_error_rate": ["baseline_iqr", "rolling_iqr"],
                "active_connections": ["rolling_iqr"],
                "http_requests_per_sec": ["rolling_iqr"],
                "restart_delta": ["counter_delta"],
            }
            metric_detector_map
            """
        ),
        cell_markdown(
            """
            Ý tưởng: detector không được hard-code riêng cho `cart-service`. Metric nào có trong service thì detector tương ứng được chạy. Ví dụ memory/GC dùng baseline IQR/EWMA để bắt drift, latency/error dùng baseline hoặc rolling band, restart count dùng counter delta.
            """
        ),
        cell_markdown("## 2.2 Baseline IQR / EWMA signals"),
        cell_code(
            """
            def first_sustained_mask(mask, points=3):
                sustained = mask.rolling(points).sum() >= points
                if not sustained.any():
                    return None
                return int(np.where(sustained)[0][0] - points + 1)

            def baseline_iqr_signal(df, metric, baseline_hours=6, multiplier=3.0, points=3):
                s = df[metric].astype(float)
                start = df["timestamp"].min()
                baseline_mask = df["timestamp"] < start + pd.Timedelta(hours=baseline_hours)
                baseline = s[baseline_mask].dropna()
                if len(baseline) < 60:
                    return None
                q1, q3 = baseline.quantile(0.25), baseline.quantile(0.75)
                iqr = q3 - q1
                if iqr == 0:
                    return None
                upper = q3 + multiplier * iqr
                score = (s - q3) / iqr
                idx = first_sustained_mask((s > upper) & (~baseline_mask), points)
                if idx is None:
                    return None
                return df.loc[idx, "timestamp"], s.iloc[idx], score.iloc[idx]

            def ewma_signal(df, metric, span=120, z_threshold=4.0, points=3):
                s = df[metric].astype(float)
                mean = s.shift(1).ewm(span=span, min_periods=60, adjust=False).mean()
                std = s.shift(1).ewm(span=span, min_periods=60, adjust=False).std()
                z = (s - mean) / std.replace(0, np.nan)
                idx = first_sustained_mask(z >= z_threshold, points)
                if idx is None:
                    return None
                return df.loc[idx, "timestamp"], s.iloc[idx], z.iloc[idx]

            def rolling_iqr_signal(df, metric, window=120, multiplier=3.0, points=3):
                s = df[metric].astype(float)
                baseline = s.shift(1).rolling(window=window, min_periods=60)
                q1 = baseline.quantile(0.25)
                q3 = baseline.quantile(0.75)
                iqr = q3 - q1
                upper = q3 + multiplier * iqr
                score = (s - q3) / iqr.replace(0, np.nan)
                idx = first_sustained_mask(s > upper, points)
                if idx is None:
                    return None
                return df.loc[idx, "timestamp"], s.iloc[idx], score.iloc[idx]

            services = {}
            for name in ["cart-service", "order-service", "payment-service", "api-gateway", "product-service"]:
                df = load_metric(name)
                if "memory_usage_bytes" in df and "memory_limit_bytes" in df:
                    df["memory_pct"] = 100 * df["memory_usage_bytes"] / df["memory_limit_bytes"]
                if "container_restart_count" in df:
                    df["restart_delta"] = df["container_restart_count"].diff().fillna(0)
                services[name] = df

            rows = []
            for service, df in services.items():
                for metric, detectors in metric_detector_map.items():
                    if metric not in df:
                        continue
                    for detector in detectors:
                        result = None
                        if detector == "baseline_iqr":
                            result = baseline_iqr_signal(df, metric)
                        elif detector == "ewma":
                            result = ewma_signal(df, metric)
                        elif detector == "rolling_iqr":
                            result = rolling_iqr_signal(df, metric)
                        elif detector == "counter_delta":
                            hits = df[df[metric] > 0]
                            if not hits.empty:
                                result = (hits["timestamp"].iloc[0], hits[metric].iloc[0], hits[metric].iloc[0])
                        if result:
                            ts, value, score = result
                            rows.append({
                                "timestamp": ts,
                                "service": service,
                                "metric": metric,
                                "detector": detector,
                                "value": round(float(value), 3),
                                "score": round(float(score), 3),
                            })

            detector_signals = pd.DataFrame(rows).sort_values("timestamp")
            detector_signals
            """
        ),
        cell_markdown(
            """
            Với detector registry, các mốc đáng chú ý vẫn xuất hiện mà không cần dùng fixed threshold làm detector chính: product latency/5xx bất thường sớm, cart latency drift từ khoảng `15:19Z`, memory drift từ khoảng `16:39Z`, GC drift từ khoảng `18:48Z`, và restart delta lúc `20:00Z`.
            """
        ),
        cell_markdown("## 2.3 Rolling Z-score để so sánh"),
        cell_code(
            """
            def rolling_z(series, window=120, min_periods=60):
                baseline = series.shift(1).rolling(window=window, min_periods=min_periods)
                return (series - baseline.mean()) / baseline.std()

            z_rows = []
            for metric in ["memory_usage_bytes", "jvm_gc_pause_ms_avg", "http_p99_latency_ms"]:
                z = rolling_z(cart[metric].astype(float))
                hits = cart[z >= 3]
                if not hits.empty:
                    idx = hits.index[0]
                    z_rows.append({
                        "metric": metric,
                        "first_z_anomaly": cart.loc[idx, "timestamp"],
                        "z_score": z.loc[idx],
                        "value": cart.loc[idx, metric],
                    })
            pd.DataFrame(z_rows)
            """
        ),
        cell_markdown(
            """
            Raw Rolling Z-score có thể bắt outlier nhỏ từ sớm. Vì vậy, khi viết postmortem, chúng ta không chỉ dựa vào một điểm z-score, mà dùng thêm sustained threshold để xác nhận tín hiệu có ý nghĩa vận hành.
            """
        ),
        cell_code(
            """
            fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=True)
            for ax, metric in zip(axes, ["memory_pct", "jvm_gc_pause_ms_avg", "http_p99_latency_ms"]):
                z = rolling_z(cart[metric].astype(float))
                ax.plot(cart["timestamp"], z, linewidth=1)
                ax.axhline(3, color="#d62728", linestyle="--", linewidth=1)
                ax.set_ylabel(metric)
                ax.grid(True, alpha=0.25)
                format_time_axis(ax)
            fig.suptitle("Rolling Z-score trên cart-service")
            fig.tight_layout()
            fig.savefig(PLOTS / "02_metric_rolling_z_cart.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Rolling Z-score trên cart-service", "02_metric_rolling_z_cart.png"),
        cell_markdown("## 2.4 Sustained threshold chỉ dùng để xác nhận vận hành"),
        cell_code(
            """
            def first_sustained(df, series, threshold, points=5):
                mask = series >= threshold
                sustained = mask.rolling(points).sum() >= points
                if not sustained.any():
                    return None
                idx = np.where(sustained)[0][0] - points + 1
                return df.loc[idx, "timestamp"], series.iloc[idx]

            checks = [
                ("cart-service", "jvm_gc_pause_ms_avg", cart["jvm_gc_pause_ms_avg"], 100),
                ("cart-service", "memory_pct", cart["memory_pct"], 70),
                ("cart-service", "http_5xx_rate", cart["http_5xx_rate"], 5),
            ]
            rows = []
            for service, metric, series, threshold in checks:
                result = first_sustained(cart, series, threshold)
                if result:
                    ts, value = result
                    rows.append({"service": service, "metric": metric, "first_sustained": ts, "threshold": threshold, "value": value})
            pd.DataFrame(rows)
            """
        ),
        cell_markdown("## 2.5 Isolation Forest trên cart-service"),
        cell_code(
            """
            feature_cols = ["memory_pct", "jvm_gc_pause_ms_avg", "http_p99_latency_ms", "http_5xx_rate", "restart_delta"]
            features = cart[feature_cols].astype(float).ffill().bfill()
            scaled = StandardScaler().fit_transform(features)

            model = IsolationForest(n_estimators=300, contamination=0.04, random_state=42)
            pred = model.fit_predict(scaled)
            score = -model.decision_function(scaled)
            cart["if_anomaly"] = pred == -1
            cart["if_score"] = score

            first_idx = cart.index[cart["if_anomaly"]][0]
            cart.loc[first_idx, ["timestamp"] + feature_cols + ["if_score"]]
            """
        ),
        cell_code(
            """
            fig, ax = plt.subplots(figsize=(13, 5))
            ax.plot(cart["timestamp"], cart["memory_pct"], label="memory %", color="#1f77b4")
            ax2 = ax.twinx()
            ax2.plot(cart["timestamp"], cart["jvm_gc_pause_ms_avg"], label="GC pause", color="#9467bd", alpha=0.75)
            ax.axvline(cart.loc[first_idx, "timestamp"], color="#111111", linestyle="--", label="Isolation Forest first anomaly")
            ax.axhline(70, color="#d62728", linestyle=":", linewidth=1)
            ax.set_title("Isolation Forest anomaly đặt trên memory và GC")
            ax.set_ylabel("memory %")
            ax2.set_ylabel("GC pause ms")
            ax.grid(True, alpha=0.25)
            format_time_axis(ax)
            lines, labels = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines + lines2, labels + labels2, fontsize=8, loc="upper left")
            fig.tight_layout()
            fig.savefig(PLOTS / "02_metric_isolation_forest_cart.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Isolation Forest trên cart-service", "02_metric_isolation_forest_cart.png"),
        cell_markdown(
            """
            Isolation Forest bắt anomaly đầu tiên ở khoảng `18:04:30Z`, rất gần với mốc GC sustained anomaly `18:06Z`. Đây là evidence mạnh rằng `cart-service` đã bước vào trạng thái bất thường trước khi OOM và restart xảy ra.
            """
        ),
    ]


def notebook_03() -> list[dict]:
    return [
        cell_markdown(
            """
            # 03 - Log Analysis với Drain3

            Sau khi metrics chỉ ra `cart-service` là service chính cần điều tra, notebook này phân tích logs để giải thích cơ chế lỗi.

            Ý tưởng: raw logs rất nhiều dòng, nên ta dùng Drain3 để gom message thành template. Sau đó đếm template theo thời gian để tìm pattern spike.
            """
        ),
        cell_code(
            """
            from pathlib import Path
            import json
            import re
            from collections import Counter

            import pandas as pd
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            from drain3 import TemplateMiner
            from drain3.template_miner_config import TemplateMinerConfig

            def find_project_root():
                cwd = Path.cwd().resolve()
                for candidate in [cwd, *cwd.parents]:
                    if (candidate / "g2-data" / "g2").exists():
                        return candidate
                raise FileNotFoundError("Cannot find project root containing g2-data/g2")

            ROOT = find_project_root()
            DATA = ROOT / "g2-data" / "g2"
            LOGS = DATA / "logs"
            PLOTS = ROOT / "lab" / "plots"
            RESULTS = ROOT / "lab" / "results"
            PLOTS.mkdir(parents=True, exist_ok=True)
            RESULTS.mkdir(parents=True, exist_ok=True)

            def format_time_axis(ax, interval=3):
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=interval))
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
                ax.tick_params(axis="x", labelrotation=0, labelsize=8, labelbottom=True)
            """
        ),
        cell_markdown("## 3.1 Đọc log JSONL"),
        cell_code(
            """
            def read_jsonl(path):
                rows = []
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        rows.append(json.loads(line))
                df = pd.DataFrame(rows)
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                return df

            cart_logs = read_jsonl(LOGS / "cart-service.log.jsonl")
            order_logs = read_jsonl(LOGS / "order-service.log.jsonl")

            pd.DataFrame([
                {"service": "cart-service", "rows": len(cart_logs), "start": cart_logs["timestamp"].min(), "end": cart_logs["timestamp"].max()},
                {"service": "order-service", "rows": len(order_logs), "start": order_logs["timestamp"].min(), "end": order_logs["timestamp"].max()},
            ])
            """
        ),
        cell_markdown("## 3.2 Phân bố log level theo thời gian"),
        cell_code(
            """
            cart_logs["hour"] = cart_logs["timestamp"].dt.floor("h")
            level_hour = cart_logs.groupby(["hour", "level"]).size().unstack(fill_value=0)
            level_hour.tail(8)
            """
        ),
        cell_code(
            """
            fig, ax = plt.subplots(figsize=(13, 5))
            level_hour.plot(kind="area", stacked=True, ax=ax, linewidth=0)
            ax.set_title("Cart-service log volume theo level")
            ax.set_ylabel("log count/hour")
            ax.grid(True, alpha=0.25)
            format_time_axis(ax)
            fig.tight_layout()
            fig.savefig(PLOTS / "03_log_cart_levels_by_hour.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Cart-service log volume theo level", "03_log_cart_levels_by_hour.png"),
        cell_markdown("## 3.3 Drain3 template mining"),
        cell_code(
            """
            def parse_with_drain(df):
                config = TemplateMinerConfig()
                config.profiling_enabled = False
                miner = TemplateMiner(config=config)
                rows = []
                for _, event in df.iterrows():
                    result = miner.add_log_message(event["message"])
                    rows.append({
                        "timestamp": event["timestamp"],
                        "level": event["level"],
                        "service": event["service"],
                        "message": event["message"],
                        "template": result["template_mined"],
                        "cluster_id": result["cluster_id"],
                    })
                return pd.DataFrame(rows)

            cart_templates = parse_with_drain(cart_logs)
            cart_templates["template"].value_counts().head(15)
            """
        ),
        cell_markdown("## 3.4 Template spike quan trọng"),
        cell_code(
            """
            patterns = {
                "cache eviction": "ProductCatalogCache eviction failed",
                "GC warning": "GC overhead limit warning",
                "slow response": "Slow response detected",
                "OOM imminent": "OutOfMemoryError imminent",
                "OOMKilled": "Container OOMKilled",
            }

            rows = []
            for label, needle in patterns.items():
                matched = cart_logs[cart_logs["message"].str.contains(re.escape(needle), regex=True)]
                counts = matched.set_index("timestamp").resample("30min").size()
                rows.append({
                    "pattern": label,
                    "first_seen": matched["timestamp"].min(),
                    "peak_bucket": counts.idxmax(),
                    "peak_count_30m": counts.max(),
                    "total_count": len(matched),
                })
            pd.DataFrame(rows)
            """
        ),
        cell_code(
            """
            fig, ax = plt.subplots(figsize=(13, 6))
            for label, needle in patterns.items():
                matched = cart_logs[cart_logs["message"].str.contains(re.escape(needle), regex=True)]
                counts = matched.set_index("timestamp").resample("30min").size()
                ax.plot(counts.index, counts.values, label=label, linewidth=1.4)
            ax.set_title("Cart-service log template counts theo bucket 30 phút")
            ax.set_ylabel("count/30min")
            ax.grid(True, alpha=0.25)
            ax.legend(fontsize=8)
            format_time_axis(ax)
            fig.tight_layout()
            fig.savefig(PLOTS / "03_log_cart_template_spikes.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Cart-service log template spikes", "03_log_cart_template_spikes.png"),
        cell_markdown("## 3.5 Khai thác field phụ: cache_size_mb và heap_used_mb"),
        cell_markdown(
            """
            Ngoài message text, `cart-service.log.jsonl` còn có một số field số rất quan trọng:

            - `cache_size_mb`: kích thước cache `ProductCatalogCache`.
            - `heap_used_mb`: heap đã dùng khi JVM báo sắp hết bộ nhớ.
            - `memory_limit_bytes`: giới hạn memory của container.

            Các field này giúp root cause mạnh hơn, vì không chỉ thấy log nói "cache eviction failed", mà còn thấy cache/heap đã lớn tới mức nào.
            """
        ),
        cell_code(
            """
            numeric_cols = ["timestamp", "level", "message", "cache_size_mb", "heap_used_mb", "memory_limit_bytes"]
            numeric = cart_logs[
                cart_logs[["cache_size_mb", "heap_used_mb", "memory_limit_bytes"]].notna().any(axis=1)
            ][numeric_cols].copy()

            summary_rows = []
            for field in ["cache_size_mb", "heap_used_mb"]:
                values = numeric.dropna(subset=[field]) if field in numeric else pd.DataFrame()
                if not values.empty:
                    summary_rows.append({
                        "field": field,
                        "first_seen": values["timestamp"].min(),
                        "count": len(values),
                        "median": values[field].median(),
                        "max": values[field].max(),
                        "max_at": values.loc[values[field].idxmax(), "timestamp"],
                        "example_message": values.loc[values[field].idxmax(), "message"],
                    })
            pd.DataFrame(summary_rows)
            """
        ),
        cell_code(
            """
            fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)

            cache = numeric.dropna(subset=["cache_size_mb"]).set_index("timestamp")["cache_size_mb"]
            cache_30m = cache.resample("30min").agg(["median", "max"])
            axes[0].plot(cache_30m.index, cache_30m["median"], label="median cache_size_mb", color="#1f77b4")
            axes[0].plot(cache_30m.index, cache_30m["max"], label="max cache_size_mb", color="#ff7f0e")
            axes[0].axhline(1800, color="#d62728", linestyle="--", linewidth=1, label="~1.8 GB")
            axes[0].set_ylabel("cache MB")
            axes[0].legend(fontsize=8)

            heap = numeric.dropna(subset=["heap_used_mb"]).set_index("timestamp")["heap_used_mb"]
            heap_30m = heap.resample("30min").agg(["median", "max"])
            axes[1].plot(heap_30m.index, heap_30m["median"], label="median heap_used_mb", color="#9467bd")
            axes[1].plot(heap_30m.index, heap_30m["max"], label="max heap_used_mb", color="#d62728")
            axes[1].axhline(2048, color="#111111", linestyle="--", linewidth=1, label="2 GB limit")
            axes[1].set_ylabel("heap MB")
            axes[1].legend(fontsize=8)

            for ax in axes:
                ax.grid(True, alpha=0.25)
                format_time_axis(ax)
            fig.suptitle("Cart-service cache_size_mb và heap_used_mb từ log")
            fig.tight_layout()
            fig.savefig(PLOTS / "03_log_cart_cache_heap_fields.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Cart-service cache và heap fields", "03_log_cart_cache_heap_fields.png"),
        cell_markdown(
            """
            Kết quả quan trọng: `cache_size_mb` có lúc lên gần `1.8 GB`, trong khi memory limit của container là khoảng `2 GB`. Khi OOM bắt đầu xuất hiện, `heap_used_mb` nằm khoảng `1.9-1.98 GB`. Đây là bằng chứng rất mạnh cho giả thuyết `ProductCatalogCache` phình lớn, eviction thất bại, rồi dẫn tới memory pressure/OOM.
            """
        ),
        cell_markdown("## 3.6 Order-service log patterns liên quan tới cart"),
        cell_code(
            """
            order_patterns = {
                "cart timeout": "Cart service timeout",
                "cart returned 5xx": "Cart service returned 5xx",
            }
            rows = []
            for label, needle in order_patterns.items():
                matched = order_logs[order_logs["message"].str.contains(re.escape(needle), regex=True)]
                counts = matched.set_index("timestamp").resample("30min").size()
                rows.append({
                    "pattern": label,
                    "first_seen": matched["timestamp"].min(),
                    "first_high_bucket": counts[counts >= 20].index.min(),
                    "total_count": len(matched),
                })
            pd.DataFrame(rows)
            """
        ),
        cell_code(
            """
            fig, ax = plt.subplots(figsize=(13, 5))
            for label, needle in order_patterns.items():
                matched = order_logs[order_logs["message"].str.contains(re.escape(needle), regex=True)]
                counts = matched.set_index("timestamp").resample("30min").size()
                ax.plot(counts.index, counts.values, label=label, linewidth=1.4)
            ax.set_title("Order-service log patterns liên quan tới cart-service")
            ax.set_ylabel("count/30min")
            ax.grid(True, alpha=0.25)
            ax.legend(fontsize=8)
            format_time_axis(ax)
            fig.tight_layout()
            fig.savefig(PLOTS / "03_log_order_cart_failures.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Order-service patterns liên quan tới cart", "03_log_order_cart_failures.png"),
        cell_markdown(
            """
            Log analysis giải thích cơ chế lỗi: cache eviction failure và GC warning spike từ `14:00Z`, sau đó `OutOfMemoryError imminent` và `OOMKilled` xuất hiện lúc `19:59Z`. Đây là evidence trực tiếp cho giả thuyết memory pressure/restart loop.
            """
        ),
    ]


def notebook_04() -> list[dict]:
    return [
        cell_markdown(
            """
            # 04 - Incident Timeline và Root Cause

            Notebook cuối kết hợp evidence từ metrics và logs để trả lời đầy đủ:

            - **WHEN**: anomaly bắt đầu từ lúc nào?
            - **WHERE**: service nào là nơi lỗi chính?
            - **WHAT**: cơ chế/root cause hypothesis là gì?

            Notebook này tự đọc raw data từ `g2-data/g2`, tự tính lại timeline, không phụ thuộc vào file CSV trong `lab/results`.
            """
        ),
        cell_code(
            """
            from pathlib import Path
            import json
            import re

            import numpy as np
            import pandas as pd
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler

            def find_project_root():
                cwd = Path.cwd().resolve()
                for candidate in [cwd, *cwd.parents]:
                    if (candidate / "g2-data" / "g2").exists():
                        return candidate
                raise FileNotFoundError("Cannot find project root containing g2-data/g2")

            ROOT = find_project_root()
            DATA = ROOT / "g2-data" / "g2"
            METRICS = DATA / "metrics"
            LOGS = DATA / "logs"
            PLOTS = ROOT / "lab" / "plots"
            PLOTS.mkdir(parents=True, exist_ok=True)

            def format_time_axis(ax, interval=3):
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=interval))
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
                ax.tick_params(axis="x", labelrotation=0, labelsize=8, labelbottom=True)

            def load_metric(name):
                df = pd.read_csv(METRICS / f"{name}.csv")
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                return df

            def first_sustained(df, series, threshold, points=5):
                mask = series >= threshold
                sustained = mask.rolling(points).sum() >= points
                if not sustained.any():
                    return None
                idx = np.where(sustained)[0][0] - points + 1
                return df.loc[idx, "timestamp"], float(series.iloc[idx])

            def first_log_timestamp(path, needle):
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        event = json.loads(line)
                        if needle in event["message"]:
                            return pd.to_datetime(event["timestamp"], utc=True)
                return None

            def first_30m_spike(path, needle, min_count=100):
                timestamps = []
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        event = json.loads(line)
                        if needle in event["message"]:
                            timestamps.append(pd.to_datetime(event["timestamp"], utc=True))
                counts = pd.Series(1, index=pd.DatetimeIndex(timestamps)).resample("30min").size()
                high = counts[counts >= min_count]
                return high.index.min() if not high.empty else None

            cart = load_metric("cart-service")
            product = load_metric("product-service")
            gateway = load_metric("api-gateway")
            order = load_metric("order-service")
            payment = load_metric("payment-service")

            cart["memory_pct"] = 100 * cart["memory_usage_bytes"] / cart["memory_limit_bytes"]
            cart["restart_delta"] = cart["container_restart_count"].diff().fillna(0)
            """
        ),
        cell_markdown("## 4.1 Tự dựng lại các mốc từ raw metrics/logs"),
        cell_code(
            """
            # Product early suspicious signal
            product_p99_ts, _ = first_sustained(product, product["http_p99_latency_ms"], 100)
            product_5xx_ts, _ = first_sustained(product, product["http_5xx_rate"], 5)

            # Cart metrics
            cart_gc_ts, _ = first_sustained(cart, cart["jvm_gc_pause_ms_avg"], 100)
            cart_mem_ts, _ = first_sustained(cart, cart["memory_pct"], 70)

            # Cart multivariate anomaly via Isolation Forest
            feature_cols = ["memory_pct", "jvm_gc_pause_ms_avg", "http_p99_latency_ms", "http_5xx_rate", "restart_delta"]
            features = cart[feature_cols].astype(float).ffill().bfill()
            scaled = StandardScaler().fit_transform(features)
            model = IsolationForest(n_estimators=300, contamination=0.04, random_state=42)
            pred = model.fit_predict(scaled)
            first_if_idx = np.where(pred == -1)[0][0]
            cart_if_ts = cart.loc[first_if_idx, "timestamp"]

            # Logs
            cart_log = LOGS / "cart-service.log.jsonl"
            cache_first_ts = first_log_timestamp(cart_log, "ProductCatalogCache eviction failed")
            cache_spike_ts = first_30m_spike(cart_log, "ProductCatalogCache eviction failed", min_count=100)
            oom_imminent_ts = first_log_timestamp(cart_log, "OutOfMemoryError imminent")
            oomkilled_ts = first_log_timestamp(cart_log, "Container OOMKilled")

            # Restart
            restart_rows = cart[cart["restart_delta"] > 0]
            restart_ts = restart_rows["timestamp"].iloc[0]

            # Downstream metrics
            gateway_ts, _ = first_sustained(gateway, gateway["cart_upstream_error_rate"], 5)
            order_ts, _ = first_sustained(order, order["upstream_timeout_rate"], 10)
            payment_ts, _ = first_sustained(payment, payment["upstream_timeout_rate"], 10)

            timeline = pd.DataFrame(
                [
                    (product_p99_ts, "product-service", "Product p99 latency sustained >100 ms"),
                    (product_5xx_ts, "product-service", "Product 5xx sustained >5%"),
                    (cache_first_ts, "cart-service", "ProductCatalogCache eviction failures first appear"),
                    (cache_spike_ts, "cart-service", "Cache eviction failures become high-volume"),
                    (cart_if_ts, "cart-service", "Isolation Forest first multivariate anomaly"),
                    (cart_gc_ts, "cart-service", "GC pause sustained >100 ms"),
                    (cart_mem_ts, "cart-service", "Memory sustained >70% of limit"),
                    (oom_imminent_ts, "cart-service", "OutOfMemoryError imminent"),
                    (oomkilled_ts, "cart-service", "Container OOMKilled"),
                    (restart_ts, "cart-service", "First container restart recorded"),
                    (gateway_ts, "api-gateway", "Cart upstream error rate sustained >5%"),
                    (order_ts, "order-service", "Order upstream timeout rate sustained >10%"),
                    (payment_ts, "payment-service", "Payment upstream timeout rate sustained >10%"),
                ],
                columns=["timestamp_dt", "service", "evidence"],
            ).sort_values("timestamp_dt")

            timeline["timestamp"] = timeline["timestamp_dt"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            timeline[["timestamp", "service", "evidence"]]
            """
        ),
        cell_markdown("## 4.2 Cross-signal timeline"),
        cell_code(
            """
            service_y = {name: idx for idx, name in enumerate(timeline["service"].unique())}
            timeline["y"] = timeline["service"].map(service_y)

            fig, ax = plt.subplots(figsize=(13, 6))
            ax.scatter(timeline["timestamp_dt"], timeline["y"], s=80, color="#1f77b4")
            for _, row in timeline.iterrows():
                ax.text(row["timestamp_dt"], row["y"] + 0.08, row["evidence"], fontsize=7, rotation=25, ha="left")
            ax.set_yticks(list(service_y.values()), list(service_y.keys()))
            ax.set_title("Cross-signal incident timeline")
            ax.grid(True, axis="x", alpha=0.25)
            format_time_axis(ax)
            fig.tight_layout()
            fig.savefig(PLOTS / "04_incident_cross_signal_timeline.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Cross-signal incident timeline", "04_incident_cross_signal_timeline.png"),
        cell_markdown("## 4.3 Xếp hạng service theo first anomaly"),
        cell_code(
            """
            first_anomaly = pd.DataFrame(
                [
                    ("product-service", product_p99_ts, "early suspicious signal"),
                    ("cart-service", cache_first_ts, "first proven cart signal"),
                    ("api-gateway", gateway_ts, "cart upstream errors"),
                    ("order-service", order_ts, "upstream timeouts"),
                    ("payment-service", payment_ts, "upstream timeouts"),
                ],
                columns=["service", "timestamp", "meaning"],
            )
            first_anomaly["timestamp_dt"] = pd.to_datetime(first_anomaly["timestamp"], utc=True)
            first_anomaly["timestamp"] = first_anomaly["timestamp_dt"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            first_anomaly
            """
        ),
        cell_code(
            """
            start = first_anomaly["timestamp_dt"].min()
            first_anomaly["hours_since_first"] = (first_anomaly["timestamp_dt"] - start).dt.total_seconds() / 3600

            fig, ax = plt.subplots(figsize=(9, 5))
            ax.barh(first_anomaly["service"], first_anomaly["hours_since_first"], color="#4c78a8")
            ax.set_xlabel("giờ sau signal đầu tiên")
            ax.set_title("Xếp hạng first anomaly theo service")
            ax.grid(True, axis="x", alpha=0.25)
            fig.tight_layout()
            fig.savefig(PLOTS / "04_service_first_anomaly_ranking.png", dpi=160)
            plt.show()
            """
        ),
        cell_image("Xếp hạng first anomaly theo service", "04_service_first_anomaly_ranking.png"),
        cell_markdown(
            """
            ## 4.4 Kết luận WHEN / WHERE / WHAT

            **WHEN**

            - Earliest suspicious signal: `product-service` lúc `03:03Z`.
            - Earliest proven cart signal: `ProductCatalogCache eviction failed` lúc `06:32:33Z`.
            - First high-volume cart signal: template spike lúc `14:00Z`.
            - First strong metric anomaly trên cart: Isolation Forest lúc `18:04:30Z`, GC sustained lúc `18:06Z`.
            - Failure thật sự: OOM/OOMKilled lúc `19:59Z`, restart đầu tiên lúc `20:00Z`.

            **WHERE**

            - Root failure nằm ở `cart-service`.
            - `api-gateway`, `order-service`, và `payment-service` là downstream symptoms vì chúng bất thường sau cart.

            **WHAT**

            - Giả thuyết root cause: `cart-service` bị memory pressure liên quan tới `ProductCatalogCache`.
            - Cache eviction failures xuất hiện sớm và spike từ `14:00Z`.
            - Heap pressure làm GC pause tăng, memory tăng, cuối cùng OOMKilled và restart loop.
            - Product-service có anomaly rất sớm, có thể là possible trigger, nhưng chưa đủ evidence để gọi là root cause.
            """
        ),
        cell_markdown(
            """
            ## 4.5 Limitations

            - Không có product-service logs, nên chưa chứng minh trực tiếp product anomaly gây ra cart cache issue.
            - Không có distributed traces để nối quan hệ request/cache refresh giữa product và cart.
            - Metrics thiếu 30 phút từ `11:30Z` đến `11:59:30Z`.
            - Rolling Z-score có thể bắt outlier sớm, nên phải kết hợp sustained threshold và Isolation Forest.
            """
        ),
    ]


def main() -> None:
    NOTEBOOKS.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)

    save_eda_plots()
    save_anomaly_plots()
    save_log_plots()
    save_timeline_plots()

    notebooks = {
        "01_eda_metrics.ipynb": notebook_01(),
        "02_metric_anomaly.ipynb": notebook_02(),
        "03_log_analysis.ipynb": notebook_03(),
        "04_incident_timeline.ipynb": notebook_04(),
    }
    for name, cells in notebooks.items():
        write_notebook(NOTEBOOKS / name, cells)
        print("wrote", NOTEBOOKS / name)

    print("plots written to", PLOTS)


if __name__ == "__main__":
    main()
