import html
import json
from pathlib import Path

from .bundle import digest, safe_read
from .artifact_format import MAX_MANIFEST_BYTES, MAX_ARTIFACT_BYTES, json_text, write_artifact
from .provenance import data_label

REPLAY_FILES = ["__init__.py", "bundle.py", "runtime.py", "sql_worker.py", "analytics.py", "replay.py", "provenance.py", "evidence.py", "artifact_format.py"]
RATE_NOTICE = ("通用分析/图表仅计算选定查询列的 successes / total；non_successes 是 total - successes，"
               "不能据此自动解释为准时/延误。列名和 source_evidence_id 保留来源，不代表已验证业务口径。"
               "模型/脚本的自由文本解读、因果说法和业务批准仍未经算术验证。")
REPLAY_SCRIPT = """import sys
from pathlib import Path
sys.dont_write_bytecode = True
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "_replay"))
from investigator.replay import verify
verify(root)
"""


def cell(kind, source):
    result = {"cell_type": kind, "metadata": {}, "source": source.splitlines(keepends=True)}
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


def qualification(outcome):
    if outcome.get("clarification_block"):
        return "调查停止：澄清状态容量已满；新声明的阻塞未能完整记录，禁止继续给出结论。"
    if outcome["status"] == "conditional":
        return "条件性结果：仅在列出的假设成立时适用；尚未完成无条件判断。"
    if outcome["status"] == "needs_clarification":
        return "待澄清：关键问题尚未解决，不能作最终业务判断。"
    if outcome["failure"] and any(q["resolution"] is None for q in outcome.get("clarifications", [])):
        return "调查失败；已声明的阻塞问题仍未解决。"
    return "调查未完成。" if outcome["failure"] else ""


def evidence_roles(outcome):
    """Presentation only: never infer an answer from a support or an older query."""
    if outcome.get("evidence_interface") != "answer_roles_v1":
        return None
    answer = outcome.get("answer") or {}
    return {"answer_evidence_id": answer.get("answer_evidence_id"),
            "supporting_evidence_ids": answer.get("supporting_evidence_ids", []),
            "caller_answer_contract": outcome["answer_contract"],
            "answer_contract_sha256": outcome["answer_contract_sha256"],
            "validation_scope": "Source/type/shape only; not numerical correctness or support relevance"}


def notebook(events, outcome):
    answer = outcome["answer"] or {}
    pending = [q["question"] for q in outcome.get("clarifications", [])
               if q["resolution"] is None and (not answer or q.get("kind") != "assumption")]
    scope = f"\n\n交付状态：{outcome['status']}。{qualification(outcome)}"
    roles = evidence_roles(outcome)
    if roles is not None:
        scope += "\n\n答案证据与支持证据（调用方契约；不代表数值正确）：\n\n```json\n" + json_text(roles) + "\n```"
    if answer.get("conditions"):
        scope += "\n\n适用假设（未经确认）：\n\n" + "\n".join("- " + q for q in answer["conditions"])
    if pending:
        scope += "\n\n仍需澄清：\n\n" + "\n".join("- " + q for q in pending)
    cells = [
        cell("markdown", "# 可复跑调查证据\n\n**" + data_label(outcome.get("provenance")) + " · " + outcome["disclosure"] +
             f"**\n\n实际工具动作：{outcome['tool_actions']}；"
             f"调查完成：{'是' if outcome['investigation_complete'] else '否'}。" + scope +
             "\n\n只重放本次实际 SQL 与固定 Python 统计操作；不调用模型。"
             "错误也会重放并与原错误比较；可信调用方的澄清只重放原记录，不重新核验来源权威性。"
             "请从本 notebook 所在目录启动 kernel。"
             "分析函数源代码随产物保存在 _replay/investigator/analytics.py。"
             "这不是任意 Python Agent 执行入口。\n\n" + RATE_NOTICE + "\n\n来源记录（声明及冻结审核记录，不是重新认证）：\n\n```json\n" + json_text(outcome.get("provenance", {})) + "\n```"),
        cell("code", "import sys, json\nfrom pathlib import Path\n"
             "sys.dont_write_bytecode = True\nroot = Path.cwd()\n"
             "sys.path.insert(0, str(root / '_replay'))\n"
             "from investigator.replay import Replay\nreplay = Replay(root)\n"),
    ]
    for event in events:
        if event["tool"] == "run_error":
            cells.append(cell("markdown", "本次运行未完成：" + event["result"]["error"]["message"]))
            continue
        cells.append(cell("markdown", f"## {event['evidence_id']} · {event['tool']}\n\n"
                          + event["public_note"] +
                          ("\n\n原始工具错误保留如下，不能将其视为成功。" if not event["result"]["ok"] else "")))
        # Only trusted template code is executable. All provider values are JSON string data.
        encoded = json.dumps(event, ensure_ascii=False, allow_nan=False)
        cells.append(cell("code", f"event = json.loads({encoded!r})\n"
                          "actual = replay.check(event)\n"
                          "print(json.dumps(actual, ensure_ascii=False, allow_nan=False))\n"))
    return {"nbformat": 4, "nbformat_minor": 5, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
    }, "cells": [dict(c, id=f"cell-{i:03d}") for i, c in enumerate(cells)]}


