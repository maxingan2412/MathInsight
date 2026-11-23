"""学生练习：提交前不露答案、提示阶梯逐级展开、单选/多选/填空自动判分、解答题自评、记录持久化、学习监督、文字包。"""
import re
from urllib.parse import quote

import pytest

from conftest import answer_letters, plain_text


def _items(C, B, sid):
    Q = {q["id"]: q for q in B["questions"]}
    out = []
    for g in C["profiles"][sid]["practice"]["groups"]:
        for it in g["items"]:
            if it["qid"] in Q:
                out.append(dict(it, unit=g["unit"], q=Q[it["qid"]]))
    return out


def _find(C, B, pred):
    for s in C["students"]:
        for i, it in enumerate(_items(C, B, s["id"])):
            if pred(it):
                return s["id"], i, it
    pytest.skip("数据里没有符合条件的推荐题")


def _open(mi, sid, qid):
    mi.fresh("practice/%s?q=%s" % (sid, qid), "#pr-q .qid")
    mi.page.evaluate("localStorage.clear()")
    mi.fresh("practice/%s?q=%s" % (sid, qid), "#pr-q .qid")
    assert mi.page.inner_text("#pr-q .qid") == qid


def _levels(it):
    # 页面显示的提示级数就是 hints（题眼的卡点、打通已折进其中，不再追加一遍原文）
    return list(it.get("hints") or [])


def _no_answer_shown(mi, q):
    t = mi.page.inner_text("#pr-q")
    assert "参考答案" not in t and mi.page.locator("#pr-sol-box").count() == 0
    assert mi.page.locator("#pr-q .result-box.right, #pr-q .result-box.wrong, #pr-q .result-box.partial").count() == 0


def test_nav_and_first_unfinished(mi, web_class, web_bank):
    C, B = web_class, web_bank
    sid = C["students"][1]["id"]
    items = _items(C, B, sid)
    mi.fresh("practice/" + sid, "#pr-nav button")
    mi.page.evaluate("localStorage.clear()")
    mi.fresh("practice/" + sid, "#pr-nav button")
    assert mi.page.locator("#pr-nav button").count() == len(items)
    assert mi.page.inner_text("#pr-q .qid") == items[0]["qid"]
    assert "第 1 / %d 题" % len(items) in mi.page.inner_text("#pr-q .qcard-head")
    assert "0 / %d 题" % len(items) in mi.page.inner_text("#pr-monitor")
    # 下一题 / 上一题 / 点题号
    assert mi.page.is_disabled("#pr-prev")
    mi.page.click("#pr-next")
    assert mi.page.inner_text("#pr-q .qid") == items[1]["qid"]
    mi.page.click("#pr-prev")
    assert mi.page.inner_text("#pr-q .qid") == items[0]["qid"]
    mi.page.click('#pr-nav button[data-i="%d"]' % (len(items) - 1))
    assert mi.page.inner_text("#pr-q .qid") == items[-1]["qid"]
    assert mi.page.is_disabled("#pr-next")
    # 每题显示的预计得分率与角色来自数据
    head = mi.page.inner_text("#pr-q .qcard-head")
    assert items[-1]["role"] in head and ("预计得分率 %d%%" % round(items[-1]["pred"] * 100)) in head
    ok, bad, left = mi.katex_report("#pr-q")
    assert bad == 0 and not left, left[:5]
    mi.assert_clean()


def test_hint_ladder(mi, web_class, web_bank):
    sid, i, it = _find(web_class, web_bank, lambda x: len(_levels(x)) >= 3 and x["q"]["type"] in ("单选", "多选"))
    _open(mi, sid, it["qid"])
    lv = _levels(it)
    _no_answer_shown(mi, it["q"])
    for k in range(len(lv)):
        assert mi.page.inner_text("#pr-hint") == "提示（%d/%d）" % (k, len(lv))
        mi.page.click("#pr-hint")
        boxes = mi.page.locator("#pr-hints .hint-box")
        assert boxes.count() == k + 1
        assert "提示 %d" % (k + 1) in boxes.nth(k).inner_text()
        want = plain_text(lv[k]).split("$")[0][:10]
        assert re.sub(r"\s", "", want) in re.sub(r"\s", "", boxes.nth(k).inner_text()), (k, want)
        _no_answer_shown(mi, it["q"])
    assert mi.page.is_disabled("#pr-hint")
    ok, bad, left = mi.katex_report("#pr-hints")
    assert bad == 0 and not left
    # 提交后记录用了几级提示
    letters = answer_letters(it["q"])
    for L in letters:
        mi.page.click('#pr-q button[data-opt="%s"]' % L)
    mi.page.click("#pr-submit")
    assert "用了 %d 级提示" % len(lv) in mi.page.inner_text("#pr-q .result-box")
    assert re.search(r"独立完成\s*0 / 1 题", mi.page.inner_text("#pr-monitor"))
    mi.assert_clean()


