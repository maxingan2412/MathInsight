"""横向对比：切换板块后排名表与统计数字、学生雷达叠加（选 2～3 人）。"""
import re
import statistics


def _rows(mi):
    return mi.page.eval_on_selector_all(
        "#cmp-table tbody tr",
        "trs => trs.map(tr => [tr.querySelector('.muted.small').textContent, tr.children[2].textContent.trim()])",
    )


def _unit_rows(C, unit):
    rows = []
    for s in C["students"]:
        u = [x for x in C["profiles"][s["id"]]["units"] if x["unit"] == unit][0]
        rows.append((s["id"], u["mastery"]))
    return sorted(rows, key=lambda r: -r[1])


def test_default_unit_and_ranking(mi, web_class):
    C = web_class
    mi.fresh("compare", "#cmp-table table")
    unit = C["overview"]["weak_units"][0]
    assert mi.page.input_value("#cmp-unit") == unit
    rows = _rows(mi)
    want = _unit_rows(C, unit)
    assert len(rows) == len(C["students"])
    assert [r[0] for r in rows] == [w[0] for w in want]
    assert [r[1] for r in rows] == ["%d%%" % round(w[1] * 100 + 1e-9) for w in want] or \
        all(abs(int(r[1].rstrip("%")) - w[1] * 100) <= 0.5 + 1e-9 for r, w in zip(rows, want))
    mi.assert_clean()


def test_change_unit_updates_table_and_stats(mi, web_class):
    C = web_class
    mi.fresh("compare", "#cmp-table table")
    units = C["meta"]["units"]
    for unit in [units[0], units[-1], units[5]]:
        before = mi.page.inner_text("#cmp-stat")
        mi.navigating(lambda: mi.page.select_option("#cmp-unit", unit), "#cmp-table table")
        assert "unit=" + unit in __import__("urllib.parse").parse.unquote(mi.hash())
        assert mi.page.input_value("#cmp-unit") == unit
        rows = _rows(mi)
        want = _unit_rows(C, unit)
        assert [r[0] for r in rows] == [w[0] for w in want], unit
        vals = [w[1] for w in want]
        m = re.search(r"均值 (\d+)%", mi.page.inner_text("#cmp-stat"))
        assert abs(int(m.group(1)) - statistics.mean(vals) * 100) <= 0.5 + 1e-9
        hist = mi.series("cmp-dist")[1]["data"]
        assert sum(hist) == len(C["students"])
        assert mi.chart_ink("cmp-dist") > 300
    mi.assert_clean()


def test_radar_overlay_pick(mi, web_class):
    C = web_class
    s = [x["id"] for x in C["students"]]
    mi.fresh("compare", "#cmp-radar-u canvas")
    on = lambda: mi.page.eval_on_selector_all("#cmp-pick .chip.on", "es => es.map(e => e.dataset.id)")
    assert on() == s[:2]
    names = lambda: [d for d in mi.page.eval_on_selector_all("#cmp-stu-table thead th", "es => es.map(e => e.textContent)")][1:-1]

    def radar_names():
        return mi.page.evaluate("echarts.getInstanceByDom(document.getElementById('cmp-radar-u')).getOption().series[0].data.map(d => d.name)")

    # 加第 3 人
    mi.navigating(lambda: mi.page.click('#cmp-pick .chip[data-id="%s"]' % s[5]), "#cmp-radar-u canvas")
    assert on() == sorted([s[0], s[1], s[5]], key=s.index)
    assert names() == [C["profiles"][x]["name"] for x in [s[0], s[1], s[5]]]
    assert radar_names()[:3] == names() and radar_names()[3] == "班级均值"
    vals = mi.page.evaluate("echarts.getInstanceByDom(document.getElementById('cmp-radar-u')).getOption().series[0].data[2].value")
    assert vals == [u["mastery"] for u in C["profiles"][s[5]]["units"]]
    # 第 4 人：最早选的被挤掉，最多 3 人
    mi.navigating(lambda: mi.page.click('#cmp-pick .chip[data-id="%s"]' % s[9]), "#cmp-radar-u canvas")
    assert names() == [C["profiles"][x]["name"] for x in [s[1], s[5], s[9]]]
    # 再点取消
    mi.navigating(lambda: mi.page.click('#cmp-pick .chip[data-id="%s"]' % s[5]), "#cmp-radar-u canvas")
    assert names() == [C["profiles"][x]["name"] for x in [s[1], s[9]]]
    mi.navigating(lambda: mi.page.click('#cmp-pick .chip[data-id="%s"]' % s[1]), "#cmp-radar-u canvas")
    assert names() == [C["profiles"][s[9]]["name"]]
    # 只剩 1 人时不能再取消
    h = mi.hash()
    mi.page.click('#cmp-pick .chip[data-id="%s"]' % s[9])
    mi.page.wait_for_timeout(200)
    assert mi.hash() == h and names() == [C["profiles"][s[9]]["name"]]
    for cid in ["cmp-radar-u", "cmp-radar-c"]:
        assert mi.chart_ink(cid) > 500
    mi.assert_clean()


def test_ranking_name_links_to_profile(mi, web_class):
    mi.fresh("compare", "#cmp-table table")
    first = _rows(mi)[0][0]
    mi.navigating(lambda: mi.page.click('#cmp-table a[href="#/student/%s"]' % first), "#s-units canvas")
    assert web_class["profiles"][first]["name"] in mi.page.inner_text(".profile-name")
