"""试卷分析与梯度组卷。

* analyze()：一张卷子考了哪些板块/素养、分值怎样分布、难度曲线、哪些板块没考到，
  并与题库中历年高考的平均分布对照。
* compare()：多次考试(月考、一模……四模)的板块覆盖矩阵与累计覆盖，找出一直没考的内容。
* build()：按阶段(基础 → 提高 → 拔高 → 冲刺)自动组卷——难度曲线逐轮上移，
  冲刺卷整体难度高于高考均值；避开已考过的题，板块分值向高考分布靠拢。
"""
from __future__ import annotations

import random
from collections import defaultdict

from .taxonomy import COMPETENCIES, THEMES, UNITS

TEMPLATES = {
    "上海卷": [("填空", 4)] * 6 + [("填空", 5)] * 6 + [("单选", 4)] * 2 + [("单选", 5)] * 2
              + [("解答", 14)] * 3 + [("解答", 18)] * 2,
    "新高考卷": [("单选", 5)] * 8 + [("多选", 6)] * 3 + [("填空", 5)] * 3
               + [("解答", 13), ("解答", 15), ("解答", 15), ("解答", 17), ("解答", 17)],
}

# 阶段: (说明, 难度曲线整体平移量)
STAGES = {
    "基础": ("一模：回归教材，考查基础知识与通性通法", -0.16),
    "提高": ("二模：综合运用，提高中档题比例", -0.04),
    "拔高": ("三模：压轴题前移，强化思维深度", 0.07),
    "冲刺": ("四模：整体难度略高于高考，练应变与时间分配", 0.15),
}

TYPE_FALLBACK = {"多选": ["多选", "单选"], "单选": ["单选", "多选"], "填空": ["填空"], "解答": ["解答"]}


def unit_share(items: list[tuple[dict, float]]) -> dict[str, float]:
    tot = sum(s for _, s in items) or 1
    out = defaultdict(float)
    for q, s in items:
        w = {u: (1.0 if i == 0 else 0.5) for i, u in enumerate(q["units"])}
        t = sum(w.values())
        for u, v in w.items():
            out[u] += s * v / t
    return {u: round(out[u] / tot, 4) for u in UNITS if out[u] > 0}


def gaokao_reference(bank) -> dict[str, float]:
    """题库中全部高考卷的平均板块分值占比。"""
    papers = defaultdict(list)
    for q in bank.questions:
        if q["kind"] == "高考" and not q.get("optional"):
            papers[q["paper"]].append((q, q["score"]))
    acc = defaultdict(float)
    for items in papers.values():
        for u, v in unit_share(items).items():
            acc[u] += v / len(papers)
    return {u: round(acc[u], 4) for u in UNITS}


def analyze(bank, exam: dict, fit=None, class_idx=None) -> dict:
    """exam = {"id", "title", "items": [{"qid", "score"}]}"""
    items = [(bank[it["qid"]], it["score"]) for it in exam["items"]]
    total = sum(s for _, s in items)
    us = unit_share(items)
    ref = gaokao_reference(bank)
    theme = defaultdict(float)
    comp = defaultdict(float)
    for q, s in items:
        theme[q["theme"]] += s / total
        for c, w in q["competencies"].items():
            comp[c] += s * w / total
    curve = [{"no": k + 1, "qid": q["id"], "type": q["type"], "score": s,
              "difficulty": q.get("difficulty", 0.5)} for k, (q, s) in enumerate(items)]
    sections = sorted({f'{x["book"]} {x["sec"]} {x.get("name", "")}'.strip() for q, _ in items for x in q["sections"]})
    gaps = [u for u in UNITS if ref.get(u, 0) >= 0.03 and us.get(u, 0) == 0]
    over = [u for u in UNITS if us.get(u, 0) - ref.get(u, 0) >= 0.06]
    under = [u for u in UNITS if ref.get(u, 0) - us.get(u, 0) >= 0.05 and u not in gaps]
    mean_diff = sum(q.get("difficulty", .5) * s for q, s in items) / total
    return {
        "id": exam["id"], "title": exam.get("title", exam["id"]), "total": total,
        "unit_share": us, "gaokao_ref": ref, "theme_share": {t: round(theme[t], 4) for t in THEMES},
        "competency_share": {c: round(comp[c], 4) for c in COMPETENCIES},
        "curve": curve, "sections_covered": sections, "mean_difficulty": round(mean_diff, 3),
        "gaps": gaps, "over": over, "under": under,
    }


def compare(bank, exams: list[dict]) -> dict:
    mat = {u: [] for u in UNITS}
    seen = set()
    cumulative = []
    for ex in exams:
        items = [(bank[it["qid"]], it["score"]) for it in ex["items"]]
        us = unit_share(items)
        for u in UNITS:
            mat[u].append(us.get(u, 0))
        seen |= {u for u, v in us.items() if v > 0}
        cumulative.append(len(seen))
    never = [u for u in UNITS if not any(mat[u])]
    return {"exams": [e["id"] for e in exams], "matrix": mat, "cumulative_units": cumulative,
            "never_tested": never}


def build(bank, *, template: str = "上海卷", stage: str = "基础", exclude: set | None = None,
          regions: list[str] | None = None, seed: int = 0, exam_id: str = "", title: str = "") -> dict:
    """按阶段自动组卷。返回 exam dict。"""
    rng = random.Random(seed)
    exclude = set(exclude or ())
    slots = TEMPLATES[template]
    shift = STAGES[stage][1]
    ref = gaokao_reference(bank)
    total = sum(s for _, s in slots)
    got = defaultdict(float)
    chosen: list[tuple[dict, float]] = []
    n = len(slots)
    for k, (t, score) in enumerate(slots):
        target = min(max(0.15 + 0.72 * k / (n - 1) + shift, 0.05), 0.97)
        cands = []
        for tt in TYPE_FALLBACK[t]:
            cands = [q for q in bank.filter(types=[tt], regions=regions, exclude=exclude, verified_only=True)
                     if q["id"] not in {c["id"] for c, _ in chosen} and not q.get("optional")]
            if cands:
                break
        best, best_cost = None, 1e9
        for q in cands:
            u = q["units"][0]
            over = max(0.0, (got[u] + score) / total - ref.get(u, 0) - 0.04)
            cost = abs(q.get("difficulty", .5) - target) * 3 + over * 8 + rng.random() * 0.15
            if cost < best_cost:
                best, best_cost = q, cost
        if best is None:
            continue
        chosen.append((best, score))
        got[best["units"][0]] += score
    return {"id": exam_id or f"{stage}-{seed}", "title": title or f"{stage}卷", "stage": stage,
            "stage_note": STAGES[stage][0], "template": template,
            "items": [{"qid": q["id"], "score": s} for q, s in chosen]}