@pytest.mark.parametrize("correct", [True, False], ids=["right", "wrong"])
def test_single_choice_autograde(mi, web_class, web_bank, correct):
    sid, i, it = _find(web_class, web_bank, lambda x: x["q"]["type"] == "单选" and len(answer_letters(x["q"])) == 1)
    _open(mi, sid, it["qid"])
    ans = answer_letters(it["q"])
    pick = ans if correct else next(L for L in "ABCD" if L != ans)
    mi.page.click('#pr-q button[data-opt="%s"]' % pick)
    assert "on" in mi.page.get_attribute('#pr-q button[data-opt="%s"]' % pick, "class")
    _no_answer_shown(mi, it["q"])
    mi.page.click("#pr-submit")
    box = mi.page.inner_text("#pr-q .result-box")
    assert ("全对" if correct else "不会 / 错误") in box
    assert "你的选择 %s，正确答案 %s" % (pick, ans) in box
    assert "hit" in mi.page.get_attribute('#pr-q button[data-opt="%s"]' % ans, "class")
    assert "参考答案" in mi.page.inner_text("#pr-q")
    assert ("right" if correct else "wrong") in mi.page.get_attribute('#pr-nav button[data-i="%d"]' % i, "class")
    assert "1 / %d 题" % len(_items(web_class, web_bank, sid)) in mi.page.inner_text("#pr-monitor")
    acc = "100%" if correct else "0%"
    assert re.search(r"正确率\s*%s" % acc, mi.page.inner_text("#pr-monitor"))
    # 重新加载后记录仍在（localStorage）
    mi.fresh("practice/%s?q=%s" % (sid, it["qid"]), "#pr-q .result-box")
    assert ("全对" if correct else "不会 / 错误") in mi.page.inner_text("#pr-q .result-box")
    assert mi.page.locator("#pr-submit").count() == 0
    mi.assert_clean()


def test_multi_choice_partial_and_wrong(mi, web_class, web_bank):
    sid, i, it = _find(web_class, web_bank, lambda x: x["q"]["type"] == "多选" and len(answer_letters(x["q"])) >= 2)
    ans = answer_letters(it["q"])
    _open(mi, sid, it["qid"])
    mi.page.click('#pr-q button[data-opt="%s"]' % ans[0])
    mi.page.click("#pr-submit")
    assert re.search(r"结果：\s*部分正确", mi.page.inner_text("#pr-q .result-box")), mi.page.inner_text("#pr-q .result-box")
    _open(mi, sid, it["qid"])
    wrong = next(L for L in "ABCD" if L not in ans)
    mi.page.click('#pr-q button[data-opt="%s"]' % ans[0])
    mi.page.click('#pr-q button[data-opt="%s"]' % wrong)
    mi.page.click("#pr-submit")
    assert "不会 / 错误" in mi.page.inner_text("#pr-q .result-box")
    _open(mi, sid, it["qid"])
    for L in ans:
        mi.page.click('#pr-q button[data-opt="%s"]' % L)
    mi.page.click('#pr-q button[data-opt="%s"]' % ans[0])  # 再点取消
    mi.page.click('#pr-q button[data-opt="%s"]' % ans[0])
    mi.page.click("#pr-submit")
    assert "全对" in mi.page.inner_text("#pr-q .result-box")
    mi.assert_clean()


