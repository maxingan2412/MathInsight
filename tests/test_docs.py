"""README 里的题库数字必须与 bank/papers.json 一致，题库扩充后漏改说明会在这里报错。"""
import json
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
PAPERS = json.loads((ROOT / "bank" / "papers.json").read_text(encoding="utf-8"))
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _group(p):
    if p["kind"] != "高考":
        return "模拟考试"
    return {"上海": "上海高考", "全国": "全国高考", "浙江": "浙江高考"}.get(p["region"], p["region"] + "高考")


def test_badge_matches_bank():
    m = re.search(r"badge/题库-(\d+) 套 · (\d+) 题", unquote(README))
    assert m, "README 顶部缺题库徽章"
    assert (int(m.group(1)), int(m.group(2))) == (len(PAPERS), sum(p["count"] for p in PAPERS))


def test_table_matches_bank():
    want = {}
    for p in PAPERS:
        g = want.setdefault(_group(p), [0, 0])
        g[0] += 1
        g[1] += p["count"]
    want["**合计**"] = [len(PAPERS), sum(p["count"] for p in PAPERS)]
    got = {}
    for line in README.splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) == 4 and c[2].strip("*").isdigit() and c[3].strip("*").isdigit():
            got[c[0]] = [int(c[2].strip("*")), int(c[3].strip("*"))]
    assert got == want


def test_table_years_cover_bank():
    """数据现状表每一行要写到该类里每份高考卷的年份。"""
    for line in README.splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) != 4 or not c[0].endswith("高考"):
            continue
        years = set()
        for a, b in re.findall(r"(\d{4})(?:–(\d{4}))?", c[1]):
            years |= set(range(int(a), int(b or a) + 1))
        need = {p["year"] for p in PAPERS if _group(p) == c[0]}
        assert need <= years, (c[0], sorted(need - years))
