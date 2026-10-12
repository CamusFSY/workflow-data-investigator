"""Reviewed, fixed statistical and SVG operations; no eval, exec, or model code."""
import html
import math
import json

from .provenance import data_label


def counts(row, successes, total):
    good, n = row[successes], row[total]
    if (type(good) not in {int, float} or type(n) not in {int, float}
            or not math.isfinite(good) or not math.isfinite(n)
            or int(good) != good or int(n) != n or not 0 <= good <= n or n <= 0):
        raise ValueError("Need finite integer counts with 0 <= successes <= total and total > 0")
    return int(good), int(n)


def rate_source(args, *dimensions):
    # Column bindings are provenance, not validated business definitions.
    # No typed metric contract is implemented, so no domain labels are inferred.
    return {"rate_semantics": "untyped_ratio",
            "source_columns": {key: args[key] for key in ("successes", "total", *dimensions)}}


def comparison(rows, args):
    if args["baseline"] == args["current"]:
        raise ValueError("baseline and current must name distinct periods")
    before = [r for r in rows if r[args["period"]] == args["baseline"]]
    after = [r for r in rows if r[args["period"]] == args["current"]]
    if len(before) != 1 or len(after) != 1 or len(rows) != 2:
        raise ValueError("Need exactly one aggregate row per requested period")
    bg, bn = counts(before[0], args["successes"], args["total"])
    ag, an = counts(after[0], args["successes"], args["total"])
    return {
        "baseline": {"period": args["baseline"], "successes": bg, "total": bn,
                     "rate": bg / bn, "non_successes": bn - bg},
        "current": {"period": args["current"], "successes": ag, "total": an,
                    "rate": ag / an, "non_successes": an - ag},
        "delta_percentage_points": (ag / an - bg / bn) * 100,
        "non_success_count_change": (an - ag) - (bn - bg),
        "scope": "Descriptive arithmetic on selected columns only. non_successes = total - successes; "
                 "this complement is not necessarily late. Metric meaning, business approval, "
                 "causality and statistical significance are not verified.",
    }


def analyze(rows, args):
    if args["operation"] == "compare_rates":
        return {**comparison(rows, args), **rate_source(args, "period")}
    if args["operation"] == "cohort_change":
        group = args["group"]
        names = sorted({r[group] for r in rows}, key=str)
        results = []
        for name in names:
            selected = [r for r in rows if r[group] == name]
            result = comparison(selected, args)
            results.append({"group": name, **result})
        return {"groups": sorted(results, key=lambda x: x["delta_percentage_points"]),
                **rate_source(args, "period", "group"),
                "scope": "Within-group arithmetic on selected columns; metric meaning and business "
                         "approval are unverified. Equal ratios do not imply equal metrics or root cause."}
    raise ValueError("Unsupported analysis operation")


def bar_chart(rows, args, *, provenance=None):
    if not 1 <= len(rows) <= 12:
        raise ValueError("Chart requires 1..12 aggregate rows")
    points = []
    for row in rows:
        good, total = counts(row, args["successes"], args["total"])
        points.append({"label": str(row[args["label"]]), "rate": good / total,
                       "successes": good, "non_successes": total - good, "total": total})
    label = data_label(provenance)
    binding = f"successes: {args['successes']} / total: {args['total']}"
    visible_binding = binding if len(binding) <= 80 else binding[:77] + "..."
    height = 107 + len(points) * 56
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 {height}" '
        f'role="img" aria-label="Observed untyped ratios from query columns, {label}">',
        '<metadata>' + html.escape(json.dumps(provenance or {"type": "synthetic"}, ensure_ascii=False)) + '</metadata>',
        f'<desc>{html.escape(binding)}. Metric meaning and business approval are unverified.</desc>',
        f'<rect width="700" height="{height}" rx="12" fill="#f3f6fb"/>',
        '<text x="22" y="30" fill="#17304d" font-family="sans-serif" font-size="17">'
        f'Observed ratio · UNTYPED · {label}</text>',
        f'<text x="22" y="52" fill="#17304d" font-family="sans-serif" font-size="12">'
        f'<title>{html.escape(binding)}</title>{html.escape(visible_binding)}</text>',
    ]
    for index, point in enumerate(points):
        y = 82 + index * 56
        label = html.escape(point["label"][:40])
        chunks.extend([
            f'<text x="22" y="{y + 18}" font-family="sans-serif" font-size="13">{label}</text>',
            f'<rect x="170" y="{y}" width="360" height="26" rx="4" fill="#dce4ef"/>',
            f'<rect x="170" y="{y}" width="{point["rate"] * 360:.2f}" height="26" '
            'rx="4" fill="#007f7a"/>',
            f'<text x="545" y="{y + 18}" font-family="sans-serif" font-size="13">'
            f'{point["rate"]:.1%} ({point["successes"]}/{point["total"]})</text>',
        ])
    chunks.append("</svg>")
    return {"points": points, "svg": "".join(chunks), **rate_source(args, "label")}
