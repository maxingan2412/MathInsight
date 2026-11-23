"""肉眼问题的机器检查：图表里的文字互相压住、文字压住数据点、图元出界、图例颜色与线不符、色条无刻度、
同一考试两种叫法、题目表与题卡分值不一致、输入框提示文字被截断；题眼与改编方向的编号重复。

图表几何从 ECharts 的绘制列表里取（每个文字片段、每个数据点符号的屏幕矩形），与渲染方式无关。
"""
import re
from urllib.parse import quote

import pytest

LAYOUT_JS = """id => { const el = document.getElementById(id); const c = echarts.getInstanceByDom(el);
  const texts = [], marks = [];
  c.getZr().storage.getDisplayList(true).forEach(e => { if (e.invisible || e.ignore) return;
    const r0 = e.getBoundingRect(); const m = e.getComputedTransform(); const r = r0.clone(); if (m) r.applyTransform(m);
    const pt = (x, y) => m ? [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]] : [x, y];
    const box = {x: r.x, y: r.y, w: r.width, h: r.height,
      poly: [pt(r0.x, r0.y), pt(r0.x + r0.width, r0.y), pt(r0.x + r0.width, r0.y + r0.height), pt(r0.x, r0.y + r0.height)]};
    if (e.type === 'tspan' && e.style && String(e.style.text || '').trim()) texts.push(Object.assign({t: String(e.style.text)}, box));
    else if (e.type === 'path' && r.width >= 4 && r.height >= 4 && r.width <= 16 && r.height <= 16) marks.push(box); });
  const g = c.getModel().getComponent('grid'); const gr = g && g.coordinateSystem ? g.coordinateSystem.getRect() : null;
  return {W: c.getWidth(), H: c.getHeight(), texts: texts, marks: marks, grid: gr && {x: gr.x, y: gr.y, w: gr.width, h: gr.height}}; }"""


def _layout(mi, cid):
    return mi.page.evaluate(LAYOUT_JS, cid)


def _hit(a, b, tol=1.0):
    """两个（可能旋转的）矩形是否重叠超过 tol 像素：分离轴判定。"""
    for P in (a["poly"], b["poly"]):
        for i in range(4):
            (x1, y1), (x2, y2) = P[i], P[(i + 1) % 4]
            n = (y1 - y2, x2 - x1)
            ln = (n[0] ** 2 + n[1] ** 2) ** 0.5 or 1.0
            pa = [(x * n[0] + y * n[1]) / ln for x, y in a["poly"]]
            pb = [(x * n[0] + y * n[1]) / ln for x, y in b["poly"]]
            if min(max(pa), max(pb)) - max(min(pa), min(pb)) <= tol:
                return False
    return True


def _text_overlaps(L, gap=0.0):
    """文字两两重叠（gap > 0 时，间距小于 gap 像素也算）。"""
    ts = L["texts"]
    return [(a["t"], b["t"]) for i, a in enumerate(ts) for b in ts[i + 1:] if _hit(a, b, tol=1.0 - gap)]


def _text_on_marks(L, legend_bottom=30):
    # 图例里的圆点与图例文字并排，不算
    marks = [m for m in L["marks"] if m["y"] < L["H"] - legend_bottom]
    return [(t["t"], (round(m["x"]), round(m["y"]))) for t in L["texts"] for m in marks if _hit(t, m)]


def _out_of_box(L):
    bad = []
    for t in L["texts"]:
        if t["x"] < -0.5 or t["y"] < -0.5 or t["x"] + t["w"] > L["W"] + 0.5 or t["y"] + t["h"] > L["H"] + 0.5:
            bad.append(("文字", t["t"]))
    for m in L["marks"]:
        if m["y"] < -0.5 or m["y"] + m["h"] > L["H"] + 0.5:
            bad.append(("数据点", round(m["x"]), round(m["y"])))
    return bad


# ---------- 学生档案 ----------
def test_student_unit_bars_labels_clear(mi, web_class):
    """板块掌握度条形图：数值标签不被班级均值菱形压住，标签之间不重叠。"""
    bad = {}
    for s in web_class["students"][:8]:
        mi.goto("student/" + s["id"], "#s-units canvas")
        L = _layout(mi, "s-units")
        hit = _text_on_marks(L) + _text_overlaps(L)
        if hit:
            bad[s["id"]] = hit[:3]
    assert not bad, "条形图标签被压住：%s" % bad


def test_student_trend_labels_clear(mi, web_class):
    """成绩与名次走势：数据标签不与左右纵轴刻度重叠。"""
    bad = {}
    for s in web_class["students"][:8]:
        mi.goto("student/" + s["id"], "#s-trend canvas")
        L = _layout(mi, "s-trend")
        hit = _text_overlaps(L) + _out_of_box(L)
        if hit:
            bad[s["id"]] = hit[:3]
    assert not bad, "走势图文字重叠或出界：%s" % bad


# ---------- 班级总览 ----------
def test_overview_diag_charts_inside(mi, web_class):
    """诊断卡模型路小图：折线、数据点、刻度都在图内；最高的数据点离绘图区顶边至少留 4px，不贴边、不被裁。"""
    mi.fresh("overview", "#d-gm-0 canvas")
    bad = {}
    for i in range(len(web_class["overview"]["diagnoses"])):
        for cid in ("d-ev-%d" % i, "d-gm-%d" % i):
            L = _layout(mi, cid)
            g = L["grid"]
            out = _out_of_box(L) + _text_overlaps(L)
            out += [("数据点贴住或超出绘图区顶边", round(m["y"] - g["y"], 1)) for m in L["marks"]
                    if m["y"] < g["y"] + 4 and m["y"] < L["H"] - 30]
            if out:
                bad[cid] = out[:4]
    assert not bad, bad


