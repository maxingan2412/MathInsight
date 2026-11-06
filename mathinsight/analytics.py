"""个体与班级学情分析。

* 纵向(个体)：同一学生各板块/素养的相对强弱、历次考试的分数与名次走势、错因分布。
* 横向(群体)：同一板块全班的分布与排名，班级整体薄弱板块。
* 归因：对班级薄弱板块，比较「失分在各素养上的占比」与「题目本身的素养权重」，
  比值最大的素养就是主要短板；再结合教师标注的错因与板块内最弱的教材小节给出解释。
"""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from .comments import tag_comment
from .model import UNIT_NAMES
from .taxonomy import COMPETENCIES

ADVICE_COMP = {
    "数学运算": "运算是主要失分点：每天 10 分钟限时运算（含分式、根式、联立消元），做完自查每一步的等价性。",
    "逻辑推理": "推理链条不完整：解答题先写「要证什么 ⇐ 只需什么」的倒推框架，再正向书写；多做必要性/充分性的反例练习。",
    "直观想象": "缺少画图习惯：几何、函数题先画草图并标出关键量，立体几何练习「找射影、作截面」的基本动作。",
    "数学抽象": "条件翻译困难：把题干中的「任意」「存在」「集合关系」逐句翻译成数学式，建立常见表述对照表。",
    "数学建模": "情境题建模慢：先列出「已知量-未知量-关系」三栏，再选模型；多练实际情境下的概率与函数题。",
    "数据分析": "数据读取与统计量理解不足：重做统计图表题，口述每个统计量的含义和适用场景。",
}
ADVICE_UNIT = {
    "解析几何": "联立后先写判别式和韦达定理，再统一代入目标式；练「设而不求」与「点差法」两种模板。",
    "导数": "单调性讨论按「求导—定号—分类」三步走；含参问题先找分类的临界值。",
    "立体几何": "几何法与坐标法都要会；建系后先检查坐标再求法向量。",
    "数列": "通项与求和的方法清单（累加、累乘、错位相减、裂项）逐一过关。",
    "三角": "公式变形熟练度：降幂、辅助角、拆角三类变形各练一组。",
    "概率": "先写清样本空间与事件，再判断互斥、独立，最后选公式。",
    "函数概念与性质": "奇偶性、单调性、周期性的定义要能口述并会用定义证明。",
}


def _rank(values: list[float]) -> list[int]:
    order = sorted(range(len(values)), key=lambda k: -values[k])
    r = [0] * len(values)
    for pos, k in enumerate(order):
        r[k] = pos + 1
    return r


def exam_table(resp, exams: list[dict], bank) -> dict:
    """每次考试：每个学生的总分、名次、各板块得分率。"""
    by = defaultdict(lambda: defaultdict(float))
    unit_got = defaultdict(lambda: defaultdict(float))
    unit_full = defaultdict(lambda: defaultdict(float))
    for s, e, q, sc, fu in zip(resp.student, resp.exam, resp.qid, resp.score, resp.full):
        by[e][s] += sc
        u = bank[q]["units"][0]
        unit_got[(e, s)][u] += sc
        unit_full[(e, s)][u] += fu
    out = {}
    for ex in exams:
        e = ex["id"]
        studs = sorted(by[e])
        totals = [by[e][s] for s in studs]
        ranks = _rank(totals)
        full = sum(it["score"] for it in ex["items"])
        out[e] = {
            "full": full,
            "mean": round(float(np.mean(totals)), 2) if totals else 0,
            "students": {s: {"total": round(t, 1), "rank": r,
                             "unit_rate": {u: round(unit_got[(e, s)][u] / unit_full[(e, s)][u], 3)
                                           for u in unit_full[(e, s)]}}
                         for s, t, r in zip(studs, totals, ranks)},
        }
    return out


