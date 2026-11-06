"""填空题答案的数值化：把答案 HTML 转成各空的实数值，供网页自动判分。

原则是宁可漏判、不可误判：只要有一空不是能确定的单个实数（区间、集合、方程、
含字母、多个答案并列、带文字单位等），整题返回 None，网页退回自评流程。

支持的写法：整数、小数、\\frac/\\dfrac/\\tfrac（含 \\dfrac13、\\dfrac7{15} 这类省略括号的写法）、
\\sqrt{}、\\sqrt[n]{}、\\pi、正负号与加减乘除、乘方 ^{}、隐式乘法（2\\sqrt3、24\\pi）、
末尾的 \\%（按百分数折算）与 ^\\circ（角度制，数值按度计）。
多空用 ；/;/，/、/(1)(2)/①② 或多个 key 标签分隔。
"""
from __future__ import annotations

import html
import math
import re

__all__ = ["numeric_answer", "latex_value", "count_blanks"]


class _Reject(Exception):
    pass


KEY_RE = re.compile(r'<span class="key">(.*?)</span>', re.S)
TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
# 答案后的等价写法说明，如「（即 $5^{\frac14}$）」「（也可写 …）」；只认全角括号
REMARK_RE = re.compile(r"（\s*(?:即|亦即|或写成|或写作|也可写成|也可写作|也可写|亦可写成|亦可写|可写成|化简为|化简得)(.*?)）", re.S)
MATH_RE = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)", re.S)
BOUNDARY = "\x00"
# 题干中的填空横线
BLANK_RE = re.compile(r"_{2,}|＿{2,}|\\underline\{\s*\\q?quad\s*\}")


def count_blanks(stem_html: str) -> int:
    """数题干里的填空横线（不计图片与 SVG 内的内容）。"""
    s = re.sub(r"<svg.*?</svg>|<img[^>]*>", "", stem_html or "", flags=re.S)
    return len(BLANK_RE.findall(s))


# ---------------- LaTeX 数值求值 ----------------

_SPACING = {",", ";", "!", " ", ":", "quad", "qquad"}
_ALLOWED_CMDS = {"frac", "sqrt", "pi"}


def _tokenize(src: str) -> list[tuple[str, str, bool]]:
    """切成 (类别, 文本, 前面是否有空白) 三元组。类别：d 数字字符 / . / op / cmd / sp。"""
    toks: list[tuple[str, str, bool]] = []
    i, n, space = 0, len(src), False
    while i < n:
        c = src[i]
        if c.isspace():
            space = True
            i += 1
            continue
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", src[i:])
            if not m:
                raise _Reject("孤立反斜杠")
            name = m.group(1)
            i += len(m.group(0))
            if name in ("dfrac", "tfrac"):
                name = "frac"
            if name in ("left", "right"):
                # \left( \right) 只允许圆括号
                if i < n and src[i] in "()":
                    toks.append(("op", src[i], space))
                    i += 1
                    space = False
                    continue
                raise _Reject("非圆括号的 \\left/\\right")
            if name in ("cdot", "times"):
                toks.append(("op", "*", space))
            elif name == "div":
                toks.append(("op", "/", space))
            elif name in _SPACING:
                toks.append(("sp", " ", space))
            elif name in _ALLOWED_CMDS:
                toks.append(("cmd", name, space))
            else:
                raise _Reject(f"不支持的命令 \\{name}")
            space = False
            continue
        if c.isdigit():
            toks.append(("d", c, space))
        elif c == ".":
            toks.append((".", c, space))
        elif c in "+-*/^(){}[]":
            toks.append(("op", c, space))
        elif c == "~":
            toks.append(("sp", " ", space))
        else:
            raise _Reject(f"不支持的字符 {c!r}")
        space = False
        i += 1
    return toks