def report_html(events, outcome):
    esc = html.escape
    incomplete = "调查未完成。"
    if outcome["failure"] and outcome["failure"].get("phase") == "response_validation":
        incomplete = "模型响应无效；调查未完成。"
    if outcome["tool_actions"] == 0:
        incomplete += "尚未执行任何工具动作，没有 SQL 调查结果。"
    answer = outcome["answer"] or {"summary": incomplete, "findings": [],
        "questions": [q["question"] for q in outcome.get("clarifications", []) if q["resolution"] is None]}
    findings = []
    for finding in answer["findings"]:
        refs = " ".join(f'<a href="#{esc(ref)}">[{esc(ref)}]</a>' for ref in finding.get("evidence", []))
        findings.append(f'<li>{esc(finding["text"])} {refs}</li>')
    role_html = ""
    roles = evidence_roles(outcome)
    if roles is not None:
        answer_ref = roles["answer_evidence_id"]
        answer_link = f'<a href="#{esc(answer_ref)}">[{esc(answer_ref)}]</a>' if answer_ref else "未接受答案证据"
        support_links = " ".join(f'<a href="#{esc(ref)}">[{esc(ref)}]</a>' for ref in roles["supporting_evidence_ids"]) or "无"
        role_html = (f'<p><strong>答案证据：</strong>{answer_link}；<strong>支持证据：</strong>{support_links}</p>'
                     '<p>来源、类型、形状校验不代表数值正确或支持内容相关。</p>'
                     '<details><summary>调用方冻结的答案契约</summary><pre>' + esc(json_text(roles)) + '</pre></details>')
    questions = "".join(f"<li>{esc(q)}</li>" for q in answer["questions"])
    conditions = "".join(f"<li>{esc(q)}</li>" for q in answer.get("conditions", []))
    notice = qualification(outcome)
    resolved = []
    for question in outcome.get("clarifications", []):
        resolution = question["resolution"]
        if resolution:
            resolved.append(f'<li>{esc(question["question"])}<br>{esc(resolution["answer"])}<br>'
                            f'来源：{esc(resolution["source_kind"])} · {esc(resolution["source_reference"])} '
                            f'<a href="#{esc(resolution["received_at"])}">[{esc(resolution["received_at"])}]</a></li>')
    trail = []
    charts = []
    for event in events:
        eid = esc(event["evidence_id"])
        ok = event["result"]["ok"]
        status = "OK" if ok else "ERROR · 已保留"
        batch_position = (f'模型第 {event["model_turn"]} 轮 · 批次第 {event["batch_index"] + 1} 项；'
                          f'选择时最后可见证据：{esc(str(event["decision_after_evidence"] or "开始"))}'
                          if "model_turn" in event else "")
        trail.append(
            f'<details id="{eid}" {"open" if not ok else ""}>'
            f'<summary><b>{eid}</b> · {esc(event["tool"])} '
            f'<span class="{"ok" if ok else "error"}">{status}</span></summary>'
            f'<p>{esc(event["public_note"])}</p>'
            f'<p class="muted">{batch_position}</p>'
            f'<p class="muted">上一执行动作：{esc(str(event.get("after_evidence") or "开始"))}</p>'
            f'<h4>实际输入</h4><pre>{esc(json_text(event["input"]))}</pre>'
            f'<h4>实际返回</h4><pre>{esc(json_text(event["result"]))}</pre></details>')
        if event["tool"] == "plot" and ok:
            data = event["result"]["data"]
            columns = data["source_columns"]
            binding = esc(f"successes: {columns['successes']} / total: {columns['total']}")
            source = esc(data["source_evidence_id"])
            origin = "公开真实数据" if outcome.get("synthetic") is False else "合成数据"
            charts.append(f'<figure><img src="chart-{eid}.svg" alt="{origin}查询列比率；业务口径未验证"/>'
                          f'<figcaption>{binding} · 源查询 <a href="#{source}">{source}</a>'
                          f' · 图表 <a href="#{eid}">{eid}</a></figcaption></figure>')
    errors = sum(not e["result"]["ok"] for e in events)
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy"
 content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'">
