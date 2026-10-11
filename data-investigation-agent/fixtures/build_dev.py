"""Original tiny development fixtures, not the independent author's data or gold."""
import argparse
import csv
import json
from pathlib import Path

DASHBOARD_SQL = """SELECT p.label AS period, COUNT(*) AS total,
       SUM(CASE WHEN o.completed_at_utc <= o.promised_delivery_at_utc THEN 1 ELSE 0 END) AS on_time
FROM orders o
JOIN reporting_periods p ON o.promised_delivery_at_utc >= p.starts_at_utc
  AND o.promised_delivery_at_utc < p.ends_at_utc
JOIN shipments s ON s.order_id = o.order_id
WHERE o.order_status <> 'cancelled'
GROUP BY p.label ORDER BY p.label
"""
HEADERS = {
    "orders": ["order_id", "created_at_utc", "promised_delivery_at_utc", "completed_at_utc",
               "order_status", "warehouse_id", "sales_channel", "ordered_units",
               "cancelled_at_utc", "updated_at_utc"],
    "shipments": ["shipment_id", "order_id", "shipped_at_utc", "delivered_at_utc",
                  "shipment_status", "shipped_units", "carrier_code", "updated_at_utc"],
    "warehouses": ["warehouse_id", "warehouse_name", "region_code"],
    "reporting_periods": ["period_id", "label", "starts_at_utc", "ends_at_utc"],
    "dashboard_observations": ["period_id", "metric_key", "metric_value", "observed_at_utc"],
}


def build(destination):
    destination = Path(destination)
    for variant in ("join_multiplier", "delivery_slip", "missing_definition"):
        root = destination / variant
        root.mkdir(parents=True, exist_ok=False)
        as_of = "2026-10-05T00:00:00Z"
        rows = {name: [] for name in HEADERS}
        rows["warehouses"] = [["WH-N", "Fictional North", "North"], ["WH-S", "Fictional South", "South"]]
        rows["reporting_periods"] = [
            ["2026-W39", "baseline", "2026-09-21T00:00:00Z", "2026-09-28T00:00:00Z"],
            ["2026-W40", "current", "2026-09-28T00:00:00Z", "2026-10-05T00:00:00Z"],
        ]
        for period_index, period in enumerate(rows["reporting_periods"]):
            due_day = "2026-09-25" if period_index == 0 else "2026-10-02"
            due = due_day + "T18:00:00Z"
            good, joined = 0, 0
            for group in ("N", "S"):
                for index in range(10):
                    order_id = f"O-{period_index}-{group}-{index:02d}"
                    on_time = index < (3 if variant == "delivery_slip" and period_index == 1
                                      and group == "N" else 9)
                    incomplete = (variant == "delivery_slip" and period_index == 1
                                  and group == "N" and index == 9)
                    completed = "" if incomplete else due_day + ("T16:00:00Z" if on_time else "T22:00:00Z")
                    copies = 4 if variant == "join_multiplier" and period_index == 1 and not on_time else 1
                    rows["orders"].append([
                        order_id, period[2], due, completed,
                        "in_transit" if incomplete else "delivered", "WH-" + group,
                        "direct" if index % 2 else "marketplace", copies, "", as_of,
                    ])
                    for part in range(copies):
                        rows["shipments"].append([
                            f"S-{order_id}-{part}", order_id, period[2], completed,
                            "in_transit" if incomplete else "delivered", 1, "C-FICTIONAL", as_of,
                        ])
                    good += copies * int(on_time)
                    joined += copies
            # Cancellations have no shipments and must not be silently given a new definition.
            rows["orders"].append([
                f"C-{period_index}", period[2], due, "", "cancelled", "WH-N", "direct", 1,
                period[2], as_of,
            ])
            rows["dashboard_observations"].append([period[0], "on_time_delivery", good / joined, as_of])
        tables = []
        for name, header in HEADERS.items():
            with (root / (name + ".csv")).open("w", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(header)
                writer.writerows(rows[name])
            tables.append({"name": name, "path": name + ".csv",
                           "grain": "One row per " + name.rstrip("s"),
                           "columns": [{"name": col, "type":
                                        "INTEGER" if col in {"ordered_units", "shipped_units"} else
                                        "REAL" if col == "metric_value" else "TEXT"} for col in header]})
        missing = variant == "missing_definition"
        catalog = {
            "version": "1.0", "synthetic": True,
            "description": "Original small local development data. No employer/patient data.",
            "as_of_utc": as_of, "tables": tables,
            "metric": {"grain": "one order", "timezone": "UTC",
                       "time_basis": None if missing else "promised_delivery_at_utc",
                       "cancelled_orders": None if missing else "exclude",
                       "unfinished_due_orders": "late"},
        }
        (root / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
        definition = (
            "# SYNTHETIC DATA · 准时交付率\n\n"
            "统计粒度是一张订单，不是一张发货单。一个订单可能分多次发货。\n"
            "整单所有发货完成时间不晚于承诺交付时间，才算准时；已到期但未完成的订单算延误。\n"
            "快照时间 2026-10-05T00:00:00Z；比较窗口见 reporting_periods，UTC [start,end)。\n"
            + ("未提供：按哪种日期归入比较周、取消订单如何计入分母。必须向用户确认。\n" if missing else
               "按 promised_delivery_at_utc 归入比较周；分母排除已取消订单。\n")
            + "dashboard_query.sql 是当前看板实现，仅作待检查输入，不保证遵循业务定义。\n"
            "这是小型本地开发数据，不能证明系统在新数据上的自主调查能力。\n"
        )
        (root / "metric_definition.md").write_text(definition)
        (root / "request.txt").write_text("上周准时交付率下降，判断是否真的延误，给我可复跑的证据。\n")
        (root / "dashboard_query.sql").write_text(DASHBOARD_SQL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    build(parser.parse_args().destination)