def test_submit_without_choice_alerts(mi, web_class, web_bank):
    sid, i, it = _find(web_class, web_bank, lambda x: x["q"]["type"] == "单选")
    _open(mi, sid, it["qid"])
    mi.page.click("#pr-submit")
    mi.page.wait_for_timeout(200)
    assert mi.dialogs and mi.dialogs[-1][0] == "alert"
    assert mi.page.locator("#pr-submit").count() == 1, "未选就提交不应记录"


def test_numeric_fill_autograde(mi, web_class, web_bank):
    sid, i, it = _find(web_class, web_bank, lambda x: x["q"]["type"] == "填空" and x["q"].get("answer_num"))
    q = it["q"]
    _open(mi, sid, it["qid"])
    _no_answer_shown(mi, q)
    # 看不懂的写法：提示，不记录
    mi.page.fill("#pr-num", "abc")
    mi.page.click("#pr-submit")
    assert mi.page.locator("#pr-num-msg").count() == 1
    assert mi.page.locator("#pr-q .result-box.right, #pr-q .result-box.wrong").count() == 0
    # 空数不对
    if len(q["answer_num"]) == 1:
        mi.page.fill("#pr-num", "1,2")
        mi.page.click("#pr-submit")
        assert "只有 1 个空" in mi.page.inner_text("#pr-num-msg")
    # 正确数值（回车提交）
    mi.page.fill("#pr-num", ", ".join(repr(float(v)) for v in q["answer_num"]))
    mi.page.press("#pr-num", "Enter")
    mi.page.wait_for_selector("#pr-q .result-box.right")
    assert "全对" in mi.page.inner_text("#pr-q .result-box")
    mi.assert_clean()


def test_numeric_fill_wrong_value(mi, web_class, web_bank):
    sid, i, it = _find(web_class, web_bank, lambda x: x["q"]["type"] == "填空" and x["q"].get("answer_num") and len(x["q"]["answer_num"]) == 1)
    _open(mi, sid, it["qid"])
    mi.page.fill("#pr-num", repr(float(it["q"]["answer_num"][0]) + 1.5))
    mi.page.click("#pr-submit")
    mi.page.wait_for_selector("#pr-q .result-box.wrong")
    assert "正确答案" in mi.page.inner_text("#pr-q .result-box.wrong")


def test_free_response_self_grade(mi, web_class, web_bank):
    sid, i, it = _find(web_class, web_bank, lambda x: x["q"]["type"] == "解答" and x["q"].get("solution_html"))
    _open(mi, sid, it["qid"])
    _no_answer_shown(mi, it["q"])
    mi.page.fill("#pr-text", "我的步骤：先求导")
    mi.page.click("#pr-submit")
    assert mi.page.locator("#pr-q .result-box.pending").count() == 1
    assert "参考答案" in mi.page.inner_text("#pr-q")
    mi.page.click('#pr-q button[data-grade="partial"]')
    assert re.search(r"结果：\s*部分正确", mi.page.inner_text("#pr-q .result-box"))
    # 详解开合
    mi.page.click("#pr-sol")
    assert mi.page.is_visible("#pr-sol-box") and mi.page.inner_text("#pr-sol") == "收起详解"
    ok, bad, left = mi.katex_report("#pr-q")
    assert ok > 0 and bad == 0 and not left, left[:5]
    mi.page.click("#pr-sol")
    assert not mi.page.is_visible("#pr-sol-box")
    st = mi.page.evaluate("JSON.parse(localStorage.getItem('mi_practice_%s'))" % sid)
    assert st["records"][it["qid"]]["result"] == "partial" and st["records"][it["qid"]]["text"] == "我的步骤：先求导"
    mi.assert_clean()


