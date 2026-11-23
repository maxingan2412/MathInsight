"""试卷分析：切换考试、KPI、题目表与得分率、展开题干与详解、覆盖矩阵、自动组卷的冲刺卷。"""
import pytest


def _analyses(C):
    return C["paper_analysis"] + [C["next_paper"]["analysis"]]


def _exam(C, eid):
    return [e for e in C["exams"] + [C["next_paper"]["exam"]] if e["id"] == eid][0]


def test_tabs_switch_exam(mi, web_class):
    C = web_class
    mi.fresh("papers", "#next-list table")
    tabs = mi.page.eval_on_selector_all(".tabs button", "bs => bs.map(b => b.dataset.exam)")
    assert tabs == [a["id"] for a in _analyses(C)]
    for a in _analyses(C):
        mi.navigating(lambda: mi.page.click('.tabs button[data-exam="%s"]' % a["id"]), "#next-list table")
        assert mi.page.get_attribute(".tabs button.on", "data-exam") == a["id"]
        e = _exam(C, a["id"])
        assert e["title"] in mi.page.inner_text(".stage-note") and e["stage"] in mi.page.inner_text(".stage-note")
        total = mi.page.evaluate("[...document.querySelectorAll('.kpi')][0].querySelector('.kpi-value').textContent")
        assert total == "%s分" % a["total"]
        assert "%d 题" % len(e["items"]) in mi.page.inner_text(".kpi >> nth=0")
        assert "%d节" % len(a["sections_covered"]) == mi.page.evaluate("[...document.querySelectorAll('.kpi')][2].querySelector('.kpi-value').textContent")
        rows = mi.page.eval_on_selector_all("#next-list tbody tr:not([data-row])", "trs => trs.map(t => [...t.children].map(c => c.textContent.trim()))")
        assert [r[1] for r in rows] == [c["qid"] for c in a["curve"]]
        has_rate = mi.page.locator("#next-list thead th", has_text="全班得分率").count() == 1
        assert has_rate == (a["id"] != "NEXT")
        if has_rate:
            for r, c in zip(rows, a["curve"]):
                rate = C["item_rate"].get(c["qid"])
                assert r[5] == ("—" if rate is None else "%d%%" % round(rate * 100)) or abs(int(r[5].rstrip("%")) - rate * 100) <= 0.5 + 1e-9
        assert mi.series("p-unit")[0]["data"] == [a["unit_share"].get(u, 0) for u in C["meta"]["units"]]
        assert mi.series("p-curve")[0]["data"] == [c["difficulty"] for c in a["curve"]]
        for cid in ["p-unit", "p-curve", "p-theme", "p-comp", "p-matrix", "p-cum"]:
            assert mi.chart_ink(cid) > 300, "%s 的图表 %s 是空的" % (a["id"], cid)
    mi.assert_clean()


def test_exam_total_equals_item_scores(mi, web_class):
    """卷面总分 = 题目表各题分值之和。"""
    C = web_class
    mi.fresh("papers", "#next-list table")
    for a in _analyses(C):
        mi.goto("papers?exam=" + a["id"], "#next-list table")
        scores = mi.page.eval_on_selector_all("#next-list tbody tr:not([data-row])", "trs => trs.map(t => +t.children[3].textContent)")
        assert sum(scores) == a["total"] == sum(c["score"] for c in a["curve"]), a["id"]


def test_expand_question_and_toggles(mi, web_class, web_bank):
    C = web_class
    Q = {q["id"]: q for q in web_bank["questions"]}
    a = C["paper_analysis"][0]
    mi.fresh("papers?exam=" + a["id"], "#next-list table")
    qid = next(c["qid"] for c in a["curve"] if Q[c["qid"]].get("solution_html") and Q[c["qid"]]["type"] == "解答")
    mi.page.click('#next-list a[data-open="%s"]' % qid)
    card = '#next-list tr[data-row="%s"] #qc-%s' % (qid, qid)
    mi.page.wait_for_selector(card)
    assert "#/papers" in mi.hash(), "点题号不应跳走"
    for tg in ["answer", "solution"]:
        mi.page.click(card + ' button[data-tg="%s"]' % tg)
        sec = card + ' [data-sec="%s"]' % tg
        assert mi.page.is_visible(sec)
    ok, bad, left = mi.katex_report('#next-list tr[data-row="%s"]' % qid)
    assert ok > 0 and bad == 0 and not left, (qid, ok, bad, left[:5])
    mi.page.click(card + ' button[data-tg="solution"]')
    assert not mi.page.is_visible(card + ' [data-sec="solution"]')
    mi.page.click('#next-list a[data-open="%s"]' % qid)
    assert not mi.page.is_visible('#next-list tr[data-row="%s"]' % qid)
    mi.assert_clean()


def test_coverage_matrix(mi, web_class):
    pc = web_class["paper_compare"]
    mi.fresh("papers", "#p-matrix canvas")
    data = mi.series("p-matrix")[0]["data"]
    mu = list(pc["matrix"].keys())
    assert sorted(tuple(d) for d in data) == sorted((ei, ui, v) for ui, u in enumerate(mu) for ei, v in enumerate(pc["matrix"][u]))
    assert mi.series("p-cum")[0]["data"] == pc["cumulative_units"]
    sub = mi.page.inner_text(".card.span-2 .card-sub")
    if pc["never_tested"]:
        assert all(u in sub for u in pc["never_tested"])
    else:
        assert "所有板块均已考到" in sub


def test_next_paper_avoids_tested_questions(mi, web_class):
    """README：梯度组卷自动避开已考过的题。"""
    C = web_class
    used = {i if isinstance(i, str) else i.get("qid") for e in C["exams"] for i in e["items"]}
    nxt = [c["qid"] for c in C["next_paper"]["analysis"]["curve"]]
    mi.fresh("papers?exam=NEXT", "#next-list table")
    rows = mi.page.eval_on_selector_all("#next-list a[data-open]", "as => as.map(a => a.dataset.open)")
    assert rows == nxt
    assert not (set(rows) & used), "冲刺卷里出现了已考过的题：%s" % sorted(set(rows) & used)
    assert len(set(rows)) == len(rows), "冲刺卷里有重复题"
