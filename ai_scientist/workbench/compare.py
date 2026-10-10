"""Compare approved run protocols; optionally use MLflow for tracked scores/curves."""
import math

from .mlflow_tracking import sync_comparison, tracking_uri
from .store import canonical


def _valid_result(row):
    metric = row["metric"]
    spec = row["protocol"]["metric"]
    return (
        row["state"] == "COMPLETED"
        and isinstance(metric, dict)
        and isinstance(spec, dict)
        and metric.get("name") == spec.get("name")
        and metric.get("direction") == spec.get("direction")
        and metric.get("direction") in {"maximize", "minimize"}
        and type(metric.get("final_value")) in (int, float)
        and math.isfinite(metric["final_value"])
    )


def compare_runs(working, project_id, run_ids):
    if not 2 <= len(run_ids) <= 8 or len(set(run_ids)) != len(run_ids):
        raise ValueError("Choose 2–8 distinct runs to compare")
    rows = []
    for run_id in run_ids:
        detail = working.detail(project_id, run_id)
        approved = working.store.approved_snapshot(project_id, run_id)
        body, snapshot = approved["body"], approved["snapshot"]
        selected = set(body.get("data_refs") or [])
        sources = sorted(
            (resource["id"], resource["version"], resource["content_sha256"])
            for resource in snapshot["resources"] if resource["id"] in selected
        )
        protocol = {
            "mode": detail["mode"], "data": sources,
            "split": body.get("split"), "metric": body.get("metric"),
        }
        row = {
            "run_id": run_id, "title": detail["title"], "purpose": detail["purpose"],
            "state": detail["state"], "account": detail.get("account"),
            "parent_run_id": (detail.get("variant") or {}).get("parent_run_id")
                             or detail.get("parent_run_id"),
            "metric": detail.get("result_metric"), "protocol": protocol,
            "budget": body.get("budget") if isinstance(body.get("budget"), dict) else {},
        }
        record = working.record(project_id, run_id) if hasattr(working, "record") else None
        row["points"] = working.records.logs(project_id, run_id, limit=1)["points"] if record else []
        rows.append(row)

    warnings = []
    if any(row["protocol"]["mode"] != "training_research" for row in rows):
        warnings.append("Run Etc không có protocol training để xếp hạng metric chung.")
    for field, label in (("data", "nguồn dữ liệu"), ("split", "split"), ("metric", "metric")):
        if any(not row["protocol"][field] for row in rows):
            warnings.append(f"Thiếu {label} trong protocol đã duyệt; chưa thể xác nhận cùng phép đo.")
        if len({canonical(row["protocol"][field]) for row in rows}) > 1:
            warnings.append(f"Khác {label} đã duyệt; không xếp hạng chung.")
    comparable = not warnings

    # Budget differences are meaningful caveats, not a different evaluation
    # dataset/metric; do not silently make rankings impossible.
    fairness_warnings = []
    for key in ("training_seconds", "execution_seconds"):
        values = [row["budget"].get(key) for row in rows]
        if any(value is not None for value in values) and len({canonical(v) for v in values}) > 1:
            fairness_warnings.append(f"Khác budget {key}; kết quả có thể không công bằng.")

    backend = "workbench"
    tracking_warning = None
    if tracking_uri():
        try:
            if sync_comparison(project_id, rows):
                backend = "mlflow"
        except Exception as exc:
            # Tracking is a projection: its outage must never fail Workbench
            # comparisons or mutate the underlying successful Kaggle run.
            tracking_warning = (
                f"MLflow chưa đồng bộ được ({type(exc).__name__}); "
                "đang dùng metric đã xác minh từ Workbench."
            )

    metrics = [row["metric"] for row in rows]
    if comparable and (any(not _valid_result(row) for row in rows)
                       or len({(metric.get("name"), metric.get("direction"))
                               for metric in metrics if metric}) != 1):
        warnings.append("Chưa có metric cuối hợp lệ cho mọi run; chưa thể xếp hạng.")
    ranked = []
    if not warnings:
        reverse = metrics[0]["direction"] == "maximize"
        ranked = [row["run_id"] for row in sorted(
            rows, key=lambda row: row["metric"]["final_value"], reverse=reverse
        )]
    return {
        "runs": rows, "same_protocol": comparable, "warnings": warnings,
        "fairness_warnings": fairness_warnings, "tracking_backend": backend,
        "tracking_warning": tracking_warning, "ranked_run_ids": ranked,
    }
