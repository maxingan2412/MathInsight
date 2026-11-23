"""学生档案与阶段报告：切换学生、搜索、图表数据、推荐题、学情复盘文字包、打印报告。"""
import re

import pytest


def _thetarank(C, sid):
    arr = sorted((p["theta"] for p in C["profiles"].values()), reverse=True)
    return arr.index(C["profiles"][sid]["theta"]) + 1


def _check_profile(mi, C, sid):
    p = C["profiles"][sid]
    head = mi.page.inner_text(".profile-name") + mi.page.inner_text(".profile-meta")
    assert p["name"] in head and sid in head
    assert "θ = %.2f" % p["theta"] in head
    assert "班内第 %d 名" % _thetarank(C, sid) in head
    last = p["trend"][-1]
    assert ("%s 分 / 第 %d 名" % (("%g" % last["total"]), last["rank"])) in head or ("%s 分 / 第 %d 名" % (last["total"], last["rank"])) in head
    radar = mi.series("s-unit-radar")[0]["data"]
    assert radar[0] == [u["mastery"] for u in p["units"]]
    assert mi.series("s-comp-radar")[0]["data"][0] == [c["mastery"] for c in p["competencies"]]
    assert mi.series("s-trend")[0]["data"] == [t["total"] for t in p["trend"]]
    assert mi.series("s-trend")[2]["data"] == [t["rank"] for t in p["trend"]]
    assert sum(mi.series("s-err")[0]["data"]) == sum(p["errors"].values())
    bars = mi.series("s-units")[0]["data"]
    assert bars == sorted((u["mastery"] for u in p["units"]), reverse=True)
    for cid in ["s-unit-radar", "s-comp-radar", "s-trend", "s-err", "s-units"]:
        assert mi.chart_ink(cid) > 500, "图表 %s 是空的" % cid
    tags = mi.page.inner_text(".tag-row")
    for u in p["strong"] + p["weak"]:
        assert u in tags
    advice = mi.page.eval_on_selector_all(".advice-list li", "es => es.map(e => e.textContent)")
    assert advice == p["advice"]
    n = sum(len(g["items"]) for g in p["practice"]["groups"])
    assert ("推荐练习（%d 题）" % n) in mi.page.inner_text("#view")
    cards = mi.page.eval_on_selector_all("#view .qcard .qid", "es => es.map(e => e.textContent)")
    assert cards == [it["qid"] for g in p["practice"]["groups"] for it in g["items"]]


def test_profile_matches_data(mi, web_class):
    sid = web_class["students"][0]["id"]
    mi.fresh("student/" + sid, "#s-units canvas")
    _check_profile(mi, web_class, sid)
    ok, bad, left = mi.katex_report()
    assert ok > 0 and bad == 0 and not left, (ok, bad, left[:5])
    mi.assert_clean()


def test_switch_student_changes_everything(mi, web_class):
    C = web_class
    a, b = C["students"][0]["id"], C["students"][7]["id"]
    mi.fresh("student/" + a, "#s-units canvas")
    before = mi.page.inner_text(".profile-meta")
    mi.navigating(lambda: mi.page.click('#stu-list a[href="#/student/%s"]' % b), "#s-units canvas")
    assert mi.hash() == "#/student/" + b
    assert mi.page.inner_text(".profile-meta") != before
    assert mi.page.get_attribute("#stu-list a.active", "href") == "#/student/" + b
    _check_profile(mi, C, b)
    mi.assert_clean()


def test_student_search_filters_list(mi, web_class):
    C = web_class
    mi.fresh("student/S01", "#stu-list")
    target = C["students"][10]
    for key in [target["name"][1:], target["id"].lower(), target["id"]]:
        mi.page.fill("#stu-search", key)
        vis = mi.page.eval_on_selector_all("#stu-list .item", "es => es.filter(e => e.style.display !== 'none').map(e => e.querySelector('.sid').textContent)")
        want = [s["id"] for s in C["students"] if key.lower() in (s["name"] + " " + s["id"]).lower()]
        assert vis == want and target["id"] in vis, key
    mi.page.fill("#stu-search", "不存在的名字zz")
    assert mi.page.eval_on_selector_all("#stu-list .item", "es => es.filter(e => e.style.display !== 'none').length") == 0
    mi.page.fill("#stu-search", "")
    assert mi.page.eval_on_selector_all("#stu-list .item", "es => es.filter(e => e.style.display !== 'none').length") == len(C["students"])


def test_practice_links_from_profile(mi, web_class):
    sid = web_class["students"][2]["id"]
    p = web_class["profiles"][sid]
    qid = p["practice"]["groups"][1]["items"][2]["qid"]
    mi.fresh("student/" + sid, "#s-units canvas")
    mi.navigating(lambda: mi.page.click('a[href="#/practice/%s?q=%s"]' % (sid, qid)), "#pr-q .qid")
    assert mi.page.inner_text("#pr-q .qid") == qid
    mi.navigating(lambda: mi.page.click('#view a.btn[href="#/student/%s"]' % sid), "#s-units canvas")
    mi.navigating(lambda: mi.page.locator('.page-actions a[href="#/practice/%s"]' % sid).first.click(), "#pr-q .qid")
    assert mi.hash() == "#/practice/" + sid
    mi.assert_clean()


