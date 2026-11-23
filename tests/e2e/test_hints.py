"""提示阶梯：页面上逐级展开的提示不重复前面的原文；级数与数据一致；没有材料的题不冒充三级。"""
import re

from conftest import plain_text


def _norm(h):
    return re.sub(r"\s+", "", plain_text(h).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))


def _page_levels(mi, sid, qid):
    mi.fresh("practice/%s?q=%s" % (sid, qid), "#pr-q .qid")
    mi.page.evaluate("localStorage.clear()")
    mi.fresh("practice/%s?q=%s" % (sid, qid), "#pr-q .qid")
    m = re.match(r"提示（0/(\d+)）", mi.page.inner_text("#pr-hint"))
    n = int(m.group(1))
    for _ in range(n):
        mi.page.click("#pr-hint")
    return [_norm(re.sub(r"^\s*提示\s*\d+", "", t)) for t in mi.page.locator("#pr-hints .hint-box").all_inner_texts()]


def test_hint_levels_do_not_repeat(mi, web_class, web_bank):
    """任一级提示的正文不得整段出现在另一级里（旧版最后一级把题眼原文再贴一遍）。先查全部数据，再在页面上看带题眼的一题。"""
    Q = {q["id"]: q for q in web_bank["questions"]}
    rep = []
    pick = None
    for s in web_class["students"]:
        for g in web_class["profiles"][s["id"]]["practice"]["groups"]:
            for it in g["items"]:
                lv = [_norm(h) for h in it["hints"]]
                for i, a in enumerate(lv):
                    for j, b in enumerate(lv):
                        if i != j and len(a) >= 8 and a in b:
                            rep.append((s["id"], it["qid"], i + 1, j + 1))
                if pick is None and Q[it["qid"]].get("tiyan"):
                    pick = (s["id"], it["qid"], it)
    assert not rep, "%d 处提示重复前一级原文，例如 %s" % (len(rep), rep[:5])
    assert pick, "推荐题里没有带题眼的题"
    sid, qid, it = pick
    shown = _page_levels(mi, sid, qid)
    assert len(shown) == len(it["hints"]), (len(shown), len(it["hints"]))
    for i, a in enumerate(shown):
        for j, b in enumerate(shown):
            assert i == j or len(a) < 8 or a not in b, "页面第 %d 级提示的原文又出现在第 %d 级" % (i + 1, j + 1)
    mi.assert_clean()


def test_hint_levels_are_real(web_class):
    """三级提示各有内容：不是同一句通用话，也不是「无」。"""
    bad = []
    for s in web_class["students"]:
        for g in web_class["profiles"][s["id"]]["practice"]["groups"]:
            for it in g["items"]:
                lv = [_norm(h) for h in it["hints"]]
                if len(lv) > 1 and (len(set(lv)) < len(lv) or any(re.fullmatch(r"[^：]*：?无。?", x) for x in lv)):
                    bad.append((s["id"], it["qid"], lv))
    assert not bad, bad[:5]