class _Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self, kind=None, text=None):
        tok = self.peek()
        if tok is None or (kind and tok[0] != kind) or (text and tok[1] != text):
            raise _Reject(f"期望 {kind or ''}{text or ''}，得到 {tok}")
        self.i += 1
        return tok

    def is_op(self, ch):
        tok = self.peek()
        return tok is not None and tok[0] == "op" and tok[1] == ch

    def skip_sp(self):
        while self.peek() is not None and self.peek()[0] == "sp":
            self.i += 1

    def parse(self):
        v = self.expr()
        self.skip_sp()
        if self.peek() is not None:
            raise _Reject(f"多余内容 {self.peek()}")
        return v

    def expr(self):
        self.skip_sp()
        sign = 1.0
        if self.is_op("-") or self.is_op("+"):
            sign = -1.0 if self.take()[1] == "-" else 1.0
        v = sign * self.term()
        while True:
            self.skip_sp()
            if self.is_op("+"):
                self.take()
                v += self.term()
            elif self.is_op("-"):
                self.take()
                v -= self.term()
            else:
                return v

    def term(self):
        v = self.factor()
        divided = False
        while True:
            # 空白命令后不允许隐式乘法（如 "2\,3"）
            had_sp = self.peek() is not None and self.peek()[0] == "sp"
            self.skip_sp()
            tok = self.peek()
            if tok is None:
                return v
            if tok[0] == "op" and tok[1] in "*/":
                self.take()
                r = self.factor()
                if tok[1] == "*":
                    v *= r
                else:
                    if r == 0:
                        raise _Reject("除以零")
                    v /= r
                    divided = True
            elif not had_sp and ((tok[0] == "cmd") or (tok[0] == "op" and tok[1] in "({")):
                if divided:
                    raise _Reject("除号后隐式乘法有歧义（如 2/3\\pi）")
                if tok == ("cmd", "frac", tok[2]):
                    raise _Reject("数后紧跟分数（可能是带分数）")
                v *= self.factor()  # 隐式乘法：2\sqrt3、24\pi、2(…)
            elif tok[0] in ("d", "."):
                raise _Reject("两个数直接相连")
            else:
                return v

    def factor(self):
        self.skip_sp()
        base = self.atom()
        if self.is_op("^"):
            self.take()
            ex = self.arg()
            if abs(ex) > 64 or (base == 0 and ex <= 0):
                raise _Reject("指数不合理")
            if base < 0 and ex != int(ex):
                raise _Reject("负数的分数次幂")
            base = base ** ex
        return base

    def number(self):
        s = ""
        while self.peek() is not None and self.peek()[0] == "d" and not (s and self.peek()[2]):
            s += self.take()[1]
        if self.peek() is not None and self.peek()[0] == "." and not self.peek()[2]:
            self.take()
            frac = ""
            while self.peek() is not None and self.peek()[0] == "d" and not self.peek()[2]:
                frac += self.take()[1]
            if not frac:
                raise _Reject("小数点后无数字")
            s = (s or "0") + "." + frac
        if not s:
            raise _Reject("缺数字")
        return float(s)

    def atom(self):
        tok = self.peek()
        if tok is None:
            raise _Reject("表达式不完整")
        if tok[0] in ("d", "."):
            return self.number()
        if tok[0] == "cmd":
            self.take()
            if tok[1] == "pi":
                return math.pi
            if tok[1] == "frac":
                a = self.arg()
                b = self.arg()
                if b == 0:
                    raise _Reject("分母为零")
                return a / b
            if tok[1] == "sqrt":
                k = 2.0
                self.skip_sp()
                if self.is_op("["):
                    self.take()
                    k = self.expr()
                    self.take("op", "]")
                    if k != int(k) or k < 2:
                        raise _Reject("根指数不是 ≥2 的整数")
                x = self.arg()
                if x < 0:
                    raise _Reject("负数开方")
                return x ** (1.0 / k)
        if tok[0] == "op" and tok[1] in "({":
            close = ")" if tok[1] == "(" else "}"
            self.take()
            v = self.expr()
            self.skip_sp()
            self.take("op", close)
            return v
        raise _Reject(f"无法识别 {tok}")

    def arg(self):
        """宏参数：{…} 整组，或恰好一个记号（一个数字或 \\pi）。"""
        self.skip_sp()
        tok = self.peek()
        if tok is None:
            raise _Reject("缺参数")
        if tok[0] == "op" and tok[1] == "{":
            self.take()
            v = self.expr()
            self.skip_sp()
            self.take("op", "}")
            return v
        if tok[0] == "d":
            self.take()
            return float(tok[1])
        if tok[0] == "cmd" and tok[1] == "pi":
            self.take()
            return math.pi
        raise _Reject(f"不支持的参数 {tok}")


def latex_value(src: str) -> float:
    """把一段数学公式（不含 $）求成实数；不是单个确定实数时抛 ValueError。"""
    try:
        return _latex_value(src)
    except (_Reject, OverflowError, ZeroDivisionError, TypeError) as e:
        raise ValueError(str(e)) from None


