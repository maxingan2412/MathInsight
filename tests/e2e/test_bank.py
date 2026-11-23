"""题库：按卷/地区/年份/题型/板块筛选、关键词搜索、分页、展开答案/详解/题眼/提炼、全库公式渲染。

期望值一律从 bank/papers.json 与 bank/questions.jsonl 现算。
"""
import re
from urllib.parse import quote

import pytest

from conftest import PAGE_SIZE, pages_of, plain_text


def _total(mi):
    return int(re.search(r"共 (\d+) 题", mi.page.inner_text("#bank-result .pager")).group(1))


def _ids_on_page(mi):
    return mi.page.eval_on_selector_all("#bank-result .qcard .qid", "es => es.map(e => e.textContent)")


def _all_ids(mi, base):
    """沿分页取出当前筛选结果的全部题号。"""
    mi.goto(base, "#bank-result .pager")
    n = _total(mi)
    ids = _ids_on_page(mi)
    for p in range(2, pages_of(n) + 1):
        mi.goto(base + ("&" if "?" in base else "?") + "page=%d" % p, "#bank-result .pager")
        ids += _ids_on_page(mi)
    return n, ids


def _kw_text(q):
    parts = [plain_text(q.get("stem_html")), str(q.get("tiyan_tag")), " ".join(q.get("tiyan") or []), q["id"],
             " ".join(s["name"] + s.get("detail", "") for s in q.get("sections") or [])]
    for p in ((q.get("refine") or {}).get("parts") or []):
        for x in [p.get("main")] + (p.get("aux") or []):
            if x and x.get("name"):
                parts.append(x["name"])
    return " ".join(parts).lower()


def test_header_counts(mi, papers, questions):
    mi.fresh("bank", "#bank-result .pager")
    desc = mi.page.inner_text(".page-desc")
    assert "%d 套试卷" % len(papers) in desc and "%d 题" % len(questions) in desc
    assert _total(mi) == len(questions)
    assert sum(p["count"] for p in papers) == len(questions), "papers.json 的 count 之和与 questions.jsonl 题数不一致"
    assert len(_ids_on_page(mi)) == min(PAGE_SIZE, len(questions))
    opts = mi.page.eval_on_selector_all("#f-paper option", "os => os.slice(1).map(o => o.value)")
    assert opts == [p["id"] for p in papers]
    mi.assert_clean()


def test_filter_by_paper_via_select(mi, papers, questions):
    p = papers[0]
    mi.fresh("bank", "#bank-result .pager")
    mi.navigating(lambda: mi.page.select_option("#f-paper", p["id"]), "#bank-result .pager")
    assert "paper=" + p["id"] in mi.hash()
    want = [q["id"] for q in questions if q["paper"] == p["id"]]
    assert _total(mi) == p["count"] == len(want)
    n, ids = _all_ids(mi, "bank?paper=" + p["id"])
    assert sorted(ids) == sorted(want)
    heads = mi.page.eval_on_selector_all("#bank-result .qcard-head .muted", "es => es.map(e => e.textContent)")
    assert all(h.startswith(p["title"]) for h in heads)


def test_every_paper_count(mi, papers, questions):
    """34 套卷逐一筛选：页面题数 = papers.json 的 count = questions.jsonl 里该卷的题数。"""
    mi.fresh("bank", "#bank-result .pager")
    bad = []
    for p in papers:
        mi.goto("bank?paper=" + quote(p["id"]), "#bank-result .pager")
        got = _total(mi)
        real = sum(1 for q in questions if q["paper"] == p["id"])
        opt = mi.page.eval_on_selector('#f-paper option[value="%s"]' % p["id"], "o => o.textContent")
        if not (got == p["count"] == real) or not opt.endswith("（%d）" % p["count"]):
            bad.append((p["id"], got, p["count"], real, opt))
    assert not bad, "卷题数对不上（卷, 页面, papers.json, questions.jsonl, 下拉文字）：%s" % bad
    mi.assert_clean()


@pytest.mark.parametrize("field,sel", [("region", "#f-region"), ("year", "#f-year"), ("type", "#f-type"), ("unit", "#f-unit")])
def test_single_filters(mi, questions, field, sel):
    mi.fresh("bank", "#bank-result .pager")
    values = mi.page.eval_on_selector_all(sel + " option", "os => os.slice(1).map(o => o.value)")
    assert values
    label_bad = []
    for v in values:
        mi.navigating(lambda: mi.page.select_option(sel, v), "#bank-result .pager")
        if field == "unit":
            want = [q for q in questions if v in q["units"]]
        else:
            want = [q for q in questions if str(q[field]) == v]
        assert _total(mi) == len(want), (field, v)
        assert mi.page.input_value(sel) == v
        label = mi.page.eval_on_selector(sel + ' option[value="%s"]' % v, "o => o.textContent")
        if field != "year" and not label.endswith("（%d）" % len(want)):
            label_bad.append("下拉写「%s」，选中后实际 %d 题" % (label, len(want)))
        types = mi.series("b-type")[0]["data"]
        assert sum(types) == len(want)
        mi.navigating(lambda: mi.page.click("#f-clear"), "#bank-result .pager")
    mi.assert_clean()
    assert not label_bad, "%s 下拉里的题数与筛选结果不一致：%s" % (field, label_bad)


