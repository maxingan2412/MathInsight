"""网页直接插入页面的 HTML 字段：公式里的 < > 必须已转义，不能混进外部组件代码，列表不能套出「1. 1.」。

不依赖浏览器：用标准库 html.parser 解析题库（bank/questions.jsonl、web/data/bank.js）与推荐提示（web/data/class.js）。
"""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HTML_TAGS = {
    "a", "b", "blockquote", "br", "caption", "code", "col", "colgroup", "div", "em", "figcaption", "figure",
    "h2", "h3", "h4", "hr", "i", "img", "li", "ol", "p", "pre", "s", "small", "span", "strong", "sub", "sup",
    "svg", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}
SVG_TAGS = {
    "circle", "clippath", "defs", "desc", "ellipse", "g", "line", "lineargradient", "marker", "mask", "metadata",
    "path", "pattern", "polygon", "polyline", "radialgradient", "rect", "stop", "style", "symbol", "text",
    "textpath", "title", "tspan", "use",
}
REFINE_HTML = ("what", "crux", "pitfalls", "essence", "variants")
MATH = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.S)
SVG_BLOCK = re.compile(r"<svg\b.*?</svg>", re.S | re.I)


def load_js(name):
    s = (ROOT / "web" / "data" / name).read_text(encoding="utf-8").strip()
    return json.loads(s[s.index("=") + 1:].strip().rstrip(";"))


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth, self.bad, self.after_li = 0, [], False
        self.nested = 0

    def handle_starttag(self, tag, attrs):
        if self.depth:
            if tag not in SVG_TAGS and ":" not in tag and tag != "svg":
                self.bad.append("<%s>（svg 内）" % tag)
        elif tag not in HTML_TAGS:
            self.bad.append("<%s>" % tag[:40])
        if tag == "svg":
            self.depth += 1
        if self.after_li and tag in ("ol", "ul"):
            self.nested += 1
        self.after_li = tag == "li"

    def handle_endtag(self, tag):
        if tag == "svg" and self.depth:
            self.depth -= 1
        self.after_li = False

    def handle_data(self, data):
        if data.strip():
            self.after_li = False


def html_fields():
    """(来源, 题号, 字段名, HTML) —— 页面上按 HTML 插入的全部字段。"""
    for src, qs in (("bank", [json.loads(l) for l in (ROOT / "bank" / "questions.jsonl").open(encoding="utf-8") if l.strip()]),
                    ("bank.js", load_js("bank.js")["questions"])):
        for q in qs:
            for k in ("stem_html", "answer_html", "solution_html"):
                yield src, q["id"], k, q.get(k) or ""
            for i, t in enumerate(q.get("tiyan") or []):
                yield src, q["id"], "tiyan[%d]" % i, t
            for k in REFINE_HTML:
                yield src, q["id"], "refine." + k, (q.get("refine") or {}).get(k) or ""
    C = load_js("class.js")
    for sid, p in C["profiles"].items():
        for g in p["practice"]["groups"]:
            for it in g["items"]:
                for i, h in enumerate(it["hints"]):
                    yield "class.js", "%s/%s" % (sid, it["qid"]), "hints[%d]" % i, h


FIELDS = list(html_fields())


def test_only_known_tags():
    """没有被当成标签吞掉的公式片段（如「<x<2$…>」），也没有 <text color=…>、<Chart …> 之类的外部组件代码。"""
    bad = []
    for src, qid, k, h in FIELDS:
        p = _Tags()
        p.feed(h)
        p.close()
        if p.bad:
            bad.append((src, qid, k, p.bad[:3]))
    assert not bad, "%d 个字段里有不认识的标签，例如 %s" % (len(bad), bad[:8])


def test_math_lt_gt_escaped():
    """公式 $…$ / $$…$$ 里的 < > 一律写成 &lt; &gt;。"""
    bad = []
    for src, qid, k, h in FIELDS:
        for m in MATH.finditer(SVG_BLOCK.sub("", h)):
            f = m.group(1) or m.group(2)
            if "<" in f or ">" in f:
                bad.append((src, qid, k, f[:50]))
    assert not bad, "%d 处公式含未转义的 < 或 >，例如 %s" % (len(bad), bad[:8])


def test_no_doubled_numbering():
    """题眼开头不出现「((2))」；列表项不直接套一层列表（页面显示成「1. 1.」）。"""
    bad = []
    for src, qid, k, h in FIELDS:
        if k.startswith("tiyan") and re.match(r"\s*[（(]\s*[（(]", h):
            bad.append((src, qid, k, h[:20]))
        p = _Tags()
        p.feed(h)
        p.close()
        if p.nested:
            bad.append((src, qid, k, "列表套列表 %d 处" % p.nested))
    assert not bad, "%d 处编号重复，例如 %s" % (len(bad), bad[:8])


def test_real_data_checked():
    """防空转：三份数据都被读到了。"""
    srcs = {s for s, *_ in FIELDS}
    assert srcs == {"bank", "bank.js", "class.js"}
    assert sum(1 for s, _, k, _ in FIELDS if s == "bank" and k == "stem_html") == len(
        [l for l in (ROOT / "bank" / "questions.jsonl").open(encoding="utf-8") if l.strip()])
