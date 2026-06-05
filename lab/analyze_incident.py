from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "g2-data" / "g2"
METRICS = DATA / "metrics"
LOGS = DATA / "logs"
OUT = ROOT / "lab" / "results"
PLOTS = ROOT / "lab" / "plots"


def ensure_dirs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)


def load_metric(name: str) -> pd.DataFrame:
    df = pd.read_csv(METRICS / f"{name}.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def timestamp_z(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def timestamp_ms_z(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def format_time_axis(ax, interval: int = 3) -> None:
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.tick_params(axis="x", labelrotation=0, labelsize=8, labelbottom=True)


def rolling_z_anomalies(
    df: pd.DataFrame,
    service: str,
    metrics: list[str],
    window: int = 120,
    min_periods: int = 60,
    z_threshold: float = 3.0,
) -> pd.DataFrame:
    rows = []
    for metric in metrics:
        s = df[metric].astype(float)
        baseline = s.shift(1).rolling(window=window, min_periods=min_periods)
        mu = baseline.mean()
        sigma = baseline.std().replace(0, np.nan)
        z = (s - mu) / sigma
        candidates = df[(z >= z_threshold) & s.notna()]
        if candidates.empty:
            continue
        idx = candidates.index[0]
        rows.append(
            {
                "service": service,
                "metric": metric,
                "first_anomaly_timestamp": timestamp_z(df.loc[idx, "timestamp"]),
                "score": round(float(z.loc[idx]), 3),
                "value": round(float(s.loc[idx]), 3),
                "detector": "rolling_z_score",
            }
        )
    return pd.DataFrame(rows)


def isolation_forest_anomalies(
    df: pd.DataFrame,
    service: str,
    feature_cols: list[str],
    contamination: float = 0.035,
) -> pd.DataFrame:
    features = df[feature_cols].astype(float).copy()
    features = features.ffill().bfill()
    scaled = StandardScaler().fit_transform(features)
    model = IsolationForest(n_estimators=300, contamination=contamination, random_state=42)
    pred = model.fit_predict(scaled)
    score = -model.decision_function(scaled)
    rows = []
    for col in feature_cols:
        anomaly_idx = np.where(pred == -1)[0]
        if len(anomaly_idx) == 0:
            continue
        idx = int(anomaly_idx[0])
        rows.append(
            {
                "service": service,
                "metric": col,
                "first_anomaly_timestamp": timestamp_z(df.loc[idx, "timestamp"]),
                "score": round(float(score[idx]), 4),
                "value": round(float(features.iloc[idx][col]), 3),
                "detector": "isolation_forest",
            }
        )
    return pd.DataFrame(rows)


def sustained_threshold(
    df: pd.DataFrame,
    service: str,
    metric: str,
    series: pd.Series,
    threshold: float,
    points: int = 5,
) -> dict | None:
    mask = series >= threshold
    sustained = mask.rolling(points).sum() >= points
    if not sustained.any():
        return None
    idx = int(np.where(sustained)[0][0] - points + 1)
    return {
        "service": service,
        "metric": metric,
        "threshold": threshold,
        "first_sustained_timestamp": timestamp_z(df.loc[idx, "timestamp"]),
        "value": round(float(series.iloc[idx]), 3),
    }


METRIC_DETECTOR_MAP = {
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


def metric_family(metric: str) -> str:
    if metric in {"memory_pct", "jvm_gc_pause_ms_avg", "cpu_usage_percent", "restart_delta"}:
        return "resource"
    if "5xx" in metric or "timeout" in metric or "error_rate" in metric:
        return "availability"
    if "latency" in metric:
        return "latency"
    if "requests_per_sec" in metric or "connections" in metric:
        return "traffic"
    return "other"


def first_sustained_mask(mask: pd.Series, points: int = 3) -> int | None:
    sustained = mask.rolling(points).sum() >= points
    if not sustained.any():
        return None
    return int(np.where(sustained)[0][0] - points + 1)


def ewma_detector(
    df: pd.DataFrame,
    service: str,
    metric: str,
    series: pd.Series,
    span: int = 120,
    min_periods: int = 60,
    z_threshold: float = 4.0,
    points: int = 3,
) -> dict | None:
    s = series.astype(float)
    baseline = s.shift(1).ewm(span=span, min_periods=min_periods, adjust=False).mean()
    sigma = s.shift(1).ewm(span=span, min_periods=min_periods, adjust=False).std().replace(0, np.nan)
    score = (s - baseline) / sigma
    idx = first_sustained_mask((score >= z_threshold) & s.notna(), points=points)
    if idx is None:
        return None
    return {
        "timestamp": timestamp_z(df.loc[idx, "timestamp"]),
        "service": service,
        "source": "metric",
        "metric": metric,
        "metric_family": metric_family(metric),
        "detector": "ewma_residual",
        "score": round(float(score.iloc[idx]), 3),
        "value": round(float(s.iloc[idx]), 3),
        "severity": "warning",
        "evidence": f"{metric} is above EWMA baseline for {points} consecutive points",
    }


def rolling_iqr_detector(
    df: pd.DataFrame,
    service: str,
    metric: str,
    series: pd.Series,
    window: int = 120,
    min_periods: int = 60,
    multiplier: float = 3.0,
    points: int = 3,
) -> dict | None:
    s = series.astype(float)
    baseline = s.shift(1).rolling(window=window, min_periods=min_periods)
    q1 = baseline.quantile(0.25)
    q3 = baseline.quantile(0.75)
    iqr = q3 - q1
    upper = q3 + multiplier * iqr
    score = (s - q3) / iqr.replace(0, np.nan)
    idx = first_sustained_mask((s > upper) & s.notna(), points=points)
    if idx is None:
        return None
    return {
        "timestamp": timestamp_z(df.loc[idx, "timestamp"]),
        "service": service,
        "source": "metric",
        "metric": metric,
        "metric_family": metric_family(metric),
        "detector": "rolling_iqr",
        "score": round(float(score.iloc[idx]), 3),
        "value": round(float(s.iloc[idx]), 3),
        "severity": "warning",
        "evidence": f"{metric} is above rolling IQR upper band for {points} consecutive points",
    }


def baseline_iqr_detector(
    df: pd.DataFrame,
    service: str,
    metric: str,
    series: pd.Series,
    baseline_hours: int = 6,
    multiplier: float = 3.0,
    points: int = 3,
) -> dict | None:
    s = series.astype(float)
    start = df["timestamp"].min()
    baseline_mask = df["timestamp"] < start + pd.Timedelta(hours=baseline_hours)
    baseline = s[baseline_mask].dropna()
    if len(baseline) < 60:
        return None
    q1 = baseline.quantile(0.25)
    q3 = baseline.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0 or pd.isna(iqr):
        return None
    upper = q3 + multiplier * iqr
    score = (s - q3) / iqr
    idx = first_sustained_mask((s > upper) & (~baseline_mask) & s.notna(), points=points)
    if idx is None:
        return None
    return {
        "timestamp": timestamp_z(df.loc[idx, "timestamp"]),
        "service": service,
        "source": "metric",
        "metric": metric,
        "metric_family": metric_family(metric),
        "detector": "baseline_iqr",
        "score": round(float(score.iloc[idx]), 3),
        "value": round(float(s.iloc[idx]), 3),
        "severity": "warning",
        "evidence": f"{metric} is above {baseline_hours}h baseline IQR upper band for {points} consecutive points",
    }


def counter_delta_detector(
    df: pd.DataFrame,
    service: str,
    metric: str,
    series: pd.Series,
) -> dict | None:
    s = series.astype(float)
    hits = df[s > 0]
    if hits.empty:
        return None
    idx = hits.index[0]
    return {
        "timestamp": timestamp_z(df.loc[idx, "timestamp"]),
        "service": service,
        "source": "metric",
        "metric": metric,
        "metric_family": metric_family(metric),
        "detector": "counter_delta",
        "score": round(float(s.iloc[idx]), 3),
        "value": round(float(s.iloc[idx]), 3),
        "severity": "critical",
        "evidence": f"{metric} increased",
    }


def run_metric_detector_map(service_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for service, raw_df in service_frames.items():
        df = raw_df.copy()
        if "memory_usage_bytes" in df and "memory_limit_bytes" in df:
            df["memory_pct"] = 100 * df["memory_usage_bytes"] / df["memory_limit_bytes"]
        if "container_restart_count" in df:
            df["restart_delta"] = df["container_restart_count"].diff().fillna(0)

        for metric, detectors in METRIC_DETECTOR_MAP.items():
            if metric not in df:
                continue
            series = df[metric]
            for detector in detectors:
                row = None
                if detector == "baseline_iqr":
                    row = baseline_iqr_detector(df, service, metric, series)
                elif detector == "ewma":
                    row = ewma_detector(df, service, metric, series)
                elif detector == "rolling_iqr":
                    row = rolling_iqr_detector(df, service, metric, series)
                elif detector == "counter_delta":
                    row = counter_delta_detector(df, service, metric, series)
                if row:
                    rows.append(row)
    if not rows:
        return pd.DataFrame(
            columns=["timestamp", "service", "source", "metric", "metric_family", "detector", "score", "value", "severity", "evidence"]
        )
    result = pd.DataFrame(rows)
    result["_timestamp_dt"] = pd.to_datetime(result["timestamp"], utc=True)
    return result.sort_values(["_timestamp_dt", "service", "metric", "detector"]).drop(columns="_timestamp_dt")


def summarize_metrics() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    services = {
        "cart-service": load_metric("cart-service"),
        "order-service": load_metric("order-service"),
        "payment-service": load_metric("payment-service"),
        "api-gateway": load_metric("api-gateway"),
        "product-service": load_metric("product-service"),
    }

    summaries = []
    gaps = []
    z_rows = []
    if_rows = []
    threshold_rows = []

    for service, df in services.items():
        for col in df.columns:
            if col == "timestamp":
                continue
            summaries.append(
                {
                    "service": service,
                    "metric": col,
                    "min": float(df[col].min()),
                    "median": float(df[col].median()),
                    "mean": float(df[col].mean()),
                    "max": float(df[col].max()),
                    "max_at": timestamp_z(df.loc[df[col].idxmax(), "timestamp"]),
                }
            )

        diffs = df["timestamp"].diff()
        bad = df[diffs > pd.Timedelta(seconds=30)]
        for idx, row in bad.iterrows():
            prev = df.loc[idx - 1, "timestamp"]
            missing = int((row["timestamp"] - prev).total_seconds() / 30) - 1
            gaps.append(
                {
                    "service": service,
                    "gap_start_after": timestamp_z(prev),
                    "next_timestamp": timestamp_z(row["timestamp"]),
                    "missing_30s_points": missing,
                }
            )

    cart = services["cart-service"].copy()
    cart["memory_pct"] = 100 * cart["memory_usage_bytes"] / cart["memory_limit_bytes"]
    cart["restart_delta"] = cart["container_restart_count"].diff().fillna(0)

    z_specs = {
        "cart-service": ["memory_usage_bytes", "jvm_gc_pause_ms_avg", "http_p99_latency_ms"],
        "order-service": ["http_p99_latency_ms", "upstream_timeout_rate"],
        "payment-service": ["http_p99_latency_ms", "upstream_timeout_rate"],
        "api-gateway": ["cart_upstream_error_rate", "http_p99_latency_ms"],
        "product-service": ["http_p99_latency_ms", "http_5xx_rate", "cpu_usage_percent"],
    }
    for service, cols in z_specs.items():
        z_rows.append(rolling_z_anomalies(services[service], service, cols))

    if_rows.append(
        isolation_forest_anomalies(
            cart,
            "cart-service",
            ["memory_pct", "jvm_gc_pause_ms_avg", "http_p99_latency_ms", "http_5xx_rate", "restart_delta"],
            contamination=0.04,
        )
    )

    threshold_specs = [
        ("cart-service", "jvm_gc_pause_ms_avg", services["cart-service"]["jvm_gc_pause_ms_avg"], 100),
        (
            "cart-service",
            "memory_pct",
            100 * services["cart-service"]["memory_usage_bytes"] / services["cart-service"]["memory_limit_bytes"],
            70,
        ),
        ("cart-service", "http_5xx_rate", services["cart-service"]["http_5xx_rate"], 5),
        ("api-gateway", "cart_upstream_error_rate", services["api-gateway"]["cart_upstream_error_rate"], 5),
        ("order-service", "upstream_timeout_rate", services["order-service"]["upstream_timeout_rate"], 10),
        ("payment-service", "upstream_timeout_rate", services["payment-service"]["upstream_timeout_rate"], 10),
        ("product-service", "http_p99_latency_ms", services["product-service"]["http_p99_latency_ms"], 100),
        ("product-service", "http_5xx_rate", services["product-service"]["http_5xx_rate"], 5),
        ("product-service", "cpu_usage_percent", services["product-service"]["cpu_usage_percent"], 60),
    ]
    for service, metric, series, threshold in threshold_specs:
        row = sustained_threshold(services[service], service, metric, series, threshold)
        if row:
            threshold_rows.append(row)

    summary_df = pd.DataFrame(summaries)
    gap_df = pd.DataFrame(gaps)
    z_df = pd.concat(z_rows, ignore_index=True)
    if_df = pd.concat(if_rows, ignore_index=True)
    threshold_df = pd.DataFrame(threshold_rows)
    metric_signal_df = run_metric_detector_map(services)
    return summary_df, gap_df, z_df, if_df, threshold_df, metric_signal_df


def normalize_template(template: str) -> str:
    template = re.sub(r"<:\w+:>", "<*>", template)
    template = re.sub(r"<\*>", "<*>", template)
    return template


def drain_templates(path: Path) -> pd.DataFrame:
    config = TemplateMinerConfig()
    config.profiling_enabled = False
    config.drain_depth = 4
    config.drain_sim_th = 0.45
    miner = TemplateMiner(config=config)

    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            result = miner.add_log_message(event["message"])
            rows.append(
                {
                    "timestamp": pd.to_datetime(event["timestamp"], utc=True),
                    "level": event["level"],
                    "service": event["service"],
                    "pod": event["pod"],
                    "message": event["message"],
                    "template": normalize_template(result["template_mined"]),
                    "cluster_id": result["cluster_id"],
                    "cache_size_mb": event.get("cache_size_mb"),
                    "heap_used_mb": event.get("heap_used_mb"),
                    "memory_limit_bytes": event.get("memory_limit_bytes"),
                    "duration_ms": event.get("duration_ms"),
                }
            )
    return pd.DataFrame(rows)


def first_spike_by_template(events: pd.DataFrame, bucket: str = "30min") -> pd.DataFrame:
    rows = []
    for template, group in events.groupby("template"):
        counts = group.set_index("timestamp").resample(bucket).size()
        counts = counts[counts > 0]
        if counts.empty:
            continue
        # A spike needs enough volume and must beat the previous median by a clear margin.
        spike_time = None
        spike_count = None
        spike_score = None
        for i, (ts, count) in enumerate(counts.items()):
            previous = counts.iloc[:i]
            if count < 8:
                continue
            if len(previous) < 4:
                continue
            med = previous.median()
            mad = (previous - med).abs().median()
            robust_sigma = 1.4826 * mad if mad > 0 else max(math.sqrt(max(med, 1)), 1.0)
            score = (count - med) / robust_sigma
            if count >= max(3 * med, med + 20) and score >= 3:
                spike_time = ts
                spike_count = int(count)
                spike_score = float(score)
                break
        first_seen = group["timestamp"].min()
        rows.append(
            {
                "template": template,
                "first_seen": timestamp_ms_z(first_seen),
                "first_spike": timestamp_z(spike_time) if spike_time is not None else "",
                "spike_count_30m": spike_count if spike_count is not None else "",
                "spike_score": round(spike_score, 3) if spike_score is not None else "",
                "total_count": int(len(group)),
                "levels": ",".join(f"{k}:{v}" for k, v in Counter(group["level"]).most_common()),
            }
        )
    return pd.DataFrame(rows).sort_values(["total_count", "first_seen"], ascending=[False, True])


def summarize_logs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    all_events = []
    template_tables = []
    for path in [LOGS / "cart-service.log.jsonl", LOGS / "order-service.log.jsonl"]:
        events = drain_templates(path)
        all_events.append(events)
        spikes = first_spike_by_template(events)
        spikes.insert(0, "service", events["service"].iloc[0])
        template_tables.append(spikes)

    events_df = pd.concat(all_events, ignore_index=True)
    templates_df = pd.concat(template_tables, ignore_index=True)

    pattern_map = {
        "cache_eviction": "ProductCatalogCache eviction failed",
        "oom_imminent": "OutOfMemoryError imminent",
        "oomkilled": "Container OOMKilled",
        "product_refused": "Upstream connection refused host=product-service",
        "db_pool_near_limit": "Connection pool nearing limit",
        "order_cart_5xx": "Cart service returned 5xx",
        "order_cart_timeout": "Cart service timeout",
    }
    rows = []
    for name, needle in pattern_map.items():
        matched = events_df[events_df["message"].str.contains(re.escape(needle), regex=True)]
        if matched.empty:
            continue
        by_hour = matched.set_index("timestamp").resample("1h").size()
        rows.append(
            {
                "pattern": name,
                "service": matched["service"].iloc[0],
                "first_seen": timestamp_ms_z(matched["timestamp"].min()),
                "total_count": int(len(matched)),
                "peak_hour": timestamp_z(by_hour.idxmax()),
                "peak_hour_count": int(by_hour.max()),
                "example_template": matched["template"].iloc[0],
            }
        )
    pattern_df = pd.DataFrame(rows)

    numeric_rows = []
    for _, event in events_df.iterrows():
        row = {
            "timestamp": event["timestamp"],
            "service": event["service"],
            "level": event["level"],
            "template": event["template"],
            "message": event["message"],
        }
        for field in ["cache_size_mb", "heap_used_mb", "memory_limit_bytes", "duration_ms"]:
            if field in event and pd.notna(event[field]):
                row[field] = event[field]
        if any(field in row for field in ["cache_size_mb", "heap_used_mb", "memory_limit_bytes"]):
            numeric_rows.append(row)
    numeric_df = pd.DataFrame(numeric_rows)
    return events_df, templates_df, pattern_df, numeric_df


def summarize_cart_numeric_fields(numeric_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if numeric_df.empty:
        return pd.DataFrame(rows)
    for field in ["cache_size_mb", "heap_used_mb"]:
        if field not in numeric_df:
            continue
        values = numeric_df.dropna(subset=[field])
        if values.empty:
            continue
        rows.append(
            {
                "field": field,
                "first_seen": timestamp_ms_z(values["timestamp"].min()),
                "count": int(len(values)),
                "min": round(float(values[field].min()), 3),
                "median": round(float(values[field].median()), 3),
                "max": round(float(values[field].max()), 3),
                "max_at": timestamp_ms_z(values.loc[values[field].idxmax(), "timestamp"]),
                "example_message": values.loc[values[field].idxmax(), "message"],
            }
        )
    if "memory_limit_bytes" in numeric_df:
        limits = numeric_df.dropna(subset=["memory_limit_bytes"])
        if not limits.empty:
            rows.append(
                {
                    "field": "memory_limit_mb",
                    "first_seen": timestamp_ms_z(limits["timestamp"].min()),
                    "count": int(len(limits)),
                    "min": round(float((limits["memory_limit_bytes"] / 1024 / 1024).min()), 3),
                    "median": round(float((limits["memory_limit_bytes"] / 1024 / 1024).median()), 3),
                    "max": round(float((limits["memory_limit_bytes"] / 1024 / 1024).max()), 3),
                    "max_at": timestamp_ms_z(limits.loc[limits["memory_limit_bytes"].idxmax(), "timestamp"]),
                    "example_message": limits.loc[limits["memory_limit_bytes"].idxmax(), "message"],
                }
            )
    return pd.DataFrame(rows)


def build_timeline(
    threshold_df: pd.DataFrame,
    pattern_df: pd.DataFrame,
    templates_df: pd.DataFrame,
) -> pd.DataFrame:
    def pattern_time(name: str) -> str:
        return pattern_df.loc[pattern_df["pattern"] == name, "first_seen"].iloc[0]

    def threshold_time(service: str, metric: str) -> str:
        return threshold_df.loc[
            (threshold_df["service"] == service) & (threshold_df["metric"] == metric),
            "first_sustained_timestamp",
        ].iloc[0]

    def template_spike_time(service: str, contains: str) -> str:
        hits = templates_df[
            (templates_df["service"] == service)
            & (templates_df["template"].str.contains(re.escape(contains), regex=True))
            & (templates_df["first_spike"].astype(str) != "")
        ]
        if hits.empty:
            raise ValueError(f"No spike found for {service} template containing {contains!r}")
        return hits.sort_values("first_spike").iloc[0]["first_spike"]

    cart = load_metric("cart-service")
    restart_delta = cart["container_restart_count"].diff().fillna(0)
    restart_hits = cart[restart_delta > 0]
    if restart_hits.empty:
        raise ValueError("No cart-service restart increment found")
    first_restart_time = timestamp_z(restart_hits["timestamp"].iloc[0])

    timeline = [
        (
            threshold_time("product-service", "http_p99_latency_ms"),
            "product-service",
            "Product p99 latency sustained >100ms",
        ),
        (
            threshold_time("product-service", "http_5xx_rate"),
            "product-service",
            "Product 5xx sustained >5%",
        ),
        (pattern_time("cache_eviction"), "cart-service", "ProductCatalogCache eviction failures first appear"),
        (
            template_spike_time("cart-service", "ProductCatalogCache eviction failed"),
            "cart-service",
            "Cache eviction failures become high-volume",
        ),
        (threshold_time("cart-service", "jvm_gc_pause_ms_avg"), "cart-service", "GC pause sustained >100ms"),
        (threshold_time("cart-service", "memory_pct"), "cart-service", "Memory sustained >70% of limit"),
        (pattern_time("oom_imminent"), "cart-service", "OutOfMemoryError imminent"),
        (pattern_time("oomkilled"), "cart-service", "Container OOMKilled"),
        (first_restart_time, "cart-service", "First container restart recorded"),
        (threshold_time("api-gateway", "cart_upstream_error_rate"), "api-gateway", "Cart upstream error rate sustained >5%"),
        (threshold_time("order-service", "upstream_timeout_rate"), "order-service", "Order upstream timeout rate sustained >10%"),
        (threshold_time("payment-service", "upstream_timeout_rate"), "payment-service", "Payment upstream timeout rate sustained >10%"),
    ]
    timeline_df = pd.DataFrame(timeline, columns=["timestamp", "service", "evidence"])
    timeline_df["_timestamp_dt"] = pd.to_datetime(timeline_df["timestamp"], utc=True, format="mixed")
    return timeline_df.sort_values("_timestamp_dt").drop(columns="_timestamp_dt")


def plot_cart_timeline() -> None:
    cart = load_metric("cart-service")
    cart["memory_pct"] = 100 * cart["memory_usage_bytes"] / cart["memory_limit_bytes"]
    cart["restart_delta"] = cart["container_restart_count"].diff().fillna(0)

    def first_sustained_time(series: pd.Series, threshold: float, points: int = 5) -> pd.Timestamp | None:
        mask = series >= threshold
        sustained = mask.rolling(points).sum() >= points
        if not sustained.any():
            return None
        idx = int(np.where(sustained)[0][0] - points + 1)
        return cart.loc[idx, "timestamp"]

    def first_log_time(needle: str) -> pd.Timestamp | None:
        with (LOGS / "cart-service.log.jsonl").open(encoding="utf-8") as f:
            for line in f:
                event = json.loads(line)
                if needle in event["message"]:
                    return pd.to_datetime(event["timestamp"], utc=True)
        return None

    def first_30m_spike_time(needle: str, min_count: int = 100) -> pd.Timestamp | None:
        timestamps = []
        with (LOGS / "cart-service.log.jsonl").open(encoding="utf-8") as f:
            for line in f:
                event = json.loads(line)
                if needle in event["message"]:
                    timestamps.append(pd.to_datetime(event["timestamp"], utc=True))
        if not timestamps:
            return None
        counts = pd.Series(1, index=pd.DatetimeIndex(timestamps)).resample("30min").size()
        high = counts[counts >= min_count]
        return high.index.min() if not high.empty else None

    event_times = [
        first_30m_spike_time("ProductCatalogCache eviction failed"),
        first_sustained_time(cart["jvm_gc_pause_ms_avg"], 100),
        first_sustained_time(cart["memory_pct"], 70),
        first_log_time("OutOfMemoryError imminent"),
        cart.loc[cart["restart_delta"] > 0, "timestamp"].iloc[0],
    ]

    fig, axes = plt.subplots(4, 1, figsize=(13, 10), sharex=True)
    axes[0].plot(cart["timestamp"], cart["memory_pct"], color="#1f77b4", linewidth=1.5)
    axes[0].axhline(70, color="#d62728", linestyle="--", linewidth=1)
    axes[0].set_ylabel("memory %")

    axes[1].plot(cart["timestamp"], cart["jvm_gc_pause_ms_avg"], color="#9467bd", linewidth=1.2)
    axes[1].axhline(100, color="#d62728", linestyle="--", linewidth=1)
    axes[1].set_ylabel("GC ms")

    axes[2].plot(cart["timestamp"], cart["http_p99_latency_ms"], color="#ff7f0e", linewidth=1)
    axes[2].set_ylabel("p99 ms")

    axes[3].plot(cart["timestamp"], cart["http_5xx_rate"], color="#d62728", linewidth=1)
    axes[3].bar(cart["timestamp"], cart["restart_delta"] * 5, width=0.015, color="#222222", alpha=0.5)
    axes[3].set_ylabel("5xx %, restart")

    for ax in axes:
        ax.grid(True, alpha=0.25)
        format_time_axis(ax)
        for ts in [ts for ts in event_times if ts is not None]:
            ax.axvline(ts, color="#555555", alpha=0.25, linewidth=1)
    fig.suptitle("cart-service incident timeline")
    fig.tight_layout()
    fig.savefig(PLOTS / "cart_timeline.png", dpi=160)
    plt.close(fig)


def plot_cart_log_numeric_fields(numeric_df: pd.DataFrame) -> None:
    if numeric_df.empty:
        return
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    if "cache_size_mb" in numeric_df:
        cache = numeric_df.dropna(subset=["cache_size_mb"]).set_index("timestamp")["cache_size_mb"]
        cache_30m = cache.resample("30min").agg(["median", "max"])
        axes[0].plot(cache_30m.index, cache_30m["median"], label="median cache_size_mb", color="#1f77b4")
        axes[0].plot(cache_30m.index, cache_30m["max"], label="max cache_size_mb", color="#ff7f0e", alpha=0.8)
        axes[0].axhline(1800, color="#d62728", linestyle="--", linewidth=1, label="~1.8 GB")
        axes[0].set_ylabel("cache MB")
        axes[0].legend(fontsize=8)
    if "heap_used_mb" in numeric_df:
        heap = numeric_df.dropna(subset=["heap_used_mb"]).set_index("timestamp")["heap_used_mb"]
        heap_30m = heap.resample("30min").agg(["median", "max"])
        axes[1].plot(heap_30m.index, heap_30m["median"], label="median heap_used_mb", color="#9467bd")
        axes[1].plot(heap_30m.index, heap_30m["max"], label="max heap_used_mb", color="#d62728", alpha=0.8)
        axes[1].axhline(2048, color="#111111", linestyle="--", linewidth=1, label="2 GB limit")
        axes[1].set_ylabel("heap MB")
        axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(True, alpha=0.25)
        format_time_axis(ax)
    fig.suptitle("Cart-service log numeric fields: cache size và heap used")
    fig.tight_layout()
    fig.savefig(PLOTS / "03_log_cart_cache_heap_fields.png", dpi=160)
    plt.close(fig)


def main() -> None:
    ensure_dirs()
    summary_df, gap_df, z_df, if_df, threshold_df, metric_signal_df = summarize_metrics()
    events_df, templates_df, pattern_df, numeric_df = summarize_logs()
    numeric_summary_df = summarize_cart_numeric_fields(numeric_df)
    timeline_df = build_timeline(threshold_df, pattern_df, templates_df)

    summary_df.to_csv(OUT / "metric_summary.csv", index=False)
    gap_df.to_csv(OUT / "metric_gaps.csv", index=False)
    z_df.to_csv(OUT / "rolling_z_anomalies.csv", index=False)
    if_df.to_csv(OUT / "isolation_forest_cart_anomalies.csv", index=False)
    threshold_df.to_csv(OUT / "sustained_thresholds.csv", index=False)
    metric_signal_df.to_csv(OUT / "metric_anomaly_signals.csv", index=False)
    templates_df.to_csv(OUT / "drain3_template_spikes.csv", index=False)
    pattern_df.to_csv(OUT / "log_pattern_summary.csv", index=False)
    numeric_df.to_csv(OUT / "cart_log_numeric_fields.csv", index=False)
    numeric_summary_df.to_csv(OUT / "cart_log_numeric_summary.csv", index=False)
    timeline_df.to_csv(OUT / "incident_timeline.csv", index=False)

    # Keep the full parsed event table compact enough for review.
    events_df[["timestamp", "level", "service", "pod", "template", "message"]].to_csv(
        OUT / "drain3_parsed_logs.csv", index=False
    )

    plot_cart_timeline()
    plot_cart_log_numeric_fields(numeric_df)

    print("Wrote analysis outputs to", OUT)
    print("Wrote plot to", PLOTS / "cart_timeline.png")
    print("\nTimeline")
    print(timeline_df.to_string(index=False))
    print("\nRolling Z-score anomalies")
    print(z_df.to_string(index=False))
    print("\nIsolation Forest cart anomalies")
    print(if_df.to_string(index=False))


if __name__ == "__main__":
    main()