# ---------- 试卷分析 ----------
LEGEND_JS = """id => { const c = echarts.getInstanceByDom(document.getElementById(id)); const out = [];
  c.getModel().getSeries().forEach(s => { if (s.subType !== 'line') return;
    const st = s.getData().getVisual('style') || {};
    out.push([s.name, st.fill, s.get(['lineStyle', 'color']) || st.stroke]); }); return out; }"""


def test_paper_curve_legend_matches_line(mi, web_class):
    """难度曲线：折线在图例里的颜色（系列的 itemStyle 色）就是线的颜色（lineStyle 色）。"""
    mi.fresh("papers", "#p-curve canvas")
    bad = [(n, f, s) for n, f, s in mi.page.evaluate(LEGEND_JS, "p-curve") if str(f).lower() != str(s).lower()]
    assert not bad, "图例颜色（itemStyle）与线色（lineStyle）不一致：%s" % bad


def test_paper_cum_labels_clear(mi):
    """累计覆盖图：数据标签与纵轴刻度、标签彼此之间至少隔 3px，且都在图内。"""
    mi.fresh("papers", "#p-cum canvas")
    L = _layout(mi, "p-cum")
    assert not _text_overlaps(L, gap=3), _text_overlaps(L, gap=3)
    assert not _out_of_box(L), _out_of_box(L)


def test_paper_matrix_color_bar_has_ticks(mi):
    """覆盖矩阵：色条旁有数值刻度文字。"""
    mi.fresh("papers", "#p-matrix canvas")
    M = _layout(mi, "p-matrix")
    g = M["grid"]
    vm = [t["t"] for t in M["texts"] if t["x"] >= g["x"] + g["w"] and "%" in t["t"]]
    assert len(vm) >= 2, "覆盖矩阵色条旁没有刻度文字：%s" % vm


def test_paper_exam_names_consistent(mi, web_class):
    """覆盖矩阵与累计覆盖两图横轴用同一套考试名称（与考试标题一致，不出现 M1 之类的内部编号）。"""
    mi.fresh("papers", "#p-cum canvas")
    xs = lambda cid: mi.page.evaluate("id => echarts.getInstanceByDom(document.getElementById(id)).getOption().xAxis[0].data", cid)
    titles = [e["title"].replace("高三", "") for e in web_class["exams"]]
    assert xs("p-matrix") == titles, xs("p-matrix")
    assert xs("p-cum") == titles, xs("p-cum")


def test_paper_table_score_matches_card(mi, web_class):
    """题目表里的分值与展开的题卡上写的分值一致。"""
    bad = []
    for a in web_class["paper_analysis"]:
        mi.goto("papers?exam=" + a["id"], "#next-list table")
        for c in a["curve"]:
            mi.page.click('#next-list a[data-open="%s"]' % c["qid"])
            head = mi.page.inner_text('#next-list tr[data-row="%s"] .qcard-head' % c["qid"])
            m = re.search(r"(\d+) 分", head)
            if not m or int(m.group(1)) != c["score"]:
                bad.append((a["id"], c["qid"], c["score"], head[:60]))
            mi.page.click('#next-list a[data-open="%s"]' % c["qid"])
    assert not bad, "%d 题表格分值与题卡不一致，例如 %s" % (len(bad), bad[:5])


# ---------- 题库 ----------
def test_bank_unit_chart_labels_clear(mi):
    mi.fresh("bank", "#b-unit canvas")
    L = _layout(mi, "b-unit")
    assert not _text_overlaps(L), "「按板块」横轴标签重叠：%s" % _text_overlaps(L)[:5]
    assert not _out_of_box(L), _out_of_box(L)


def test_bank_keyword_placeholder_fits(mi):
    mi.fresh("bank", "#f-kw")
    need, have = mi.page.evaluate("""() => { const i = document.getElementById('f-kw'); const cs = getComputedStyle(i);
      const cv = document.createElement('canvas').getContext('2d'); cv.font = cs.fontSize + ' ' + cs.fontFamily;
      return [cv.measureText(i.placeholder).width, i.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)]; }""")
    assert need <= have, "关键词框提示文字要 %.0fpx，框内只有 %.0fpx" % (need, have)


@pytest.mark.parametrize("qid", ["I-2024-18", "SH-2026-17", "I-2026-16"])
def test_card_numbering_not_doubled(mi, qid):
    """题眼开头不出现「((2))」；改编方向、易错等列表不出现「1. 1.」式的套层编号。"""
    mi.fresh("bank?kw=" + quote(qid), "#qc-" + qid)
    mi.page.evaluate("id => document.querySelectorAll('#qc-' + id + ' button[data-tg]').forEach(b => b.click())", qid)
    t = mi.page.inner_text("#qc-" + qid)
    assert "((" not in t and "（（" not in t
    nested = mi.page.evaluate("id => document.querySelectorAll('#qc-' + id + ' li > ol:first-child, #qc-' + id + ' li > ul:first-child').length", qid)
    assert nested == 0, "%s 有 %d 处列表项里直接套了一层列表（显示成「1. 1.」）" % (qid, nested)