<title>数据调查 · 本地证据</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f6fb;color:#17304d;font:16px/1.65 system-ui,sans-serif}}
main{{max-width:1080px;margin:auto;padding:30px 32px 70px}}.banner{{background:#fff0c2;border:1px solid #d69c20;
padding:12px 18px;border-radius:8px;font-weight:650}}h1{{font-size:34px;line-height:1.3;margin:24px 0 10px}}
.muted{{color:#586a80;font-size:14px}}.card{{background:white;border:1px solid #dbe3ed;
border-radius:14px;padding:22px;margin:20px 0}}.summary{{font-size:22px;font-weight:650}}
.facts{{display:flex;gap:28px;flex-wrap:wrap}}.facts strong{{display:block;font-size:23px}}
a{{color:#006a91}}li{{margin:10px 0}}details{{background:white;border:1px solid #dbe3ed;border-radius:8px;
margin:10px 0;padding:12px 16px}}summary{{cursor:pointer}}.ok{{color:#007e61;float:right}}
.error{{color:#b03424;float:right}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7fb;
padding:14px;font:13px/1.6 ui-monospace,monospace;max-height:520px;overflow:auto}}
figure{{margin:20px 0}}img{{width:100%;max-height:300px}}figcaption{{font-size:13px}}
@media(max-width:650px){{main{{padding:18px}}h1{{font-size:28px}}.summary{{font-size:19px}}}}
</style><main>
<div class="banner">{esc(data_label(outcome.get("provenance")))} · {esc(outcome["mode"].upper())}<br>
<small>{esc(outcome["disclosure"])}</small></div>
<h1>数据调查 · 可复跑证据</h1>
<p class="muted">{esc(outcome["goal"])}</p>
<section class="card"><div class="facts">
<div><strong>{esc(outcome["status"])}</strong>交付状态</div>
<div><strong>{outcome["tool_actions"]}</strong>实际工具动作</div><div><strong>{errors}</strong>可见错误</div>
<div><strong>{outcome["live_calls"]}</strong>Live 请求尝试</div></div></section>
<section class="card">
{"<div class='banner'>" + esc(notice) + "</div>" if notice else ""}
{"<h3>适用假设（未经确认）</h3><ul>" + conditions + "</ul>" if conditions else ""}
{"<h3>仍需确认的具体问题</h3><ul>" + questions + "</ul>" if questions else ""}
{"<h3>可信调用方提供的澄清</h3><ul>" + "".join(resolved) + "</ul>" if resolved else ""}
<p class="muted">{esc(RATE_NOTICE)}</p>
<h2>模型/脚本提供的解读</h2>
<p class="summary">{esc(answer["summary"])}</p>{role_html}<ul>{"".join(findings)}</ul>
{"".join(charts)}</section>
<section class="card"><h2>可复跑交付物</h2>
<p><a href="investigation.ipynb">Notebook</a> · <a href="trace.jsonl">完整动作记录</a> ·
<a href="report.json">结构化结论</a> · <a href="manifest.json">输入与代码哈希</a> ·
<a href="response_diagnostics.jsonl">响应结构与拒绝原因</a></p>
<p>本目录运行 <code>python replay.py</code>。离线重算全部实际查询与固定统计操作，
逐项比较原结果；不调用 API。Notebook 未预填执行输出。</p></section>
<section class="card"><h2>数据来源与快照</h2><p>冻结的来源、许可及本地审核记录；不代表重新核验来源或隐私保证。</p>
<pre>{esc(json_text(outcome.get("provenance", {})))}</pre></section>
<h2>从目标到交付的实际动作</h2><p class="muted">展开查看输入与返回。
下一动作的公开说明展示操作变化；不收集模型私有推理。引用存在不代表结论语义已被自动证明。</p>
{"".join(trail)}</main></html>"""


def export(output, manifest, events, outcome):
    output = Path(output)
    replay_dir = output / "_replay" / "investigator"
    replay_dir.mkdir(parents=True)
    hashes = {}
    for name in REPLAY_FILES:
        data = Path(__file__).with_name(name).read_bytes()
        (replay_dir / name).write_bytes(data)
        hashes[name] = digest(data)
    write_artifact(output / "replay.py", REPLAY_SCRIPT)
    write_artifact(output / "report.json", json_text(outcome) + "\n")
    write_artifact(output / "investigation.ipynb", json_text(notebook(events, outcome)))
    write_artifact(output / "report.html", report_html(events, outcome))
    for event in events:
        if event["tool"] == "plot" and event["result"]["ok"]:
            write_artifact(output / f"chart-{event['evidence_id']}.svg", event["result"]["data"]["svg"])
    artifact_names = ["trace.jsonl", "report.json", "investigation.ipynb", "report.html", "replay.py",
                      "response_diagnostics.jsonl"]
    artifact_names += [f"chart-{e['evidence_id']}.svg" for e in events
                       if e["tool"] == "plot" and e["result"]["ok"]]
    full = {"format_version": 1, "input": manifest, "runtime": hashes,
            "artifacts": {name: digest(safe_read(output, name, MAX_ARTIFACT_BYTES)) for name in artifact_names},
            "note": "Integrity/replay hashes, not a signed provenance or live spending ledger."}
    if outcome.get("evidence_interface") == "answer_roles_v1":
        contract_file = output / "answer_contract.json"
        write_artifact(contract_file, json_text(outcome["answer_contract"]) + "\n")
        pin = digest(contract_file.read_bytes())
        full["artifacts"][contract_file.name] = pin
        full["answer_contract"] = {"file": contract_file.name, "sha256": pin}
    write_artifact(output / "manifest.json", json_text(full) + "\n", limit=MAX_MANIFEST_BYTES)
