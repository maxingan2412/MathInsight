"""个性化练习推荐。

设计原则
--------
1. 只练薄弱板块：板块与学生档案里的「弱项」是同一份名单（证据充分、掌握度偏移 δ < -0.15 的
   最低 3 个，见 analytics.student_profile），由调用方传入。
2. 难度落在「最近发展区」：预测得分率 0.60~0.85 的题收益最大——太容易是重复，
   太难会挫败。区间内的题不够时，放宽到离区间中点最近的题，并在该题上标 relaxed，
   页面如实显示「区间内题不足，放宽」。每组另配 1 道 0.40~0.55 的挑战题。
3. 不重复、广覆盖：同一教材小节最多 2 题，已做过的题不推。
4. 提示阶梯，不直接给答案：方向 → 卡点 → 打通，学生卡住时逐级展开，最后才看完整详解。
   材料来自题眼（标签与「卡点…打通…」记录）和逐题提炼（考点与思想方法、卡点或易错、关键转化、本质）；
   没有这些材料的题只给一条通用提示，不凑级数，也不进推题候选。
5. 变式扩充：题库原题不够时，用 variants.py 以题眼为「核心想法」生成同构变式。
"""
from __future__ import annotations

import html
import re
from collections import Counter

from .model import UNIT_NAMES

ZPD = (0.60, 0.85)
CHALLENGE = (0.40, 0.55)
GENERIC_HINT = "先回到题目条件，逐条写出它们各自能推出什么。"


def _blank(t) -> bool:
    """空、或只写了「无」「—」(可带标签和标点) 的材料不算。"""
    core = re.sub(r"<[^>]+>|[\s。．.，,；;：:]", "", str(t or ""))
    return core in ("", "无", "—", "-")


def _part_label(part: str) -> str:
    part = (part or "").strip()
    return "" if part in ("", "全题") else part + " "


def hint_ladder(q: dict) -> list[str]:
    """返回 HTML 片段列表，依次为 方向 / 卡点 / 打通；缺哪级材料就少哪级。"""
    rf = q.get("refine") or {}
    parts = rf.get("parts") or []
    stuck, through = [], []
    for t in q.get("tiyan") or []:          # 题眼：「(2) 卡点：…。打通：…」(已是 HTML 片段)
        if "打通" in t:
            a, _, b = t.partition("打通")
            m = re.match(r"\s*(\([^)]*\)(?:\([^)]*\))?\s*)", a)
            stuck.append(a.strip().rstrip("。；;，,") + "。")
            through.append((m.group(1) if m else "") + "打通" + b.strip())
        else:
            stuck.append(t)
    hints = []
    # 1 方向
    if q.get("tiyan_tag"):
        hints.append(f"方向：这道题的关键在「{html.escape(q['tiyan_tag'], quote=False)}」。")
    else:
        dirs = []
        for p in parts:
            name = html.escape((p.get("main") or {}).get("name", ""), quote=False)
            if not name:
                continue
            meth = p.get("method", "")
            dirs.append(html.escape(_part_label(p.get("part", "")), quote=False) + "想想「" + name + "」" +
                        ("，思路是" + html.escape(meth, quote=False) if not _blank(meth) else ""))
        if dirs:
            hints.append("方向：" + "；".join(dirs) + "。")
    # 2 卡点
    if stuck:
        hints.append("<br>".join(stuck))
    elif not _blank(rf.get("crux")):
        hints.append(rf["crux"])
    elif not _blank(rf.get("pitfalls")):     # 基础题提炼里常写「卡点：无」, 这时用易错点当这一级
        hints.append("容易卡在这里：" + rf["pitfalls"])
    # 3 打通
    if through:
        hints.append("<br>".join(through))
    else:
        # 提炼的 parts 字段是纯文本(网页上转义后显示), 拼进 HTML 提示前同样转义
        tr = [html.escape(_part_label(p.get("part", "")) + p["transform"], quote=False)
              for p in parts if not _blank(p.get("transform"))]
        if tr:
            hints.append("打通（关键转化）：" + "；".join(tr) + "。")
        elif not _blank(rf.get("essence")):
            hints.append("打通：" + rf["essence"])
    if q.get("type") == "填空":           # 提示里不带最终答案: 含答案的那一级换成不露结果的说法
        hints = [("打通：把上一步的转化做到底，写结果前核对端点和符号。" if answer_leaks(q, h) else h) for h in hints]
    return hints or [GENERIC_HINT]


def _norm_math(t: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", "", str(t or "")))
    return re.sub(r"\\s+|\\$|\\\\left|\\\\right", "", t).replace("\\dfrac", "\\frac")


def answer_leaks(q: dict, hint: str) -> bool:
    """填空题: 答案的某一空(规范化后不少于 3 个字符)原样出现在提示里, 且前面不是负号。"""
    h = _norm_math(hint)
    for part in re.split(r"[；;]", _norm_math(q.get("answer_html"))):
        if len(part) >= 3 and re.search(r"(?<![-\d.])" + re.escape(part), h):
            return True
    return False


def recommend(fit, s_idx: int, bank, *, done: set[str], units: list[str], per_unit: int = 4) -> dict:
    """units: 该生的弱项板块(与学生档案的 weak 同一份名单)。"""
    groups = []
    for unit in units:
        u = UNIT_NAMES.index(unit)
        # 主板块是该板块的题; 没有提示材料(题眼、提炼)的题照常推, 只带一条通用提示
        cands = [q for q in bank.filter(units=[unit], exclude=done, verified_only=True)
                 if q["units"][0] == unit]
        scored = [(fit.predict(s_idx, q), q) for q in cands]
        mid = sum(ZPD) / 2
        zpd = sorted([x for x in scored if ZPD[0] <= x[0] <= ZPD[1]], key=lambda x: abs(x[0] - mid))
        if len(zpd) < per_unit:   # 题不够时放宽到最接近的(区间外的题标 relaxed)
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
        items = []
        for p, q, role in picked:
            it = {"qid": q["id"], "pred": round(p, 3), "role": role, "hints": hint_ladder(q)}
            if role == "巩固" and not (ZPD[0] <= round(p, 3) <= ZPD[1]):
                it["relaxed"] = True
            items.append(it)
        groups.append({"unit": unit, "mastery": round(float(fit.mastery_unit()[s_idx, u]), 3), "items": items})
    return {"weak_units": list(units), "groups": groups}