def student_profile(fit, s_idx: int, resp, exams, table, bank, comments: list[dict]) -> dict:
    sid = fit.students[s_idx]
    mu = fit.mastery_unit()
    mc = fit.mastery_comp()
    class_mu = mu.mean(0)
    d = fit.delta_unit[s_idx]
    ev = fit.evid_unit[s_idx]
    units = []
    for k, u in enumerate(UNIT_NAMES):
        if ev[k] < 0.5:
            continue
        pct = float((mu[:, k] < mu[s_idx, k]).mean())
        units.append({"unit": u, "mastery": round(float(mu[s_idx, k]), 3), "delta": round(float(d[k]), 3),
                      "class_mean": round(float(class_mu[k]), 3), "percentile": round(pct, 3),
                      "evidence": round(float(ev[k]), 1)})
    ok = [x for x in units if x["evidence"] >= 2]
    strong = [x["unit"] for x in sorted(ok, key=lambda x: -x["delta"])[:3] if x["delta"] > 0.15]
    weak = [x["unit"] for x in sorted(ok, key=lambda x: x["delta"])[:3] if x["delta"] < -0.15]
    comps = [{"competency": c, "mastery": round(float(mc[s_idx, k]), 3),
              "delta": round(float(fit.gamma_comp[s_idx, k]), 3),
              "class_mean": round(float(mc[:, k].mean()), 3)} for k, c in enumerate(COMPETENCIES)]
    weak_comp = min(comps, key=lambda x: x["delta"])["competency"]
    trend = [{"exam": ex["id"], "title": ex.get("title", ex["id"]),
              "total": table[ex["id"]]["students"].get(sid, {}).get("total"),
              "rank": table[ex["id"]]["students"].get(sid, {}).get("rank"),
              "full": table[ex["id"]]["full"], "class_mean": table[ex["id"]]["mean"]}
             for ex in exams]
    errs = Counter(e for s, e in zip(resp.student, resp.error) if s == sid and e)
    my_comments = [c for c in comments if c["student"] == sid]
    tags = []
    for c in my_comments:
        for t in tag_comment(c["text"]):
            if t not in tags:
                tags.append(t)
    advice = []
    for u in weak:
        if u in ADVICE_UNIT:
            advice.append(f"【{u}】{ADVICE_UNIT[u]}")
    advice.append(f"【{weak_comp}】{ADVICE_COMP[weak_comp]}")
    if errs:
        top, n = errs.most_common(1)[0]
        advice.append(f"【错因】近几次考试最常见的错因是「{top}」（{n} 次），订正时按错因分类整理错题。")
    if any(t["tag"] == "综合题畏难" for t in tags):
        advice.append("【心态】压轴题至少写出第(1)问和第(2)问的关键式子，按步骤拿分。")
    return {"id": sid, "theta": round(float(fit.theta[s_idx]), 3), "units": units, "strong": strong,
            "weak": weak, "competencies": comps, "trend": trend, "errors": dict(errs),
            "comments": my_comments, "tags": tags, "advice": advice}


def class_overview(fit, resp, bank, exams, table) -> dict:
    mu = fit.mastery_unit()
    mc = fit.mastery_comp()
    units = []
    for k, u in enumerate(UNIT_NAMES):
        col = mu[:, k]
        ev = fit.evid_unit[:, k].mean()
        if ev < 0.5:
            continue
        units.append({"unit": u, "mean": round(float(col.mean()), 3), "std": round(float(col.std()), 3),
                      "min": round(float(col.min()), 3), "max": round(float(col.max()), 3),
                      "delta_mean": round(float(fit.delta_unit[:, k].mean()), 3), "evidence": round(float(ev), 1),
                      "dist": [round(float(v), 3) for v in col]})
    # 观察得分率(按题目主板块汇总)
    og, of = defaultdict(float), defaultdict(float)
    for q, sc, fu in zip(resp.qid, resp.score, resp.full):
        u = bank[q]["units"][0]
        og[u] += sc
        of[u] += fu
    overall = sum(og.values()) / (sum(of.values()) or 1)
    for x in units:
        x["rate"] = round(og[x["unit"]] / of[x["unit"]], 3) if of[x["unit"]] else None
    # 薄弱板块：相对偏移最低，且实际得分率低于全卷平均(两条都满足，避免把「题简单但偶有失误」误判为弱)
    cand = [x for x in units if x["rate"] is not None and x["rate"] < overall - 0.03 and x["evidence"] >= 1]
    weak_units = [x["unit"] for x in sorted(cand, key=lambda x: x["delta_mean"])[:3]]
    diagnoses = [diagnose_unit(u, resp, bank, fit) for u in weak_units]
    comps = [{"competency": c, "mean": round(float(mc[:, k].mean()), 3), "std": round(float(mc[:, k].std()), 3)}
             for k, c in enumerate(COMPETENCIES)]
    heat = [[round(float(mu[s, k]), 3) for k in range(len(UNIT_NAMES))] for s in range(len(fit.students))]
    return {"units": units, "weak_units": weak_units, "diagnoses": diagnoses, "competencies": comps,
            "heatmap": {"students": fit.students, "units": UNIT_NAMES, "values": heat},
            "exam_means": [{"exam": e["id"], "title": e.get("title", e["id"]), "mean": table[e["id"]]["mean"],
                            "full": table[e["id"]]["full"]} for e in exams]}


ERROR_TO_COMP = {"计算失误": "数学运算", "审题错误": "数学抽象", "思路缺失": "逻辑推理",
                 "表述不完整": "逻辑推理", "知识遗忘": ""}