def _latex_value(src: str) -> float:
    s = src.strip()
    percent = degree = False
    m = re.search(r"(?:\^\s*\{\s*\\circ\s*\}|\^\s*\\circ|°)\s*$", s)
    if m:
        degree, s = True, s[: m.start()]
    m = re.search(r"\\%\s*$", s)
    if m and not degree:
        percent, s = True, s[: m.start()]
    if not s.strip() or "\\circ" in s or "°" in s or "%" in s:
        raise _Reject("单位位置不对")
    v = _Parser(_tokenize(s)).parse()
    if isinstance(v, complex) or not math.isfinite(v):
        raise _Reject("不是有限实数")
    return v / 100.0 if percent else v


# ---------------- 答案 HTML 拆空 ----------------

_TEXT_TOKEN = re.compile(
    r"(?P<ws>\s+)"
    r"|(?P<sep>[；;，,、]|" + BOUNDARY + r")"
    r"|(?P<label>[（(]\s*\d{1,2}\s*[）)]\s*[:：]?|[①②③④⑤⑥⑦⑧⑨⑩]\s*[:：]?|第\s*[一二三四五六1-6]\s*空\s*[:：]?)"
    r"|(?P<end>[。．.])"
)


def _plain(s: str) -> str:
    return html.unescape(TAG_RE.sub("", s)).replace("\xa0", " ")


def numeric_answer(answer_html, blanks: int | None = None) -> list[float] | None:
    """答案 HTML → 各空数值列表；任一空不是确定实数则返回 None。

    blanks：题干里的空数（可选）。给出且答案多于一空时，空数必须一致；
    题干有多个空而答案只解析出一个值时也拒绝。
    """
    if not isinstance(answer_html, str) or not answer_html.strip():
        return None
    try:
        vals = _numeric(answer_html)
    except (_Reject, OverflowError, ZeroDivisionError, TypeError):
        return None
    if not vals:
        return None
    if blanks is not None and (len(vals) > 1 or blanks > 1) and blanks != len(vals):
        return None
    return vals


def _numeric(src: str) -> list[float]:
    if src.count('<span class="key"') != len(KEY_RE.findall(src)):
        raise _Reject("key 标签不配对")
    for inner in KEY_RE.findall(src):
        if "<span" in inner:
            raise _Reject("key 内嵌套 span")
    text = KEY_RE.sub(lambda m: BOUNDARY + m.group(1) + BOUNDARY, src)
    text = _plain(text)

    remarks = [m.group(1) for m in REMARK_RE.finditer(text)]
    text = REMARK_RE.sub("", text)

    vals: list[float] = []
    labels = 0
    open_blank = True  # 当前位置可以开始一个新空
    pos = 0
    for m in MATH_RE.finditer(text):
        state = {"open": open_blank}
        labels += _scan_text(text[pos: m.start()], state)
        open_blank = state["open"]
        if not open_blank:
            raise _Reject("两段公式之间没有分隔")
        vals.append(_latex_value(next(g for g in m.groups() if g is not None)))
        open_blank = False
        pos = m.end()
    tail = text[pos:]
    if "$" in tail:
        raise _Reject("美元符号不配对")
    labels += _scan_text(tail, {"open": open_blank})

    if labels and labels != len(vals):
        raise _Reject("序号数与空数不一致")
    if remarks:
        if len(vals) != 1:
            raise _Reject("多空答案带说明")
        for r in remarks:
            ms = list(MATH_RE.finditer(r))
            if len(ms) != 1:
                continue
            try:
                alt = _latex_value(next(g for g in ms[0].groups() if g is not None))
            except (_Reject, OverflowError, ZeroDivisionError, TypeError):
                continue  # 等价写法超出本解析器能力，不影响主答案
            if not math.isclose(alt, vals[0], rel_tol=1e-9, abs_tol=1e-12):
                raise _Reject("说明中的等价写法与主答案数值不符")
    return vals


def _scan_text(seg: str, state: dict) -> int:
    """检查公式之间的文字只含空白、分隔符、序号与句号；返回序号个数。"""
    i, labels = 0, 0
    while i < len(seg):
        m = _TEXT_TOKEN.match(seg, i)
        if not m:
            raise _Reject(f"多余文字 {seg[i:i + 10]!r}")
        if m.lastgroup in ("sep", "label"):
            state["open"] = True
            labels += m.lastgroup == "label"
        i = m.end()
    return labels
