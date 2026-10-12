"""交付物一致性核验：论文表格 / 结果工作簿 / 结果数组三者互相对账。

只读取 结果/、tables/、results/ 中的既有文件，不做任何计算或写回，
因此可以独立于建模程序反复运行。运行方式（在工程根目录）：

    python code/verify_consistency.py

核验项：
1. 每份多日工作簿中，144 个时段列之和等于"全天购电量"列；
2. 问题3、问题4-3的"计划购电量"与"调整购电量"两张表的"全天购电费"逐日相同；
3. 工作簿汇总（天数、购电量、费用、紧急电量）等于 results/summary.json；
4. results/daily_summary.csv 的每个方案汇总等于 results/summary.json；
5. 论文指定时段表 tables/*_purchase.tex 的时段值与全天值等于工作簿对应单元；
6. 问题1工作簿的时段值、全天购电量等于 tables/q1_purchase.tex 与 summary.json；
7. 摘要与正文出现的关键数值，逐条等于其数据源（工作簿、summary.json、
   review_diagnostics.json、refinement_metrics.json）算出的值。
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
TOL = 5e-3          # 表格按两位小数排版，取半个末位的容差
SLOTS = ["10:00--10:10", "12:00--12:10", "14:00--14:10",
         "16:00--16:10", "18:00--18:10", "20:00--20:10"]

# 工作簿 -> (逐时工作表, 典型日表格前缀)
CASES = {
    "q2":     ("result2.xlsx",   "计划购电量", "q2"),
    "q3":     ("result3.xlsx",   "调整购电量", "q3"),
    "q4_2":   ("result4-2.xlsx", "计划购电量", "q4_2"),
    "q4_3":   ("result4-3.xlsx", "调整购电量", "q4_3"),
}
TYPICAL_DAYS = ["0320", "0621", "0923", "1221"]
failures: list[str] = []
checks = 0


def check(ok: bool, message: str) -> None:
    global checks
    checks += 1
    if not ok:
        failures.append(message)


def col_of(label: str) -> int:
    """'0:00--0:10' 对应第 2 列。"""
    hour, minute = label.split("--")[0].split(":")
    return 2 + int(hour) * 6 + int(minute) // 10


def parse_purchase_table(path: Path) -> tuple[dict[str, float], float, float]:
    text = path.read_text(encoding="utf-8")
    slots = {f"{a}--{b}": float(v)
             for a, b, v in re.findall(r"(\d\d:\d\d)--(\d\d:\d\d) & ([\d.]+)", text)}
    day = float(re.search(r"全天常规购电量：([\d.]+)", text).group(1))
    cost = float(re.search(r"全天总费用：([\d.]+)", text).group(1))
    return slots, day, cost


def row_of(ws, date: datetime) -> int:
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, 1).value == date:
            return r
    raise AssertionError(f"{ws.title} 缺少日期 {date:%Y-%m-%d}")


def main() -> int:
    summary = json.loads((ROOT / "results/summary.json").read_text(encoding="utf-8"))
    cases = summary["cases"]

    # ---- 1、2、3、5：工作簿内部与工作簿同结果数组 ----
    for name, (book, sheet, prefix) in CASES.items():
        wb = openpyxl.load_workbook(ROOT / "结果" / book, data_only=True)
        ws = wb[sheet]
        energy = cost = emergency = 0.0
        days = 0
        worst_row = 0.0
        for r in range(2, ws.max_row + 1):
            if ws.cell(r, 1).value is None:
                continue
            days += 1
            row_sum = sum((ws.cell(r, c).value or 0.0) for c in range(2, 146))
            worst_row = max(worst_row, abs(row_sum - (ws.cell(r, 146).value or 0.0)))
            energy += ws.cell(r, 146).value or 0.0
            cost += ws.cell(r, 147).value or 0.0
        check(worst_row < 1e-6, f"{book}/{sheet}: 逐时和与全天购电量最大差 {worst_row:.2e}")
        check(days == 334, f"{book}/{sheet}: 报告日数 {days} ≠ 334")

        if "调整购电量" in wb.sheetnames:
            plan, adj = wb["计划购电量"], wb["调整购电量"]
            worst = max(abs((plan.cell(r, 147).value or 0.0) - (adj.cell(r, 147).value or 0.0))
                        for r in range(2, plan.max_row + 1) if plan.cell(r, 1).value is not None)
            check(worst < 1e-6, f"{book}: 两表全天购电费最大差 {worst:.2e}（不应相加）")

        ws_em = wb["紧急购电量"]
        for r in range(2, ws_em.max_row + 1):
            v = ws_em.cell(r, 3).value
            if isinstance(v, (int, float)):
                emergency += v
        exp = cases[name]
        check(abs(cost - exp["total_cost"]) <= TOL,
              f"{book}: 费用合计 {cost:.2f} ≠ summary.json {exp['total_cost']:.2f}")
        check(abs(energy - exp["grid_kwh"]) <= TOL,
              f"{book}: 购电量合计 {energy:.2f} ≠ summary.json {exp['grid_kwh']:.2f}")
        check(abs(emergency - exp["emergency_kwh"]) <= TOL,
              f"{book}: 紧急电量合计 {emergency:.2f} ≠ summary.json {exp['emergency_kwh']:.2f}")

        for d in TYPICAL_DAYS:
            date = datetime(2025, int(d[:2]), int(d[2:]))
            r = row_of(ws, date)
            slots, tab_day, tab_cost = parse_purchase_table(
                ROOT / "tables" / f"{prefix}_{d}_purchase.tex")
            for label in SLOTS:
                got = ws.cell(r, col_of(label)).value or 0.0
                check(abs(got - slots[label]) <= TOL,
                      f"{book}/{sheet} {date:%Y-%m-%d} {label}: 表 {slots[label]:.2f} 簿 {got:.2f}")
            check(abs((ws.cell(r, 146).value or 0.0) - tab_day) <= TOL,
                  f"{book}/{sheet} {date:%Y-%m-%d}: 全天购电量 表 {tab_day:.2f} 簿 {ws.cell(r,146).value:.2f}")
            check(abs((ws.cell(r, 147).value or 0.0) - tab_cost) <= TOL,
                  f"{book}/{sheet} {date:%Y-%m-%d}: 全天总费用 表 {tab_cost:.2f} 簿 {ws.cell(r,147).value:.2f}")

    # ---- 4：daily_summary.csv 同 summary.json ----
    totals = {k: 0.0 for k in cases}
    em = {k: 0.0 for k in cases}
    rows = list(csv.DictReader((ROOT / "results/daily_summary.csv").open(encoding="utf-8-sig")))
    csv_cases = {row["case"] for row in rows}
    for row in rows:
        if row["case"] in totals:
            totals[row["case"]] += float(row["total_cost"])
            em[row["case"]] += float(row["emergency_kwh"])
    for name in sorted(csv_cases & set(cases)):
        check(abs(totals[name] - cases[name]["total_cost"]) <= TOL,
              f"daily_summary.csv {name}: 费用 {totals[name]:.2f} ≠ {cases[name]['total_cost']:.2f}")
        check(abs(em[name] - cases[name]["emergency_kwh"]) <= TOL,
              f"daily_summary.csv {name}: 紧急电量 {em[name]:.2f} ≠ {cases[name]['emergency_kwh']:.2f}")

    # ---- 6：问题1 ----
    wb1 = openpyxl.load_workbook(ROOT / "结果/result1.xlsx", data_only=True)
    ws1 = wb1["计划购电量"]
    values = {ws1.cell(r, 1).value: (ws1.cell(r, 2).value or 0.0) for r in range(2, 146)}
    slots, tab_day, tab_cost = parse_purchase_table(ROOT / "tables/q1_purchase.tex")
    day = sum(values.values())
    check(abs(day - tab_day) <= TOL, f"result1: 全天购电量 {day:.2f} ≠ 表 {tab_day:.2f}")
    check(abs(day - summary["q1"]["grid_kwh"]) <= TOL,
          f"result1: 全天购电量 {day:.2f} ≠ summary.json {summary['q1']['grid_kwh']:.2f}")
    check(abs(tab_cost - summary["q1"]["objective"]) <= TOL,
          f"问题1表: 全天费用 {tab_cost:.2f} ≠ summary.json {summary['q1']['objective']:.2f}")
    for label in SLOTS:
        a, b = label.split("--")
        got = values[f"{a}-{b}"]
        check(abs(got - slots[label]) <= TOL, f"result1 {label}: 表 {slots[label]:.2f} 簿 {got:.2f}")
    ws2 = wb1["充放电量"]
    ch = sum((ws2.cell(r, 2).value or 0.0) for r in range(2, 8))
    dis = sum((ws2.cell(r, 3).value or 0.0) for r in range(2, 8))
    check(abs(ch - summary["q1"]["ch_kwh"]) <= TOL, f"result1: 充电合计 {ch:.2f} ≠ {summary['q1']['ch_kwh']:.2f}")
    check(abs(dis - summary["q1"]["dis_kwh"]) <= TOL, f"result1: 放电合计 {dis:.2f} ≠ {summary['q1']['dis_kwh']:.2f}")

    # ---- 7：摘要与正文文字数值同数据源对账 ----
    # 摘要与正文的关键数字均以字面值排版，此处按数据源重算后逐条比对，
    # 防止正文数字与工作簿、结果数组之间发生漂移。
    diag = json.loads((ROOT / "results/review_diagnostics.json").read_text(encoding="utf-8"))
    refi = json.loads((ROOT / "results/refinement_metrics.json").read_text(encoding="utf-8"))
    dgn = json.loads((ROOT / "results/diagnostics.json").read_text(encoding="utf-8"))
    tex = (ROOT / "main.tex").read_text(encoding="utf-8")
    body = tex.split("\\section*{附录A", 1)[0]
    abstract = tex.split("\\end{center}", 1)[1].split("\\newpage", 1)[0]
    risk = {r["rho"]: r for r in diag["risk_scan"]}
    q1v = summary["q1"]
    q2c, q3c = cases["q2"], cases["q3"]
    q3d, q2n = cases["q3_daily"], cases["q2_nominal"]
    q42, q43 = cases["q4_2"], cases["q4_3"]
    q42k, q43k = cases["q4_2_known"], cases["q4_3_known"]

    def wan(x: float) -> str:
        return f"{x / 1e4:.2f}"

    saving3 = q3d["total_cost"] - q3c["total_cost"]
    claims = [
        ("摘要-问题1全天购电量", f"{q1v['grid_kwh']:.2f} kWh", "summary.json:q1.grid_kwh"),
        ("摘要-问题1电费", f"{q1v['objective']:.2f}元", "summary.json:q1.objective"),
        ("摘要-问题1无储能对照", f"{q1v['net_cost']:.2f}元", "summary.json:q1.net_cost"),
        ("摘要-问题1降幅", f"{(q1v['net_cost'] - q1v['objective']) / q1v['net_cost'] * 100:.2f}\\%", "q1: (net-objective)/net"),
        ("正文-问题1节省额", f"{q1v['net_cost'] - q1v['objective']:.2f}元", "q1: net-objective"),
        ("摘要-问题2总费用", f"{wan(q2c['total_cost'])}万元", "cases.q2.total_cost"),
        ("摘要-问题2紧急电量", f"{q2c['emergency_kwh'] / 1e4:.2f}万kWh", "cases.q2.emergency_kwh"),
        ("摘要-问题2相对点预测", f"{(q2n['total_cost'] - q2c['total_cost']) / q2n['total_cost'] * 100:.2f}\\%", "cases.q2_nominal"),
        ("摘要-问题2未利用供给", f"{diag['q2_energy']['spill_kwh'] / 1e4:.2f}万kWh", "review_diagnostics:q2_energy.spill_kwh"),
        ("摘要-权重8紧急电量", f"{risk[8]['emergency_kwh'] / 1e4:.2f}万kWh", "review_diagnostics:risk_scan[rho=8]"),
        ("摘要-权重8费用增量", f"{(risk[8]['cost'] - q2c['total_cost']) / 1e4:.2f}万元", "risk_scan[rho=8] - cases.q2"),
        ("正文-权重2总费用", f"{risk[2]['cost'] / 1e4:.2f}万元", "review_diagnostics:risk_scan[rho=2]"),
        ("摘要-问题3零时基准", f"{wan(q3d['total_cost'])}万元", "cases.q3_daily.total_cost"),
        ("摘要-问题3更新后", f"{wan(q3c['total_cost'])}万元", "cases.q3.total_cost"),
        ("摘要-问题3节省额", f"{saving3 / 1e4:.2f}万元", "cases.q3_daily - cases.q3"),
        ("摘要-问题3节省率", f"{saving3 / q3d['total_cost'] * 100:.2f}\\%", "saving3 / q3_daily"),
        ("摘要-问题3基准紧急电量", f"{q3d['emergency_kwh'] / 1e4:.2f}万", "cases.q3_daily.emergency_kwh"),
        ("摘要-问题3紧急电量", f"{q3c['emergency_kwh'] / 1e4:.2f}万kWh", "cases.q3.emergency_kwh"),
        ("摘要-问题4日前", f"{wan(q42['total_cost'])}万元", "cases.q4_2.total_cost"),
        ("摘要-问题4滚动", f"{wan(q43['total_cost'])}万元", "cases.q4_3.total_cost"),
        ("摘要-问题4价格已知日前", f"{wan(q42k['total_cost'])}万元", "cases.q4_2_known.total_cost"),
        ("摘要-问题4价格已知滚动", f"{wan(q43k['total_cost'])}万元", "cases.q4_3_known.total_cost"),
        ("摘要-问题4日前信息价值", f"{(q42['total_cost'] - q42k['total_cost']) / q42['total_cost'] * 100:.2f}\\%", "q4_2 vs q4_2_known"),
        ("摘要-问题4滚动信息价值", f"{(q43['total_cost'] - q43k['total_cost']) / q43['total_cost'] * 100:.2f}\\%", "q4_3 vs q4_3_known"),
        ("正文-问题4日前差额", f"{wan(q42['total_cost'] - q42k['total_cost'])}万元", "q4_2 - q4_2_known"),
        ("正文-问题4滚动差额", f"{wan(q43['total_cost'] - q43k['total_cost'])}万元", "q4_3 - q4_3_known"),
        ("摘要-问题4等效循环", re.compile("由约?{:d}、{:d}次升[至到]约?{:d}、{:d}次".format(
            round(q42["equivalent_cycles"]), round(q43["equivalent_cycles"]),
            round(q42k["equivalent_cycles"]), round(q43k["equivalent_cycles"]))),
         "cases[*].equivalent_cycles"),
        ("正文-费用选型对照", f"{refi['q2economic_increase']:.0f}元", "refinement_metrics:q2economic_increase"),
        ("正文-费用选型对照(价格)", f"{refi['q4_2economic_increase']:.0f}元", "refinement_metrics:q4_2economic_increase"),
        ("正文-更新后逐日盈亏", f"{dgn['update_days']['more_expensive']}天更新后更贵，"
                              f"{dgn['update_days']['cheaper']}天更便宜", "diagnostics.json:update_days"),
        ("正文-更新试验月份数", f"{len(dgn['update_cost_by_month'])}个月", "review_diagnostics:update_cost_by_month"),
    ]
    for label, literal, source in claims:
        where = "摘要" if label.startswith("摘要") else "正文"
        target = abstract if where == "摘要" else body
        found = bool(literal.search(target)) if isinstance(literal, re.Pattern) else literal in target
        check(found, f"{label}: {where}未见 {literal!r}（数据源 {source}）")

    only_summary = sorted(set(cases) - csv_cases)
    print(f"核验项：{checks}    失败：{len(failures)}")
    if only_summary:
        print(f"说明：{len(only_summary)} 个敏感性/对照方案只存于 summary.json，未逐日写入 daily_summary.csv：{only_summary}")
    for f in failures:
        print("  [不一致]", f)
    if not failures:
        print("全部一致：摘要与正文数值、论文指定表、结果工作簿、results/*.json 与 daily_summary.csv 互相对账通过。")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