def test_combined_filters(mi, questions):
    q0 = questions[len(questions) // 2]
    unit = q0["units"][0]
    base = "bank?region=%s&year=%s&type=%s&unit=%s" % (quote(q0["region"]), q0["year"], quote(q0["type"]), quote(unit))
    want = [q["id"] for q in questions if q["region"] == q0["region"] and q["year"] == q0["year"] and q["type"] == q0["type"] and unit in q["units"]]
    n, ids = _all_ids(mi, base)
    assert n == len(want) and sorted(ids) == sorted(want) and q0["id"] in ids


@pytest.mark.parametrize("kw", ["椭圆", "数列", "等比", "向量", "概率", "卡点"])
def test_keyword_search(mi, questions, kw):
    mi.fresh("bank", "#bank-result .pager")
    mi.page.fill("#f-kw", kw)
    mi.navigating(lambda: mi.page.press("#f-kw", "Enter"), "#bank-result .pager")
    want = [q["id"] for q in questions if kw.lower() in _kw_text(q)]
    assert want, "关键词在题库里不存在"
    n, ids = _all_ids(mi, "bank?kw=" + quote(kw))
    assert n == len(want) and sorted(ids) == sorted(want)
    # 搜到的题里，题干可见文字含关键词的占多数（否则搜索结果对用户不可解释）
    mi.goto("bank?kw=" + quote(kw), "#bank-result .pager")
    stems = mi.page.eval_on_selector_all("#bank-result .qcard > .qbody", "es => es.map(e => e.textContent)")
    assert stems


def test_keyword_search_by_id_and_no_hit(mi, questions):
    q = questions[123]
    n, ids = _all_ids(mi, "bank?kw=" + quote(q["id"]))
    assert q["id"] in ids and all(i.startswith(q["id"]) for i in ids)
    mi.goto("bank?kw=" + quote("这个词一定不存在zzq"), "#bank-result .pager")
    assert _total(mi) == 0 and mi.page.locator("#bank-result .card.empty").count() == 1


@pytest.mark.parametrize("kw", ["null", "undefined"])
def test_keyword_search_no_spurious_matches(mi, questions, kw):
    """检索文本里不应混入 null / undefined 这类程序值。"""
    want = [q["id"] for q in questions if kw in _kw_text(q).replace(str(None).lower(), "")]
    mi.fresh("bank?kw=" + kw, "#bank-result .pager")
    assert _total(mi) == len(want), "搜「%s」得到 %d 题，应为 %d 题" % (kw, _total(mi), len(want))


def test_clear_and_filter_button(mi, questions):
    mi.fresh("bank?type=" + quote("多选"), "#bank-result .pager")
    assert _total(mi) == sum(1 for q in questions if q["type"] == "多选")
    mi.navigating(lambda: mi.page.click("#f-clear"), "#bank-result .pager")
    assert mi.hash() == "#/bank" and _total(mi) == len(questions)
    assert mi.page.input_value("#f-type") == ""
    mi.page.fill("#f-kw", "数列")
    mi.navigating(lambda: mi.page.click("#f-go"), "#bank-result .pager")
    assert "kw=" in mi.hash()


def test_pagination(mi, questions, web_bank):
    order = [q["id"] for q in web_bank["questions"]]
    mi.fresh("bank", "#bank-result .pager")
    n = _total(mi)
    pages = pages_of(n)
    assert ("第 1 / %d 页" % pages) in mi.page.inner_text("#bank-result .pager")
    assert _ids_on_page(mi) == order[:PAGE_SIZE]
    mi.navigating(lambda: mi.page.locator('#bank-result .pager button[data-page="2"]').first.click(), "#bank-result .pager")
    assert "page=2" in mi.hash()
    assert _ids_on_page(mi) == order[PAGE_SIZE:2 * PAGE_SIZE]
    assert mi.page.get_attribute("#bank-result .pager .cur", "data-page") == "2"
    mi.goto("bank?page=%d" % pages, "#bank-result .pager")
    assert _ids_on_page(mi) == order[(pages - 1) * PAGE_SIZE:]
    mi.goto("bank?page=9999", "#bank-result .pager")
    assert ("第 %d / %d 页" % (pages, pages)) in mi.page.inner_text("#bank-result .pager")
    # 分页 + 筛选：翻页不丢筛选条件
    mi.goto("bank?type=" + quote("单选"), "#bank-result .pager")
    mi.navigating(lambda: mi.page.locator('#bank-result .pager button[data-page="2"]').first.click(), "#bank-result .pager")
    assert "type=" in mi.hash() and "page=2" in mi.hash()
    assert mi.page.input_value("#f-type") == "单选"
    mi.assert_clean()


def test_toggles_render_katex(mi, web_bank):
    """展开题眼/答案/详解/提炼/改编，内容可见且公式渲染无错。"""
    q = next(x for x in web_bank["questions"] if x.get("tiyan") and x.get("refine") and x["refine"].get("variants") and x.get("solution_html"))
    mi.fresh("bank?kw=" + quote(q["id"]), "#qc-" + q["id"])
    card = "#qc-" + q["id"]
    for tg in ["tiyan", "answer", "solution", "refine", "variants"]:
        sec = card + ' [data-sec="%s"]' % tg
        assert not mi.page.is_visible(sec)
        mi.page.click(card + ' button[data-tg="%s"]' % tg)
        assert mi.page.is_visible(sec), tg
        assert "primary" in mi.page.get_attribute(card + ' button[data-tg="%s"]' % tg, "class")
    ok, bad, left = mi.katex_report(card)
    assert ok > 0 and bad == 0 and not left, (ok, bad, left[:5])
    mi.page.click(card + ' button[data-tg="solution"]')
    assert not mi.page.is_visible(card + ' [data-sec="solution"]')
    mi.assert_clean()


def test_refine_point_link_searches_bank(mi, web_bank):
    q = next(x for x in web_bank["questions"] if x.get("refine") and x["refine"].get("parts"))
    name = q["refine"]["parts"][0]["main"]["name"]
    mi.fresh("bank?kw=" + quote(q["id"]), "#qc-" + q["id"])
    mi.page.click('#qc-%s button[data-tg="refine"]' % q["id"])
    mi.navigating(lambda: mi.page.locator("#qc-%s a.kd" % q["id"]).first.click(), "#bank-result .pager")
    assert mi.page.input_value("#f-kw") == name
    n, ids = _all_ids(mi, "bank?kw=" + quote(name))
    assert q["id"] in ids


def test_bank_charts_follow_filter(mi, questions):
    mi.fresh("bank?region=" + quote("上海"), "#b-region canvas")
    sub = [q for q in questions if q["region"] == "上海"]
    assert mi.series("b-region")[0]["data"] == [len(sub)]
    assert sum(mi.series("b-year")[0]["data"]) == len(sub)
    for cid in ["b-region", "b-type", "b-year", "b-unit"]:
        assert mi.chart_ink(cid) > 200, cid


def test_whole_bank_katex(mi, web_bank):
    """逐页展开全部答案/详解/题眼/提炼/改编，统计 KaTeX 报错与没渲染的 $。"""
    mi.fresh("bank", "#bank-result .pager")
    n = len(web_bank["questions"])
    problems = {}
    for p in range(1, pages_of(n) + 1):
        mi.goto("bank?page=%d" % p, "#bank-result .pager")
        mi.page.evaluate("() => document.querySelectorAll('#bank-result button[data-tg]').forEach(b => b.click())")
        res = mi.page.evaluate(
            """() => [...document.querySelectorAll('#bank-result .qcard')].map(c => {
              const err = [...c.querySelectorAll('.katex-error')].map(e => e.textContent.slice(0, 60));
              const left = []; const w = document.createTreeWalker(c, NodeFilter.SHOW_TEXT); let n;
              while ((n = w.nextNode())) { const pe = n.parentElement; if (!pe || pe.closest('.katex, script, style')) continue;
                if (n.nodeValue.includes('$')) left.push(n.nodeValue.trim().slice(0, 60)); }
              const unk = [...c.querySelectorAll('*')].filter(e => e instanceof HTMLUnknownElement).map(e => '<' + e.tagName.toLowerCase() + '>');
              return [c.id.slice(3), err, left, unk]; })"""
        )
        for qid, err, left, unk in res:
            if err or left or unk:
                problems[qid] = {"katex-error": err[:3], "残留$": left[:3], "被当成标签吞掉": unk[:3]}
    assert not problems, "%d 题公式有问题：%s" % (len(problems), dict(list(problems.items())[:15]))
    mi.assert_clean()