def test_reset_records_and_goal(mi, web_class, web_bank):
    sid, i, it = _find(web_class, web_bank, lambda x: x["q"]["type"] == "单选")
    _open(mi, sid, it["qid"])
    mi.page.click('#pr-q button[data-opt="%s"]' % answer_letters(it["q"]))
    mi.page.click("#pr-submit")
    assert "今日目标" in mi.page.inner_text("#pr-monitor")
    assert re.search(r"今日目标\s*1 / 5", mi.page.inner_text("#pr-monitor"))
    mi.page.fill("#pr-goal", "1")
    mi.page.dispatch_event("#pr-goal", "change")
    assert re.search(r"今日目标\s*1 / 1", mi.page.inner_text("#pr-monitor"))
    assert mi.page.locator("#pr-monitor .chip.good").count() == 1
    # 取消确认：记录保留
    mi.dialog_accept = False
    mi.page.click("#pr-reset")
    assert mi.page.locator("#pr-q .result-box").count() == 1
    # 确认：记录清空，目标保留
    mi.dialog_accept = True
    mi.page.click("#pr-reset")
    assert mi.dialogs[-1][0] == "confirm"
    assert mi.page.locator("#pr-submit").count() == 1
    assert re.search(r"今日目标\s*0 / 1", mi.page.inner_text("#pr-monitor"))
    st = mi.page.evaluate("JSON.parse(localStorage.getItem('mi_practice_%s'))" % sid)
    assert st["records"] == {} and st["goal"] == 1
    mi.assert_clean()


def test_stuck_pack_has_no_answer_or_identity(mi, web_class, web_bank):
    """「卡住了」文字包：不含答案、详解、姓名、学号、班级名。"""
    C, B = web_class, web_bank
    checked = 0
    for s in C["students"][:4]:
        for it in _items(C, B, s["id"])[:3]:
            q = it["q"]
            _open(mi, s["id"], it["qid"])
            mi.page.click('#pr-q button[data-scene="stuck"]')
            txt = mi.page.input_value("#pr-ai textarea")
            assert C["profiles"][s["id"]]["name"] not in txt
            assert not re.search(r"(?<![A-Za-z0-9-])%s(?![0-9])" % s["id"], txt)
            assert C["meta"]["class"] not in txt
            assert "核对过的答案" not in txt and "参考详解" not in txt
            key = plain_text(q.get("answer_html"))
            if q["type"] == "解答" and len(key) > 15:
                assert key[:15] not in txt, "卡住包泄露了答案"
            checked += 1
    assert checked >= 6
    mi.assert_clean()


def test_after_submit_packs(mi, web_class, web_bank):
    sid, i, it = _find(web_class, web_bank, lambda x: x["q"]["type"] == "单选" and len(answer_letters(x["q"])) == 1)
    _open(mi, sid, it["qid"])
    wrong = next(L for L in "ABCD" if L != answer_letters(it["q"]))
    mi.page.click('#pr-q button[data-opt="%s"]' % wrong)
    mi.page.click("#pr-submit")
    scenes = mi.page.eval_on_selector_all("#pr-q button[data-scene]", "bs => bs.map(b => b.dataset.scene)")
    assert scenes == ["explain", "diagnose", "more"]
    for sc in scenes:
        mi.page.click('#pr-q button[data-scene="%s"]' % sc)
        txt = mi.page.input_value("#pr-ai textarea")
        assert "我的作答：" + wrong in txt
        assert web_class["profiles"][sid]["name"] not in txt
        if sc == "more":
            assert txt.count("#/bank?kw=") == 2
    # 答对的题不出现「找错因」
    _open(mi, sid, it["qid"])
    mi.page.click('#pr-q button[data-opt="%s"]' % answer_letters(it["q"]))
    mi.page.click("#pr-submit")
    assert mi.page.eval_on_selector_all("#pr-q button[data-scene]", "bs => bs.map(b => b.dataset.scene)") == ["explain", "more"]
    mi.assert_clean()


def test_similar_question_links_work(mi, web_class, web_bank):
    sid, i, it = _find(web_class, web_bank, lambda x: x["q"]["type"] == "单选")
    _open(mi, sid, it["qid"])
    mi.page.click('#pr-q button[data-opt="%s"]' % answer_letters(it["q"]))
    mi.page.click("#pr-submit")
    mi.page.click('#pr-q button[data-scene="more"]')
    txt = mi.page.input_value("#pr-ai textarea")
    links = re.findall(r"(https?://\S+#/bank\?kw=\S+)", txt)
    assert len(links) == 2
    for url in links:
        qid = __import__("urllib.parse").parse.unquote(url.split("kw=")[1])
        mi.page.goto(url)
        mi.page.wait_for_selector("#bank-result .pager")
        assert qid in mi.page.eval_on_selector_all("#bank-result .qid", "es => es.map(e => e.textContent)")
