"""个性化练习推荐。

设计原则
--------
1. 只练薄弱板块：取掌握度偏移 δ 最低、且证据充分的 2~3 个板块。
2. 难度落在「最近发展区」：预测得分率 0.60~0.85 的题收益最大——太容易是重复，
   太难会挫败。每组另配 1 道 0.40~0.55 的挑战题。
3. 不重复、广覆盖：同一教材小节最多 2 题，已做过的题不推。
4. 提示阶梯，不直接给答案：每题附三级提示——方向(题眼标签) → 卡点 → 打通，
   学生卡住时逐级展开，最后才看完整详解。
5. 变式扩充：题库原题不够时，用 variants.py 以题眼为「核心想法」生成同构变式。
"""
from __future__ import annotations

from collections import Counter

from .model import UNIT_NAMES

ZPD = (0.60, 0.85)
CHALLENGE = (0.40, 0.55)


def hint_ladder(q: dict) -> list[str]:
    hints = []
    if q.get("tiyan_tag"):
        hints.append(f"方向：这道题的关键在「{q['tiyan_tag']}」。")
    for t in q.get("tiyan", []):
        if "打通" in t:
            stuck, _, through = t.partition("打通")
            hints.append(stuck.strip().rstrip("。；;") + "。")
            hints.append("打通" + through.strip())
        else:
            hints.append(t)
    if not hints:
        hints.append("先回到题目条件，逐条写出它们各自能推出什么。")
    return hints[:4]


def recommend(fit, s_idx: int, bank, *, done: set[str], n_units: int = 3, per_unit: int = 4,
              min_evidence: float = 2.0) -> dict:
    delta = fit.delta_unit[s_idx]
    ev = fit.evid_unit[s_idx]
    order = sorted(range(len(UNIT_NAMES)), key=lambda u: delta[u])
    weak = [u for u in order if ev[u] >= min_evidence][:n_units]
    groups = []
    for u in weak:
        unit = UNIT_NAMES[u]
        cands = [q for q in bank.filter(units=[unit], exclude=done, verified_only=True) if q["units"][0] == unit]
        scored = [(fit.predict(s_idx, q), q) for q in cands]
        mid = sum(ZPD) / 2
        zpd = sorted([x for x in scored if ZPD[0] <= x[0] <= ZPD[1]], key=lambda x: abs(x[0] - mid))
        if len(zpd) < per_unit:   # 题不够时放宽到最接近的
            zpd = sorted(scored, key=lambda x: abs(x[0] - mid))
        picked, sec_cnt = [], Counter()
        for p, q in zpd:
            key = q["sections"][0]["sec"] if q["sections"] else ""
            if sec_cnt[key] >= 2:
                continue
            picked.append((p, q, "巩固"))
            sec_cnt[key] += 1
            if len(picked) >= per_unit:
                break
        ch = [x for x in scored if CHALLENGE[0] <= x[0] <= CHALLENGE[1] and x[1] not in [y[1] for y in picked]]
        if ch:
            p, q = max(ch, key=lambda x: x[0])
            picked.append((p, q, "挑战"))
        groups.append({
            "unit": unit,
            "mastery": round(float(fit.mastery_unit()[s_idx, u]), 3),
            "items": [{"qid": q["id"], "pred": round(p, 3), "role": role, "hints": hint_ladder(q)}
                      for p, q, role in picked],
        })
    return {"weak_units": [UNIT_NAMES[u] for u in weak], "groups": groups}
