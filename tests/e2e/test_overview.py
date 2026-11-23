"""班级总览：KPI 数字、四类图表、薄弱板块诊断、热力图点击跳转、全班报告。"""
import pytest


@pytest.fixture
def ov_page(mi):
    mi.fresh("overview", "#c-heat canvas")
    mi.page.wait_for_timeout(200)
    return mi


def _kpi(mi, label):
    return mi.page.evaluate(
        """l => { const k = [...document.querySelectorAll('.kpi')].find(x => x.querySelector('.kpi-label').textContent === l);
        return k ? {v: k.querySelector('.kpi-value').textContent, f: k.querySelector('.kpi-foot').textContent} : null; }""",
        label,
    )


def test_kpis_match_data(ov_page, web_class, papers, questions):
    mi, C = ov_page, web_class
    assert _kpi(mi, "学生数")["v"] == "%d人" % len(C["students"])
    assert _kpi(mi, "考试次数")["v"] == "%d次" % len(C["exams"])
    bank = _kpi(mi, "题库")
    assert bank["v"] == "%d 套 / %d 题" % (len(papers), len(questions)), "题库 KPI 与 bank/ 不一致"
    regions = {}
    for q in questions:
        regions[q["region"]] = regions.get(q["region"], 0) + 1
    for r, n in regions.items():
        assert "%s %d" % (r, n) in bank["f"]
    last, prev = C["overview"]["exam_means"][-1], C["overview"]["exam_means"][-2]
    k = _kpi(mi, "最近一次均分")
    assert k["v"].startswith("%.1f" % last["mean"]) and ("/ %d" % last["full"]) in k["v"]
    d = last["mean"] - prev["mean"]
    assert ("%s%.1f" % ("+" if d >= 0 else "", d)) in k["f"]
    mi.assert_clean()


def test_charts_render_with_data(ov_page, web_class):
    mi, ov = ov_page, web_class["overview"]
    s = mi.series("c-units")
    assert [x["data"] for x in s] == [[u["mean"] for u in ov["units"]], [u["rate"] for u in ov["units"]]]
    r = mi.series("c-comp")[0]["data"][0]
    assert r == [c["mean"] for c in ov["competencies"]]
    heat = mi.series("c-heat")[0]["data"]
    hm = ov["heatmap"]
    assert len(heat) == len(hm["students"]) * len(hm["units"])
    assert sorted(tuple(x) for x in heat) == sorted((si, ui, v) for si, row in enumerate(hm["values"]) for ui, v in enumerate(row))
    assert mi.series("c-exams")[0]["data"] == [e["mean"] for e in ov["exam_means"]]
    ids = ["c-units", "c-comp", "c-heat", "c-exams"]
    for i in range(len(ov["diagnoses"])):
        ids += ["d-ev-%d" % i, "d-gm-%d" % i, "d-er-%d" % i]
    for cid in ids:
        assert mi.chart_ink(cid) > 500, "图表 %s 是空的" % cid


def test_weak_units_and_diagnoses(ov_page, web_class):
    mi, ov = ov_page, web_class["overview"]
    weak = mi.page.eval_on_selector_all(".weak-list.mt li .chip", "es => es.map(e => e.textContent)")
    assert weak == ov["weak_units"]
    diags = mi.page.locator(".card.diag")
    assert diags.count() == len(ov["diagnoses"])
    for i, d in enumerate(ov["diagnoses"]):
        t = diags.nth(i).inner_text()
        assert d["unit"] in t and d["main_competency"] in t and d["suggestion"][:20] in t
        for s in d["weakest_sections"]:
            assert s["section"] in t
        pie = mi.series("d-er-%d" % i)[0]["data"]
        assert sum(pie) == sum(d["errors"].values())


def test_heatmap_click_opens_student(ov_page, web_class):
    mi, hm = ov_page, web_class["overview"]["heatmap"]
    si, ui = 5, 2
    mi.page.locator("#c-heat").scroll_into_view_if_needed()
    pt = mi.page.evaluate(
        "([si, ui]) => { const c = echarts.getInstanceByDom(document.getElementById('c-heat'));"
        " const p = c.convertToPixel({seriesIndex: 0}, [si, ui]); const r = document.getElementById('c-heat').getBoundingClientRect();"
        " return [r.left + p[0], r.top + p[1]]; }",
        [si, ui],
    )
    mi.navigating(lambda: mi.page.mouse.click(pt[0], pt[1]), "#s-units canvas")
    sid = hm["students"][si]
    assert mi.hash() == "#/student/" + sid
    assert web_class["profiles"][sid]["name"] in mi.page.inner_text(".profile-name")


def test_print_whole_class_report(ov_page, web_class):
    mi = ov_page
    mi.navigating(lambda: mi.page.click('a[href="#/report/ALL"]'), ".rp-paper")
    assert mi.page.locator(".rp-paper").count() == len(web_class["students"])
    names = mi.page.eval_on_selector_all(".rp-paper .rp-name", "es => es.map(e => e.firstChild.textContent)")
    assert names == [s["name"] for s in web_class["students"]]
    assert mi.page.evaluate("document.body.classList.contains('report-mode')")
    mi.assert_clean()