def test_review_pack_has_no_identity(mi, web_class):
    """阶段复盘文字包：不含姓名、学号、班级名；内容来自本人数据。"""
    C = web_class
    for s in C["students"][:6]:
        mi.goto("student/" + s["id"], "#s-ai")
        mi.page.click("#s-ai")
        txt = mi.page.input_value("#s-ai-box textarea")
        p = C["profiles"][s["id"]]
        assert len(txt) > 200
        assert p["name"] not in txt, "包里出现了姓名"
        assert not re.search(r"(?<![A-Za-z0-9-])%s(?![0-9])" % s["id"], txt), "包里出现了学号"
        assert C["meta"]["class"] not in txt
        for u in p["weak"]:
            assert u in txt
        shown = re.search(r"共 (\d+) 字", mi.page.inner_text("#s-ai-box .ai-pack-head")).group(1)
        assert int(shown) == len(txt)
        mi.page.click('#s-ai-box [data-ai="close"]')
        assert mi.page.inner_html("#s-ai-box") == ""
    mi.assert_clean()


def test_review_pack_copy_logs(mi, web_class, context):
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    sid = web_class["students"][0]["id"]
    mi.fresh("student/" + sid, "#s-ai")
    mi.page.evaluate("localStorage.clear()")
    mi.page.click("#s-ai")
    txt = mi.page.input_value("#s-ai-box textarea")
    mi.page.click('#s-ai-box [data-ai="copy"]')
    mi.page.wait_for_selector("#s-ai-box .ai-pack-msg.ok, #s-ai-box .ai-pack-msg.warn")
    st = mi.page.evaluate("JSON.parse(localStorage.getItem('mi_practice_%s'))" % sid)
    assert st and st["ai"] and st["ai"][-1]["scene"] == "review"
    if mi.page.locator("#s-ai-box .ai-pack-msg.ok").count():
        assert mi.page.evaluate("navigator.clipboard.readText()") == txt


# ---------- 阶段报告 ----------
def test_report_single_student(mi, web_class):
    C = web_class
    i = 4
    sid = C["students"][i]["id"]
    p = C["profiles"][sid]
    mi.page.add_init_script("window.__printed = 0; window.print = () => { window.__printed++; };")
    mi.fresh("student/" + sid, "#s-units canvas")
    mi.navigating(lambda: mi.page.click('a[href="#/report/%s"]' % sid), ".rp-paper")
    t = mi.page.inner_text(".rp-paper")
    assert p["name"] in t and sid in t
    last = p["trend"][-1]
    assert "班级第 %d 名（共 %d 人）" % (last["rank"], len(C["students"])) in t
    n = sum(len(g["items"]) for g in p["practice"]["groups"])
    assert "推荐练习（%d 题）" % n in t
    for cid in ["rp-trend-0", "rp-units-0"]:
        assert mi.chart_ink(cid) > 20, cid
    assert mi.series("rp-trend-0")[0]["data"] == [x["total"] for x in p["trend"]]
    # 打印按钮
    mi.page.click("#rp-print")
    assert mi.page.evaluate("window.__printed") == 1
    # 上一位 / 下一位
    nx = C["students"][i + 1]
    mi.navigating(lambda: mi.page.click('.rp-toolbar a[href="#/report/%s"]' % nx["id"]), ".rp-paper")
    assert nx["name"] in mi.page.inner_text(".rp-name")
    assert "第 %d / %d 位" % (i + 2, len(C["students"])) in mi.page.inner_text(".rp-toolbar")
    pv = C["students"][i]
    mi.navigating(lambda: mi.page.click('.rp-toolbar a[href="#/report/%s"]' % pv["id"]), ".rp-paper")
    assert pv["name"] in mi.page.inner_text(".rp-name")
    mi.navigating(lambda: mi.page.click('.rp-toolbar a[href="#/student/%s"]' % pv["id"]), "#s-units canvas")
    assert not mi.page.evaluate("document.body.classList.contains('report-mode')")
    mi.assert_clean()


def test_report_first_and_last_have_disabled_neighbors(mi, web_class):
    C = web_class
    mi.fresh("report/" + C["students"][0]["id"], ".rp-paper")
    assert mi.page.locator(".rp-toolbar button[disabled]").count() == 1
    mi.goto("report/" + C["students"][-1]["id"], ".rp-paper")
    assert mi.page.locator(".rp-toolbar button[disabled]").count() == 1
    assert "第 %d / %d 位" % (len(C["students"]), len(C["students"])) in mi.page.inner_text(".rp-toolbar")
