from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "lab" / "architecture" / "diagrams"


def box(ax, x, y, w, h, text, fc="#f8fafc", ec="#334155", fs=9):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.03",
        linewidth=1.2,
        edgecolor=ec,
        facecolor=fc,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, wrap=True)


def arrow(ax, x1, y1, x2, y2):
    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops={"arrowstyle": "->", "lw": 1.4, "color": "#475569"},
    )


def poly_arrow(ax, points):
    xs, ys = zip(*points)
    if len(points) > 2:
        ax.plot(xs[:-1], ys[:-1], color="#475569", lw=1.4)
    ax.annotate(
        "",
        xy=points[-1],
        xytext=points[-2],
        arrowprops={"arrowstyle": "->", "lw": 1.4, "color": "#475569"},
    )


def save_architecture_overview():
    fig, ax = plt.subplots(figsize=(15, 9))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 10)
    ax.axis("off")

    layers = [
        (0.5, 8.4, 14, 1.0, "Kubernetes Services\napi-gateway | product-service | cart-service | order-service | payment-service", "#e0f2fe"),
        (0.5, 6.8, 14, 1.0, "Telemetry Collection\nPrometheus scrape | Promtail logs | OpenTelemetry Collector | Kubernetes Event Exporter", "#dcfce7"),
        (0.5, 5.2, 14, 1.0, "Telemetry Storage\nPrometheus TSDB | Loki | Tempo | Postgres incident store", "#fef9c3"),
        (0.5, 3.6, 14, 1.0, "AIOps Batch Detector\nPython CronJob: metric detectors | Drain3 log miner | K8s event detector | trace correlation", "#ffedd5"),
        (0.5, 2.0, 14, 1.0, "Correlation & Intelligence\nNormalizer | Dependency graph | Incident scoring | RCA hypothesis engine", "#ede9fe"),
        (0.5, 0.4, 14, 1.0, "Output & Action\nGrafana dashboard | Alertmanager | Slack webhook | Markdown incident report", "#fee2e2"),
    ]
    for x, y, w, h, text, color in layers:
        box(ax, x, y, w, h, text, fc=color, fs=11)
    for y1, y2 in [(8.4, 7.8), (6.8, 6.2), (5.2, 4.6), (3.6, 3.0), (2.0, 1.4)]:
        arrow(ax, 7.5, y1, 7.5, y2)

    ax.set_title("AIOps Incident Detection & Triage Architecture", fontsize=16, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "aiops_architecture_overview.png", dpi=170)
    plt.close(fig)


def save_dependency_graph():
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.axis("off")

    w = 2.1
    h = 0.7
    nodes = {
        "User": (0.6, 3.45),
        "api-gateway": (3.0, 3.45),
        "cart-service": (6.1, 4.85),
        "order-service": (6.1, 2.15),
        "product-service": (10.2, 4.85),
        "payment-service": (10.2, 2.15),
        "notification-service": (10.2, 0.65),
    }
    for name, (x, y) in nodes.items():
        color = "#fee2e2" if name == "cart-service" else "#f8fafc"
        box(ax, x, y, w, h, name, fc=color)

    def left(name):
        x, y = nodes[name]
        return x, y + h / 2

    def right(name):
        x, y = nodes[name]
        return x + w, y + h / 2

    def top(name):
        x, y = nodes[name]
        return x + w / 2, y + h

    def bottom(name):
        x, y = nodes[name]
        return x + w / 2, y

    def curved(start, end, rad=0.0, dashed=False):
        patch = FancyArrowPatch(
            start,
            end,
            arrowstyle="->",
            mutation_scale=12,
            linewidth=1.45,
            color="#475569",
            linestyle="--" if dashed else "-",
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=6,
            shrinkB=6,
        )
        ax.add_patch(patch)

    # Primary request/dependency paths. Curves are separated so they do not cross boxes.
    curved(right("User"), left("api-gateway"))
    curved(right("api-gateway"), left("cart-service"), rad=0.12)
    curved(right("api-gateway"), left("order-service"), rad=-0.12)
    curved(right("cart-service"), left("product-service"))
    curved(top("order-service"), bottom("cart-service"))
    curved(right("order-service"), left("payment-service"))
    curved(right("order-service"), left("notification-service"), rad=-0.18)

    # Optional direct product read from gateway, routed as a light dashed upper arc.
    curved(top("api-gateway"), top("product-service"), rad=0.28, dashed=True)
    ax.text(7.2, 6.55, "optional product read", fontsize=8, color="#64748b", ha="center")

    ax.set_title("Service Dependency Graph", fontsize=16, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "service_dependency_graph.png", dpi=170)
    plt.close(fig)


