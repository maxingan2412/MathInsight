"""各主要视图截图留档（整页 + 关键局部），供人工逐张查看；同时断言无控制台错误。"""
from urllib.parse import quote

import pytest

from conftest import EVIDENCE, answer_letters

SHOTS = [
    ("班级总览", "overview", "#c-heat canvas"),
    ("学生档案", "student/S01", "#s-units canvas"),
    ("横向对比", "compare?unit=%s&s=S01,S02,S03" % quote("导数"), "#cmp-radar-u canvas"),
    ("试卷分析", "papers", "#p-matrix canvas"),
    ("试卷分析_冲刺卷", "papers?exam=NEXT", "#next-list table"),
    ("题库", "bank", "#bank-result .qcard"),
    ("学生练习", "practice/S01", "#pr-monitor .card-title"),
    ("学生报告", "report/S01", ".rp-paper"),
]


@pytest.fixture(scope="module", autouse=True)
def _dir():
    EVIDENCE.mkdir(parents=True, exist_ok=True)


@pytest.mark.parametrize("name,route,ready", SHOTS, ids=[s[0] for s in SHOTS])
def test_view_screenshot(mi, name, route, ready):
    mi.fresh(route, ready)
    mi.page.wait_for_timeout(600)
    mi.page.screenshot(path=str(EVIDENCE / ("通过_%s_整页.png" % name)), full_page=True)
    mi.page.screenshot(path=str(EVIDENCE / ("通过_%s_首屏.png" % name)))
    mi.assert_clean()


def test_detail_screenshots(mi, web_bank, web_class):
    # 题库：展开一道带题眼、详解、提炼的题
    q = next(x for x in web_bank["questions"] if x.get("tiyan") and x.get("refine") and x.get("solution_html") and x["type"] == "解答")
    mi.fresh("bank?kw=" + quote(q["id"]), "#qc-" + q["id"])
    mi.page.evaluate("() => document.querySelectorAll('#bank-result button[data-tg]').forEach(b => b.click())")
    mi.page.wait_for_timeout(400)
    mi.page.locator("#qc-" + q["id"]).screenshot(path=str(EVIDENCE / ("通过_题库_展开详解_%s.png" % q["id"])))
    # 练习：提交前（展开全部提示）与提交后
    Q = {x["id"]: x for x in web_bank["questions"]}
    sid, it = next((s["id"], i) for s in web_class["students"] for g in web_class["profiles"][s["id"]]["practice"]["groups"] for i in g["items"]
                   if Q[i["qid"]]["type"] in ("单选", "多选") and len(i.get("hints") or []) >= 2)
    mi.fresh("practice/%s?q=%s" % (sid, it["qid"]), "#pr-q .qid")
    mi.page.evaluate("localStorage.clear()")
    mi.fresh("practice/%s?q=%s" % (sid, it["qid"]), "#pr-q .qid")
    while mi.page.locator("#pr-hint:not([disabled])").count():
        mi.page.click("#pr-hint")
    mi.page.wait_for_timeout(300)
    mi.page.screenshot(path=str(EVIDENCE / "通过_学生练习_提交前_提示全开.png"), full_page=True)
    for L in answer_letters(Q[it["qid"]]):
        mi.page.click('#pr-q button[data-opt="%s"]' % L)
    mi.page.click("#pr-submit")
    mi.page.click("#pr-sol")
    mi.page.wait_for_timeout(300)
    mi.page.screenshot(path=str(EVIDENCE / "通过_学生练习_提交后_详解.png"), full_page=True)
    # 总览图表行局部
    mi.fresh("overview", "#c-heat canvas")
    mi.page.wait_for_timeout(400)
    mi.page.locator("#c-heat").screenshot(path=str(EVIDENCE / "通过_班级总览_热力图.png"))
    mi.page.locator(".card.diag").first.screenshot(path=str(EVIDENCE / "通过_班级总览_诊断1.png"))
    mi.assert_clean()
