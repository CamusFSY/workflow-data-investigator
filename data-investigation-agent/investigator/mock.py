"""Explicitly SCRIPTED development driver. Not a model or autonomy benchmark.

This narrow script knows the local development table vocabulary. It chooses branches
from observations, never fixture paths/case IDs. Live orchestration never imports it.
"""
import json

from .providers import selection

CANONICAL_CTE = """
WITH completion AS (
  SELECT order_id, MAX(delivered_at_utc) AS completed_at,
         COUNT(*) = COUNT(delivered_at_utc) AS all_delivered
  FROM shipments GROUP BY order_id
), eligible AS (
  SELECT p.label AS period, o.order_id, o.warehouse_id,
         CASE WHEN c.all_delivered = 1 AND c.completed_at <= o.promised_delivery_at_utc
              THEN 1 ELSE 0 END AS on_time
  FROM orders o
  JOIN reporting_periods p ON o.promised_delivery_at_utc >= p.starts_at_utc
    AND o.promised_delivery_at_utc < p.ends_at_utc
  LEFT JOIN completion c ON c.order_id = o.order_id
  WHERE o.order_status <> 'cancelled'
)
"""
CANONICAL = CANONICAL_CTE + """
SELECT period, COUNT(*) AS total, SUM(on_time) AS on_time
FROM eligible GROUP BY period ORDER BY period
"""
GROUPS = CANONICAL_CTE + """
SELECT e.period, w.region_code AS region, COUNT(*) AS total, SUM(e.on_time) AS on_time
FROM eligible e JOIN warehouses w ON w.warehouse_id = e.warehouse_id
GROUP BY e.period, w.region_code ORDER BY e.period, w.region_code
"""
FANOUT = """
SELECT p.label AS period,
       CASE WHEN s.delivered_at_utc <= o.promised_delivery_at_utc
            THEN 'on_time' ELSE 'late' END AS outcome,
       COUNT(*) AS joined_rows, COUNT(DISTINCT o.order_id) AS distinct_orders
FROM orders o JOIN reporting_periods p
  ON o.promised_delivery_at_utc >= p.starts_at_utc AND o.promised_delivery_at_utc < p.ends_at_utc
JOIN shipments s ON s.order_id = o.order_id
WHERE o.order_status <> 'cancelled'
GROUP BY p.label, outcome ORDER BY p.label, outcome
"""