def save_incident_pipeline():
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7)
    ax.axis("off")

    steps = [
        ("Telemetry\nPrometheus/Loki/Tempo/K8s events", 0.5, 3.1, "#e0f2fe"),
        ("Python CronJob\nquery last window", 3.0, 3.1, "#dcfce7"),
        ("Detector registry\nIQR/EWMA/Drain3/events", 5.5, 3.1, "#fef9c3"),
        ("Correlation\nservice + time + graph", 8.0, 3.1, "#ede9fe"),
        ("Postgres\nincident candidates", 10.5, 3.1, "#ffedd5"),
        ("Alert + Report\nGrafana/Alertmanager", 12.5, 3.1, "#fee2e2"),
    ]
    for text, x, y, color in steps:
        box(ax, x, y, 1.8, 0.9, text, fc=color, fs=8.5)
    for i in range(len(steps) - 1):
        x1 = steps[i][1] + 1.8
        y1 = steps[i][2] + 0.45
        x2 = steps[i + 1][1]
        y2 = steps[i + 1][2] + 0.45
        arrow(ax, x1, y1, x2, y2)

    evidence = [
        ("06:32 cache eviction", 3.0, 1.4),
        ("14:00 log spike", 4.7, 1.4),
        ("18:06 GC anomaly", 6.4, 1.4),
        ("19:59 OOMKilled", 8.1, 1.4),
        ("20:00 restart", 9.8, 1.4),
        ("downstream errors", 11.5, 1.4),
    ]
    for text, x, y in evidence:
        box(ax, x, y, 1.45, 0.55, text, fc="#ffffff", fs=7.5)
        arrow(ax, x + 0.7, y + 0.55, x + 0.7, 3.1)

    ax.set_title("Runtime AIOps Pipeline", fontsize=16, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "runtime_aiops_pipeline.png", dpi=170)
    plt.close(fig)


def save_cart_prometheus_mvp():
    fig, ax = plt.subplots(figsize=(15, 8.5))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 8)
    ax.axis("off")

    box(ax, 0.5, 5.8, 2.3, 0.9, "Selected service\ncart-service", fc="#fee2e2", fs=10)
    box(ax, 0.5, 3.7, 2.3, 0.9, "Supporting logs\ncart-service.log", fc="#f8fafc", fs=10)
    box(ax, 0.5, 1.6, 2.3, 0.9, "Supporting events\nOOMKilled / restart", fc="#f8fafc", fs=10)

    box(ax, 3.6, 5.8, 2.3, 0.9, "Chosen core tool\nPrometheus", fc="#dcfce7", fs=10)
    box(ax, 3.6, 3.7, 2.3, 0.9, "Loki + Drain3\nlog template spike", fc="#fef9c3", fs=9)
    box(ax, 3.6, 1.6, 2.3, 0.9, "K8s Event Exporter\nrestart/OOM signal", fc="#fef9c3", fs=9)

    box(ax, 6.8, 5.8, 2.4, 0.9, "Metric detectors\nBaseline IQR / EWMA\nCounter delta", fc="#e0f2fe", fs=9)
    box(ax, 6.8, 3.7, 2.4, 0.9, "Evidence normalizer\nservice + timestamp", fc="#e0f2fe", fs=9)
    box(ax, 6.8, 1.6, 2.4, 0.9, "Severity confirmer\nOOM + restart", fc="#e0f2fe", fs=9)

    box(ax, 10.2, 4.6, 2.1, 0.9, "Correlation window\nsame service + time", fc="#ede9fe", fs=9)
    box(ax, 12.9, 4.6, 1.6, 0.9, "Incident\ncandidate", fc="#ffedd5", fs=9)

    box(ax, 10.2, 2.5, 4.3, 0.9, "Root cause hypothesis\ncart-service memory pressure from ProductCatalogCache", fc="#fee2e2", fs=9)

    arrow(ax, 2.8, 6.25, 3.6, 6.25)
    arrow(ax, 5.9, 6.25, 6.8, 6.25)
    arrow(ax, 9.2, 6.25, 10.2, 5.05)
    arrow(ax, 12.3, 5.05, 12.9, 5.05)

    arrow(ax, 2.8, 4.15, 3.6, 4.15)
    arrow(ax, 5.9, 4.15, 6.8, 4.15)
    arrow(ax, 9.2, 4.15, 10.2, 4.95)

    arrow(ax, 2.8, 2.05, 3.6, 2.05)
    arrow(ax, 5.9, 2.05, 6.8, 2.05)
    arrow(ax, 9.2, 2.05, 10.2, 2.95)
    arrow(ax, 11.25, 4.6, 11.25, 3.4)

    timeline = [
        ("16:39Z\nmemory drift", 4.2),
        ("18:xxZ\nGC pressure", 6.25),
        ("19:59Z\nOOMKilled", 8.3),
        ("20:00Z\nrestart", 10.35),
    ]
    ax.text(0.8, 1.02, "Evidence timeline for cart-service", fontsize=9, weight="bold", color="#334155")
    for idx, (text, x) in enumerate(timeline):
        box(ax, x, 0.75, 1.45, 0.55, text, fc="#ffffff", fs=7.5)
        if idx < len(timeline) - 1:
            arrow(ax, x + 1.45, 1.025, timeline[idx + 1][1], 1.025)
    ax.set_title("MVP Tool Choice: Prometheus for cart-service Incident Detection", fontsize=15, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "mvp_prometheus_cart_service_pipeline.png", dpi=170)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    save_architecture_overview()
    save_dependency_graph()
    save_incident_pipeline()
    save_cart_prometheus_mvp()
    print(f"Diagrams written to {OUT}")


if __name__ == "__main__":
    main()
