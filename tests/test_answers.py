"""填空题数值答案解析：常见写法要算对，含糊写法必须拒绝。"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mathinsight.answers import count_blanks, latex_value, numeric_answer  # noqa: E402


def key(tex):
    return '<span class="key">' + tex + "</span>"


# (答案 HTML, sympy 表达式字符串列表)
ACCEPT = [
    (key(r"$6$"), ["6"]),
    (key(r"$-2$"), ["-2"]),
    (key(r"$0$"), ["0"]),
    (key(r"$0.85$"), ["85/100"]),
    (key(r"$6.3$"), ["63/10"]),
    (key(r"$\dfrac13$"), ["1/3"]),
    (key(r"$\dfrac7{15}$"), ["7/15"]),
    (key(r"$-\dfrac34$"), ["-3/4"]),
    (key(r"$\dfrac{61}{25}$"), ["61/25"]),
    (key(r"$\tfrac{1}{2}$"), ["1/2"]),
    (key(r"$\frac{18}{5}$"), ["18/5"]),
    (key(r"$\sqrt3$"), ["sqrt(3)"]),
    (key(r"$\sqrt{17}$"), ["sqrt(17)"]),
    (key(r"$2\sqrt2$"), ["2*sqrt(2)"]),
    (key(r"$\dfrac{\sqrt6}4$"), ["sqrt(6)/4"]),
    (key(r"$\dfrac{5\sqrt3}{4}$"), ["5*sqrt(3)/4"]),
    (key(r"$\dfrac{\sqrt{66}}{6}$"), ["sqrt(66)/6"]),
    (key(r"$1-\sqrt2$"), ["1-sqrt(2)"]),
    (key(r"$\pi$"), ["pi"]),
    (key(r"$24\pi$"), ["24*pi"]),
    (key(r"$\dfrac{3\pi}{2}$"), ["3*pi/2"]),
    (key(r"$\dfrac\pi2$"), ["pi/2"]),
    (key(r"$\left(\dfrac12\right)^2$"), ["1/4"]),
    (key(r"$2^{10}$"), ["1024"]),
    (key(r"$3\times 4$"), ["12"]),
    (key(r"$\sqrt[4]5$") + r"（即 $5^{\frac14}$）", ["5**(1/4)"]),
    (key(r"$\sqrt[3]{\dfrac32}$（即 $\dfrac{\sqrt[3]{12}}{2}$）"), ["(3/2)**(1/3)"]),
    (key(r"$7.8^\circ$"), ["78/10"]),
    (key(r"$12.58^{\circ}$"), ["1258/100"]),
    (key(r"$20\%$"), ["1/5"]),
    ("<p>$5\\sqrt5$。</p>", ["5*sqrt(5)"]),
    ("<p>$\\pi/6$。</p>", ["pi/6"]),
    (r"$2$；$-1$", ["2", "-1"]),
    (key(r"$2$；$-1$"), ["2", "-1"]),
    (r"(1) $3$；(2) $\dfrac12$", ["3", "1/2"]),
    (r"①$3$ ②$\sqrt2$", ["3", "sqrt(2)"]),
    (key(r"$3$") + "，" + key(r"$-\dfrac12$"), ["3", "-1/2"]),
    (key(r"$4$") + key(r"$5$"), ["4", "5"]),
]

REJECT = [
    None, "", "<p></p>",
    key(r"$(1,3)$"),
    key(r"$\{2,4\}$"),
    key(r"$[1,+\infty)$"),
    key(r"$\left(0,\dfrac13\right)$"),
    key(r"$(-\infty,0)\cup(0,1)$"),
    "<p>$a\\in[1,+\\infty)$。</p>",
    key(r"$3+4\mathrm i$"),
    key(r"$2-2i$"),
    key(r"$\ln2$"),
    key(r"$\log_2 3$"),
    key(r"$\arccos\dfrac{40}{41}$") + r"（也可写 $\arctan\dfrac{9}{40}$）",
    key(r"$x+y-1=0$"),
    key(r"$f^{-1}(x)=x^{\frac13}\ (x\in\mathbf R)$"),
    key(r"$\theta=\dfrac{3\pi}{2}$；$f\left(\dfrac{2\pi}{3}\right)=1$"),
    key(r"$2$ 或 $-2$"),
    key(r"$2$") + " 或 $-2$",
    key(r"$\pm2$"),
    key(r"$\pm\sqrt3$"),
    "<p>充要条件。</p>",
    "<p>$51$ 万人。</p>",
    "<p>$5\\sqrt{17}$ cm。</p>",
    key(r"$2$（舍去 $-2$）"),
    key(r"$2$") + "（即 $3$）",          # 等价写法与主答案矛盾
    key(r"$2,3$"),
    key(r"$2$ $3$"),
    key(r"$1\ 2$"),
    key(r"$1 2$"),
    key(r"$2/3\pi$"),                    # (2/3)π 还是 2/(3π)，有歧义
    key(r"$1/2\sqrt3$"),
    key(r"$2\dfrac13$"),                  # 带分数，含义不确定
    key(r"$\sqrt12$"),
    key(r"$\sqrt{-1}$"),
    key(r"$\dfrac10$"),
    key(r"$(-8)^{\frac13}$"),
    key(r"$2^{1000}$"),
    key(r"$e$"),
    key(r"$\dfrac12x$"),
    key(r"$a$"),
    key(r"$\infty$"),
    key(r"$3"),
    key(r"$2\%^\circ$"),
    r"(1) $3$；(2) $4$；(3)",
    '<span class="key">$2$<span>x</span></span>',
]


@pytest.mark.parametrize("src,expected", ACCEPT)
def test_accept(src, expected):
    sympy = pytest.importorskip("sympy")
    got = numeric_answer(src)
    assert got is not None, src
    want = [float(sympy.sympify(e)) for e in expected]
    assert len(got) == len(want)
    for g, w in zip(got, want):
        assert math.isclose(g, w, rel_tol=1e-12, abs_tol=1e-12), (src, g, w)


@pytest.mark.parametrize("src", REJECT)
def test_reject(src):
    assert numeric_answer(src) is None, src


def test_blank_count_check():
    two = r"$2$；$-1$"
    assert numeric_answer(two, blanks=2) == [2.0, -1.0]
    assert numeric_answer(two, blanks=1) is None    # 一空却给了两个值：可能是「或」
    assert numeric_answer(two, blanks=0) is None
    assert numeric_answer(key("$5$"), blanks=0) == [5.0]   # 改写成「求…」的题干没有横线
    assert numeric_answer(key("$5$"), blanks=1) == [5.0]
    assert numeric_answer(key("$5$"), blanks=2) is None


def test_count_blanks():
    assert count_blanks("则 $\\theta=$______，$f(1)=$______．") == 2
    assert count_blanks("<p>求 $n$。</p>") == 0
    assert count_blanks('<svg><text>____</text></svg>则 $a=$____') == 1


def test_latex_value_raises():
    assert latex_value(r"\dfrac{\sqrt3}{2}") == pytest.approx(math.sqrt(3) / 2)
    with pytest.raises(ValueError):
        latex_value(r"\sin 1")


def test_bank_answer_num_consistent():
    """导入后的题库：answer_num 只出现在填空题上，且与解析结果一致。"""
    from mathinsight.bank import QuestionBank
    bank = QuestionBank.load()
    n = 0
    for q in bank.questions:
        if "answer_num" not in q:
            continue
        n += 1
        assert q["type"] == "填空"
        assert q["answer_num"] == numeric_answer(q["answer_html"], blanks=count_blanks(q["stem_html"]))
    assert n > 0