class ScriptedMock:
    mode = "mock-scripted"
    label = "SCRIPTED MOCK / local development fixture vocabulary"

    def __init__(self, inject_schema_error=False):
        self.stage = "catalog"
        self.refs = {}
        self.values = {}
        self.pending = None
        self.number = 0
        self.inject_error = inject_schema_error
        self.repaired = False

    def next(self, messages, tools, timeout_seconds):
        self.number += 1
        if self.pending:
            observed = json.loads(messages[-1]["content"])
            self.refs[self.pending] = observed["evidence_id"]
            self.values[self.pending] = observed
            self.pending = None

        def emit(key, tool, args, note, next_stage):
            self.pending = key
            self.stage = next_stage
            return selection(self.number, tool, args, note)

        def rates(key):
            return {"operation": "compare_rates", "evidence_id": self.refs[key],
                    "period": "period", "baseline": "baseline", "current": "current",
                    "successes": "on_time", "total": "total"}

        stage = self.stage
        if stage == "catalog":
            return emit("catalog", "read_context", {"document": "catalog"},
                        "MOCK：读取公共目录与指标口径。", "metric")
        if stage == "metric":
            return emit("metric", "read_context", {"document": "metric"},
                        "MOCK：确认指标的业务定义。", "definition")
        if stage == "definition":
            contract = self.values["catalog"]["data"].get("metric", {})
            missing = [k for k in ("time_basis", "cancelled_orders") if not contract.get(k)]
            if missing:
                questions = []
                if "time_basis" in missing:
                    questions.append("“上周”按承诺交付日期还是实际发货日期分组？请给 UTC 起止时间。")
                if "cancelled_orders" in missing:
                    questions.append("取消订单是否从准时交付率分母中剔除？")
                return selection(self.number, "finish", {
                    "status": "needs_clarification",
                    "summary": "缺少影响分母和周归属的关键口径，暂不能判断是否真的延误。",
                    "findings": [{"text": "公共指标说明未确定时间归属/取消订单规则。",
                                  "evidence": [self.refs["catalog"], self.refs["metric"]]}],
                    "questions": questions,
                }, "MOCK：口径不足，提出具体问题并停止下结论。")
            return emit("dashboard_text", "read_context", {"document": "dashboard"},
                        "MOCK：读取产生看板数字的原始 SQL。", "schema")
        if stage == "schema":
            return emit("schema", "inspect_schema", {}, "MOCK：核对实际列名与表结构。",
                        "bad_column" if self.inject_error else "dashboard")
        if stage == "bad_column":
            return emit("bad_column", "query",
                        {"sql": "SELECT order_id, promised_timestamp FROM orders LIMIT 3"},
                        "MOCK 故障演练：刻意查询不存在的列。", "observe_error")
        if stage == "observe_error":
            if self.values["bad_column"]["ok"]:
                raise ValueError("Expected controlled schema error was not observed")
            return emit("repair_schema", "inspect_schema", {},
                        "MOCK：已观察到 SQL 错误，重新查 schema。", "repair")
        if stage == "repair":
            tables = self.values["repair_schema"]["data"]["tables"]
            cols = next(t["columns"] for t in tables if t["name"] == "orders")
            if "promised_delivery_at_utc" not in {c["name"] for c in cols}:
                raise ValueError("Development schema is unsupported; do not guess a repair")
            return emit("repair", "query",
                        {"sql": "SELECT order_id, promised_delivery_at_utc FROM orders LIMIT 3"},
                        "MOCK：按返回的 schema 改为 promised_delivery_at_utc，再执行。", "dashboard")
        if stage == "dashboard":
            return emit("dashboard", "query",
                        {"sql": self.values["dashboard_text"]["data"]["text"]},
                        "MOCK：复现看板原始计算。", "dashboard_analysis")
        if stage == "dashboard_analysis":
            return emit("dashboard_analysis", "analyze", rates("dashboard"),
                        "MOCK：计算观察到的看板变化。", "canonical")
        if stage == "canonical":
            return emit("canonical", "query", {"sql": CANONICAL},
                        "MOCK：按订单粒度重算，避免 1:N 关联重复加权。", "canonical_analysis")
        if stage == "canonical_analysis":
            return emit("canonical_analysis", "analyze", rates("canonical"),
                        "MOCK：比较真实订单层面的准时率和延误数。", "branch")
        if stage == "branch":
            dashboard = self.values["dashboard_analysis"]["data"]
            canonical = self.values["canonical_analysis"]["data"]
            self.distorted = any(
                abs(dashboard[p]["rate"] - canonical[p]["rate"]) > 1e-9
                for p in ("baseline", "current"))
            if self.distorted:
                return emit("fanout", "query", {"sql": FANOUT},
                            "MOCK：两种粒度结果不同，检查关联行数与订单数。", "plot")
            return emit("groups", "query", {"sql": GROUPS},
                        "MOCK：订单层面也下降，按地区检查受影响群组。", "group_analysis")
        if stage == "group_analysis":
            return emit("group_analysis", "analyze",
                        {**rates("groups"), "operation": "cohort_change", "group": "region"},
                        "MOCK：量化每个群组的变化，避免把相关性说成原因。", "plot")
        if stage == "plot":
            return emit("plot", "plot",
                        {"evidence_id": self.refs["canonical"], "label": "period",
                         "successes": "on_time", "total": "total"},
                        "MOCK：用实际聚合结果绘图。", "finish")
        if stage == "finish":
            d = self.values["dashboard_analysis"]["data"]
            c = self.values["canonical_analysis"]["data"]
            findings = [{
                "text": (f"看板准时率 {d['baseline']['rate']:.1%} → {d['current']['rate']:.1%}；"
                         f"按订单重算 {c['baseline']['rate']:.1%} → {c['current']['rate']:.1%}，"
                         f"变化 {c['delta_percentage_points']:.1f} 个百分点。"),
                "evidence": [self.refs["dashboard_analysis"], self.refs["canonical_analysis"]],
            }]
            if self.distorted:
                changed = c["delta_percentage_points"] < -1e-9
                summary = ("看板存在关联加权失真；订单层面也有下降。" if changed else
                           "看板下降来自 1:N 关联加权；按订单口径，未观察到准时率下降。")
                findings.append({
                    "text": "关联行数与唯一订单数不一致；原 SQL 对不同订单赋予了不同权重。",
                    "evidence": [self.refs["fanout"], self.refs["dashboard_text"]],
                })
            else:
                groups = self.values["group_analysis"]["data"]["groups"]
                affected = [g for g in groups if g["delta_percentage_points"] < -1e-9]
                summary = ("订单层面确认准时率下降，以下群组贡献了延误数增加。" if affected else
                           "订单层面未观察到准时率下降。")
                for group in affected:
                    findings.append({
                        "text": (f"{group['group']}：{group['baseline']['rate']:.1%} → "
                                 f"{group['current']['rate']:.1%}；非分子计数变化 "
                                 f"{group['non_success_count_change']:+d}。这是分组定位，尚非因果解释。"),
                        "evidence": [self.refs["groups"], self.refs["group_analysis"]],
                    })
            findings.append({"text": "仅为小型合成数据的描述性结果；未进行显著性或因果推断。",
                             "evidence": [self.refs["canonical_analysis"]]})
            return selection(self.number, "finish", {
                "status": "answered", "summary": summary, "findings": findings, "questions": [],
            }, "MOCK：交付带证据引用的报告和可复跑 notebook。")
        raise ValueError("Unsupported scripted stage")
