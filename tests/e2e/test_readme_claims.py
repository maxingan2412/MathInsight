"""核对 README「核心功能」里的宣称在演示网站上是否落实。"""
import re
from urllib.parse import quote

import pytest

pytestmark = pytest.mark.claim


def test_every_question_has_solution(mi, questions):
    """宣称：逐题配有详解。"""
    missing = [q["id"] for q in questions if not (q.get("solution_html") or "").strip()]
    assert not missing, missing[:20]


def test_card_shows_section_unit_theme_competency(mi, web_bank):
    """宣称：每题标注教材小节、板块、课标主题、六大核心素养权重。逐项看题库卡片是否显示。"""
    q = next(x for x in web_bank["questions"] if x.get("competencies") and x.get("theme") and x.get("sections"))
    mi.fresh("bank?kw=" + quote(q["id"]), "#qc-" + q["id"])
    mi.page.evaluate("id => document.querySelectorAll('#qc-' + id + ' button[data-tg]').forEach(b => b.click())", q["id"])
    t = mi.page.inner_text("#qc-" + q["id"])
    missing = []
    for s in q["sections"]:
        if s["name"] not in t:
            missing.append("小节 " + s["name"])
    for u in q["units"]:
        if u not in t:
            missing.append("板块 " + u)
    if q["theme"] not in t:
        missing.append("课标主题 " + q["theme"])
    for c in q["competencies"]:
        if c not in t:
            missing.append("素养 " + c)
    assert not missing, "%s 卡片上看不到：%s" % (q["id"], missing)


def test_practice_in_zone_of_proximal_development(mi, web_class, web_bank):
    """宣称：推题难度落在最近发展区（预测得分率 60%–85%），另配挑战题。核对页面上「巩固」题显示的预计得分率。
    区间内题不够时推荐会放宽：这类题必须带 relaxed 标记，并在练习页与学生档案上标出「区间内题不足，放宽」；
    区间内的题不得带这个标记。"""
    LABEL = "区间内题不足，放宽"
    out, wrong_flag = [], []
    for s in web_class["students"]:
        for g in web_class["profiles"][s["id"]]["practice"]["groups"]:
            for it in g["items"]:
                inside = 0.6 <= it["pred"] <= 0.85
                if it["role"] == "巩固" and not inside:
                    out.append((s["id"], it["qid"], it["pred"], bool(it.get("relaxed"))))
                if it.get("relaxed") and (inside or it["role"] != "巩固"):
                    wrong_flag.append((s["id"], it["qid"], it["pred"], it["role"]))
    assert not wrong_flag, "区间内或非巩固题被标成放宽：%s" % wrong_flag[:5]
    unmarked = [x for x in out if not x[3]]
    total = sum(1 for s in web_class["students"] for g in web_class["profiles"][s["id"]]["practice"]["groups"] for it in g["items"] if it["role"] == "巩固")
    assert not unmarked, "%d / %d 道「巩固」题的预计得分率不在 60%%–85%%，且没有标明放宽，例如 %s" % (len(unmarked), total, unmarked[:5])
    # 抽一条放宽的题，在练习页和学生档案上看到标记；再抽一条区间内的题，看到没有标记
    if out:
        sid, qid, pred, _ = out[0]
        mi.fresh("practice/%s?q=%s" % (sid, qid), "#pr-q .qid")
        head = mi.page.inner_text("#pr-q .qcard-head")
        assert "巩固" in head and "预计得分率 %d%%" % round(pred * 100) in head and LABEL in head
        mi.fresh("student/" + sid, "#qc-" + qid)
        assert LABEL in mi.page.inner_text("#qc-" + qid + " .qcard-head")
    sid, qid = next((s["id"], it["qid"]) for s in web_class["students"] for g in web_class["profiles"][s["id"]]["practice"]["groups"]
                    for it in g["items"] if it["role"] == "巩固" and not it.get("relaxed"))
    mi.fresh("practice/%s?q=%s" % (sid, qid), "#pr-q .qid")
    assert LABEL not in mi.page.inner_text("#pr-q .qcard-head")


def test_hint_ladder_direction_crux_breakthrough(mi, web_class, web_bank):
    """宣称：提示阶梯 方向 → 卡点 → 打通。统计推荐题里只有 1 级提示的；并在页面上看一道。"""
    Q = {q["id"]: q for q in web_bank["questions"]}
    flat, total = [], 0
    for s in web_class["students"]:
        for g in web_class["profiles"][s["id"]]["practice"]["groups"]:
            for it in g["items"]:
                total += 1
                n = len(it.get("hints") or [])   # 题眼已折进 方向/卡点/打通，页面不再把题眼原文追加一遍
                if n < 3 and not (n == 1 and not Q[it["qid"]].get("tiyan") and not Q[it["qid"]].get("refine")):
                    flat.append((s["id"], it["qid"], n, (it.get("hints") or [""])[0][:20]))
    if flat:
        sid, qid, n, _ = flat[0]
        mi.fresh("practice/%s?q=%s" % (sid, qid), "#pr-q .qid")
        mi.page.evaluate("localStorage.clear()")
        mi.fresh("practice/%s?q=%s" % (sid, qid), "#pr-q .qid")
        if mi.page.locator("#pr-hint").count():
            assert mi.page.inner_text("#pr-hint") == "提示（0/%d）" % n
    generic = {}
    for _, _, _, h in flat:
        generic[h] = generic.get(h, 0) + 1
    assert not flat, "%d / %d 道推荐题的提示不足 3 级（方向/卡点/打通），最常见的提示开头：%s" % (
        len(flat), total, sorted(generic.items(), key=lambda x: -x[1])[:3])


def test_practice_is_for_weak_units(mi, web_class):
    """宣称：针对弱板块推题。推荐题分组的板块应属于该生弱项。"""
    bad = []
    for s in web_class["students"]:
        p = web_class["profiles"][s["id"]]
        for g in p["practice"]["groups"]:
            if g["unit"] not in p["weak"]:
                bad.append((s["id"], g["unit"], p["weak"]))
    mi.fresh("student/" + web_class["students"][0]["id"], "#s-units canvas")
    assert not bad, bad[:5]


def test_gradient_paper_assembly_entry(mi, web_class):
    """宣称：按卷型模板自动组卷（一模→四模冲刺）。页面上能看到各阶段与自动组出的冲刺卷。"""
    mi.fresh("papers", "#next-list table")
    stages = set()
    for e in web_class["exams"] + [web_class["next_paper"]["exam"]]:
        mi.goto("papers?exam=" + e["id"], ".stage-note")
        stages.add(e["stage"])
        assert e["stage"] in mi.page.inner_text(".stage-note")
    assert mi.page.locator("text=系统自动组卷").count() >= 1
    assert len(stages) >= 3


def test_tiyan_for_mid_and_hard_questions(mi, web_bank):
    """宣称：中档以上的题提炼「题眼」。按难度 ≥0.4（站内「中」档起点）统计没有题眼的题。"""
    mid = [q for q in web_bank["questions"] if q["difficulty"] >= 0.4]
    no = [q["id"] for q in mid if not q.get("tiyan")]
    no_crux = [i for i in no if not ((next(q for q in mid if q["id"] == i).get("refine") or {}).get("crux"))]
    assert not no, "%d / %d 道中档以上题没有「题眼」按钮（其中 %d 题在「提炼」里有卡点段），例如 %s" % (
        len(no), len(mid), len(no) - len(no_crux), no[:10])
