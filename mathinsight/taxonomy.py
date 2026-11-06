"""知识体系：教材小节 → 板块 → 课标主题，以及六大核心素养标签。

板块(unit)是学情分析的主粒度：一份试卷 20 道左右题目，按十四个板块统计既不稀疏也不过粗。
素养权重先由板块给出基线，再按题型和「题眼」关键词微调，最后归一化。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

COMPETENCIES = ["数学抽象", "逻辑推理", "数学建模", "直观想象", "数学运算", "数据分析"]

THEMES = ["预备知识", "函数", "几何与代数", "概率与统计"]

# 板块: (名称, 课标主题, 素养基线权重)
UNITS = {
    "集合与逻辑": ("预备知识", {"数学抽象": .5, "逻辑推理": .3, "数学运算": .2}),
    "不等式": ("预备知识", {"数学运算": .5, "逻辑推理": .3, "数学抽象": .2}),
    "幂指对函数": ("函数", {"数学运算": .5, "直观想象": .3, "数学抽象": .2}),
    "函数概念与性质": ("函数", {"数学抽象": .4, "逻辑推理": .3, "直观想象": .3}),
    "三角": ("函数", {"数学运算": .5, "直观想象": .3, "逻辑推理": .2}),
    "平面向量": ("几何与代数", {"数学运算": .4, "直观想象": .4, "逻辑推理": .2}),
    "复数": ("几何与代数", {"数学运算": .7, "数学抽象": .3}),
    "立体几何": ("几何与代数", {"直观想象": .5, "逻辑推理": .3, "数学运算": .2}),
    "解析几何": ("几何与代数", {"数学运算": .55, "直观想象": .25, "逻辑推理": .2}),
    "数列": ("函数", {"逻辑推理": .4, "数学运算": .4, "数学抽象": .2}),
    "导数": ("函数", {"逻辑推理": .4, "数学运算": .4, "数学抽象": .2}),
    "计数原理": ("概率与统计", {"逻辑推理": .4, "数学建模": .3, "数学运算": .3}),
    "概率": ("概率与统计", {"数学建模": .4, "数据分析": .3, "逻辑推理": .3}),
    "统计": ("概率与统计", {"数据分析": .6, "数学建模": .3, "数学运算": .1}),
}

# (教材, 章号) → 板块
CHAPTER_UNIT = {
    ("必修一", 1): "集合与逻辑", ("必修一", 2): "不等式", ("必修一", 3): "幂指对函数",
    ("必修一", 4): "幂指对函数", ("必修一", 5): "函数概念与性质",
    ("必修二", 6): "三角", ("必修二", 7): "三角", ("必修二", 8): "平面向量", ("必修二", 9): "复数",
    ("必修三", 10): "立体几何", ("必修三", 11): "立体几何", ("必修三", 12): "概率", ("必修三", 13): "统计",
    ("选必一", 1): "解析几何", ("选必一", 2): "解析几何", ("选必一", 3): "立体几何", ("选必一", 4): "数列",
    ("选必二", 5): "导数", ("选必二", 6): "计数原理", ("选必二", 7): "概率", ("选必二", 8): "统计",
}

# 旧教材(2020 年前课程)内容 → 最接近的新课标板块
OLD_CURRICULUM = [("线性规划", "不等式"), ("不等式选讲", "不等式"), ("矩阵", "平面向量"),
                  ("行列式", "平面向量"), ("坐标系与参数方程", "解析几何"), ("极坐标", "解析几何")]

# 题眼/知识细项里的关键词 → 素养加权
KEYWORD_BOOST = [
    (re.compile("翻译|集合语言|条件|定义|抽象|存在|任意|恒成立"), "数学抽象", .15),
    (re.compile("画图|图像|数形|几何|对称|射影|投影|截面|位置"), "直观想象", .15),
    (re.compile("计算|化简|运算|消元|配方|换元|求值"), "数学运算", .10),
    (re.compile("情境|实际|应用|模型|物理|经济|方案"), "数学建模", .20),
    (re.compile("构造|反证|证明|归纳|分类讨论|放缩|必要性|充分"), "逻辑推理", .15),
    (re.compile("频率|样本|回归|数据|统计|分布|期望|方差"), "数据分析", .15),
]


@dataclass
class Section:
    book: str
    sec: str
    name: str
    page: int
    unit: str


class Taxonomy:
    def __init__(self, sections: dict[tuple[str, str], Section]):
        self.sections = sections

    @classmethod
    def load(cls, path: Path | None = None) -> "Taxonomy":
        path = path or DATA / "sections.txt"
        book = None
        out: dict[tuple[str, str], Section] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"【(.+?)】", line)
            if m:
                book = m.group(1)
                line = line[m.end():]
            body = line.split(":", 1)[-1]
            for part in body.split("|"):
                mm = re.match(r"\s*\*?(\d+)\.(\d+)\s+(.+?)\s+p(\d+)\s*$", part)
                if not mm or not book:
                    continue
                ch, sub, name, page = int(mm.group(1)), mm.group(2), mm.group(3), int(mm.group(4))
                sec = f"{ch}.{sub}"
                out[(book, sec)] = Section(book, sec, name, page, CHAPTER_UNIT[(book, ch)])
        return cls(out)

    def unit_of(self, book: str, sec: str, name: str = "") -> str:
        if book == "旧教材" or not sec:
            for kw, u in OLD_CURRICULUM:
                if kw in name:
                    return u
            return "函数概念与性质"
        ch = int(sec.lstrip("*").split(".")[0])
        return CHAPTER_UNIT.get((book, ch), "函数概念与性质")

    def section_name(self, book: str, sec: str) -> str:
        s = self.sections.get((book, sec))
        return s.name if s else ""

    def annotate(self, q: dict) -> dict:
        """为题目补 units / theme / competencies 字段。"""
        units: list[str] = []
        for s in q.get("sections", []):
            s["sec"] = s["sec"].lstrip("*")
            s.setdefault("name", self.section_name(s["book"], s["sec"]))
            u = self.unit_of(s["book"], s["sec"], s.get("name", ""))
            s["unit"] = u
            if u not in units:
                units.append(u)
        if not units:
            units = ["函数概念与性质"]
        q["units"] = units
        q["theme"] = UNITS[units[0]][0]
        w = {c: 0.0 for c in COMPETENCIES}
        for i, u in enumerate(units):
            k = 1.0 if i == 0 else 0.5
            for c, v in UNITS[u][1].items():
                w[c] += k * v
        tot = sum(w.values())
        w = {c: v / tot for c, v in w.items()}
        if q.get("type") == "解答":
            w["逻辑推理"] += .15
        text = " ".join([q.get("tiyan_tag", "")] + q.get("tiyan", []) +
                        [s.get("detail", "") for s in q.get("sections", [])])
        for rx, c, b in KEYWORD_BOOST:
            if rx.search(text):
                w[c] += b
        tot = sum(w.values())
        q["competencies"] = {c: round(v / tot, 3) for c, v in w.items() if v / tot >= 0.02}
        return q