def diagnose_unit(unit: str, resp, bank, fit) -> dict:
    """班级薄弱板块归因。

    两路证据交叉印证：
    ① 模型证据：全班在各素养上的平均偏移 γ̄_c(<0 为短板)，按该板块题目的素养权重 w_c 加权，
       得到每个素养对本板块失分的「贡献」 w_c·max(0, −γ̄_c)；
    ② 教师证据：本板块错题上标注的错因分布，按错因→素养映射汇总。
    两者归一化后各占一半，得分最高的素养即主要成因。
    """
    got = full = all_got = all_full = 0.0
    errs = Counter()
    w = defaultdict(float)
    sec_got = defaultdict(float)
    sec_full = defaultdict(float)
    for q, sc, fu, er in zip(resp.qid, resp.score, resp.full, resp.error):
        all_got += sc
        all_full += fu
        qq = bank[q]
        if qq["units"][0] != unit:
            continue
        got += sc
        full += fu
        for c, v in qq["competencies"].items():
            w[c] += fu * v
        if er:
            errs[er] += 1
        if qq["sections"]:
            s0 = qq["sections"][0]
            key = f'{s0["book"]} {s0["sec"]} {s0.get("name", "")}'
            sec_got[key] += sc
            sec_full[key] += fu
    tw = sum(w.values()) or 1
    w = {c: v / tw for c, v in w.items()}
    gbar = {c: float(fit.gamma_comp[:, k].mean()) for k, c in enumerate(COMPETENCIES)}
    model_ev = {c: w.get(c, 0) * max(0.0, -gbar[c]) for c in COMPETENCIES}
    me = sum(model_ev.values())
    err_ev = defaultdict(float)
    for e, n in errs.items():
        if ERROR_TO_COMP.get(e):
            err_ev[ERROR_TO_COMP[e]] += n
    ee = sum(err_ev.values())
    km = .5 if me >= 0.02 else 0.0           # 模型证据太弱时只看教师标注
    ke = (1 - km) if ee else 0.0
    if not ee:
        km = 1.0
    score = {c: (model_ev[c] / me if me else 0) * km + (err_ev[c] / ee if ee else 0) * ke for c in COMPETENCIES}
    main_c = max(score, key=score.get) if any(score.values()) else ""
    sec_rate = sorted(((k, sec_got[k] / sec_full[k]) for k in sec_full if sec_full[k] > 0), key=lambda x: x[1])
    rate = got / full if full else 0
    overall = all_got / all_full if all_full else 0
    err_total = sum(errs.values()) or 1
    top_err = errs.most_common(1)[0] if errs else None
    rank_c = sorted(COMPETENCIES, key=lambda c: gbar[c])
    parts = [f"「{unit}」板块全班得分率 {rate:.0%}（全卷平均 {overall:.0%}）。"]
    if main_c:
        parts.append(f"主要成因判断为「{main_c}」：全班该素养相对水平偏移 {gbar[main_c]:+.2f}"
                     f"（六项素养中排第 {rank_c.index(main_c) + 1} 低），本板块题目的{main_c}权重占 {w.get(main_c, 0):.0%}")
        if me < 0.02:
            parts[-1] = f"主要成因判断为「{main_c}」：依据是教师标注的错因分布（模型层面的素养差异不明显）"
        if top_err and ERROR_TO_COMP.get(top_err[0]) == main_c and me >= 0.02:
            parts.append(f"；教师标注的错因中「{top_err[0]}」占 {top_err[1] / err_total:.0%}，两路证据一致。")
        elif top_err and ERROR_TO_COMP.get(top_err[0]) == main_c:
            parts.append(f"；教师标注的错因中「{top_err[0]}」占 {top_err[1] / err_total:.0%}。")
        elif top_err:
            parts.append(f"；教师标注的错因以「{top_err[0]}」为主（{top_err[1] / err_total:.0%}）。")
        else:
            parts.append("。")
    if sec_rate:
        parts.append(f"板块内最弱的是 {sec_rate[0][0]}（得分率 {sec_rate[0][1]:.0%}）。")
    return {"unit": unit, "rate": round(rate, 3), "overall": round(overall, 3), "main_competency": main_c,
            "evidence": {c: round(score[c], 3) for c in COMPETENCIES},
            "class_gamma": {c: round(gbar[c], 3) for c in COMPETENCIES},
            "weight_share": {c: round(v, 3) for c, v in w.items()},
            "errors": dict(errs), "weakest_sections": [{"section": k, "rate": round(v, 3)} for k, v in sec_rate[:3]],
            "text": "".join(parts),
            "suggestion": ADVICE_COMP.get(main_c, "") + (" " + ADVICE_UNIT[unit] if unit in ADVICE_UNIT else "")}
