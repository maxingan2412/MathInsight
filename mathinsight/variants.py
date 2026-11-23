"""大模型生成同构变式题(可选功能，需要配置 API)。

做法
----
0. 标准见 docs/变式题标准.md：保留题眼、更换结构；判据是「原题步骤照抄会失败，但原题的打通仍然用得上」。
1. 注入核心想法：把原题的「题眼」(卡点 + 打通)、本质、改编方向和同考点真题范例写进提示词。
2. 限定知识边界：只允许使用原题所在教材小节及之前学过的工具。
3. 指定难度方向：同级巩固 / 降一级铺垫 / 升一级拔高(可借鉴强基计划题的设问方式)。
4. 先验证再入库：模型须同时给出答案和可执行的 Python 验证代码；verify() 运行通过、
   且照抄检验与题眼检验都通过的变式才写入题库，并标记 source="变式"、parent=原题号，供老师审定。

环境变量
--------
MI_LLM_BASE_URL   兼容 Chat Completions 协议的接口地址（以 /v1 结尾）
MI_LLM_API_KEY    密钥
MI_LLM_MODEL      模型名
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

LEVELS = {"铺垫": "比原题低一个难度层级：不换结构，把卡点那一步拆成引导小问或直接给出",
          "巩固": "与原题难度相同",
          "拔高": "比原题高一个难度层级，可以增加一个参数、改为探究或存在性设问"}
# 相似度三档(标准见 docs/变式题标准.md): 题眼不变, 结构换多少
DISTANCES = {"近": "只换结构里的一个要素（如递增改递减、其中一个对象换成同类的另一个）",
             "中": "换载体（如函数换成数列、代数条件换成几何条件、正问改反问），题眼不变",
             "远": "换到另一个领域或应用情境，题眼不变"}

PROMPT = """你是一位经验丰富的高中数学命题教师。请根据下面的原题，命制 {n} 道「{level}」同构变式题。

【同构变式的标准】
一道题分四层：① 表面（数字、字母、情境）② 结构（研究什么对象、条件怎么给、问什么）③ 题眼（卡在哪一步、靠什么转换想通）④ 知识范围。
同构变式 = 保留第 ③ 层，更换第 ② 层，第 ① 层不限，第 ④ 层不超出原题范围。
判据：原题的解题步骤逐步照抄会失败，但原题题眼里「打通」的那句话仍然用得上。
只换数字不算变式；题眼变了也不算。

【原题】
{stem}

【原题答案】
{answer}

【题眼（必须保留）】
{core}

【本质】
{essence}

【可参考的改编方向】
{directions}

【同考点的真题（看同一考点在真题里换过哪些结构；它们的题眼未必与原题相同，不要照抄）】
{exemplars}

【知识范围】只允许使用以下教材小节及更早学过的知识：{sections}

【要求】
1. 相似度：{distance_desc}。难度：{level_desc}。
2. 先想这个题眼还能装进哪些结构，选定后再命题；每道题写明换了第 ② 层的什么。
3. 每道题给出：题干、答案、简要解析、新题的题眼（「卡点：…。打通：…。」）、以及一段可以独立运行的
   Python 验证代码(用 sympy 或枚举验证答案，验证通过时打印 OK)。
4. 只输出 JSON 数组，每个元素包含字段 stem, answer, solution, tiyan, changed, verify_code。题干中的数学式用 $...$ 包裹。
"""

CHECK_PROMPT = """下面是一道原题及其解答、题眼，和一道据此命制的变式题。请做两项检验，只输出 JSON：
{{"copy_ok": true/false, "tiyan_ok": true/false, "reason": "一句话"}}

1. 照抄检验：把原题解答的每一步只做替换（换数字、换字母）搬到变式题上。若每一步都能照搬并得到正确答案，
   说明太像，copy_ok 为 false；若至少有一步必须重新想，copy_ok 为 true。
2. 题眼检验：独立解变式题，写出它的卡点和打通，与原题题眼比较。卡点与打通是同一个想法则 tiyan_ok 为 true，否则为 false。

【原题】
{stem}

【原题解答】
{solution}

【原题题眼】
{core}

【变式题】
{v_stem}

【变式题答案】
{v_answer}
"""


def strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _core(q: dict) -> str:
    """题眼；没有题眼记录时用提炼里的卡点。"""
    t = html.unescape("\n".join(q.get("tiyan", [])))
    return t or strip_html((q.get("refine") or {}).get("crux")) or "（无题眼记录，请先归纳本题的关键步骤再命题）"


def exemplars(q: dict, bank, k: int = 3) -> list[dict]:
    """题库里与原题主考点相同、题型或教材小节搭配不同的真题, 用作相似度范例。"""
    def names(x):
        return {p.get("main", {}).get("name") for p in (x.get("refine") or {}).get("parts", [])} - {None, ""}
    mine = names(q)
    if not mine or bank is None:
        return []
    cands = [x for x in bank.questions if x["id"] != q["id"] and x["paper"] != q["paper"] and names(x) & mine]
    cands.sort(key=lambda x: (x["type"] == q["type"], -len(names(x) & mine), x["id"]))   # 题型不同的排前
    return cands[:k]


def build_prompt(q: dict, level: str = "巩固", n: int = 2, *, distance: str = "中", bank=None) -> str:
    sections = "、".join(f'{s["book"]} {s["sec"]} {s.get("name", "")}' for s in q["sections"]) or "高中数学"
    rf = q.get("refine") or {}
    ex = "\n\n".join(f'（{x["id"]}）{strip_html(x["stem_html"])}' for x in exemplars(q, bank)) or "（题库中暂无）"
    return PROMPT.format(n=n, level=level, stem=strip_html(q["stem_html"]), answer=strip_html(q["answer_html"]),
                         core=_core(q), essence=strip_html(rf.get("essence")) or "（无）",
                         directions=strip_html(rf.get("variants")) or "（无）", exemplars=ex,
                         sections=sections, level_desc=LEVELS[level], distance_desc=DISTANCES[distance])


def build_check_prompt(q: dict, variant: dict) -> str:
    return CHECK_PROMPT.format(stem=strip_html(q["stem_html"]), solution=strip_html(q.get("solution_html")),
                               core=_core(q), v_stem=variant.get("stem", ""), v_answer=variant.get("answer", ""))


def call_llm(prompt: str) -> str:
    base = os.environ.get("MI_LLM_BASE_URL")
    key = os.environ.get("MI_LLM_API_KEY")
    model = os.environ.get("MI_LLM_MODEL")
    if not (base and key and model):
        raise RuntimeError("未配置大模型接口：请设置 MI_LLM_BASE_URL / MI_LLM_API_KEY / MI_LLM_MODEL")
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.7}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def verify(code: str, timeout: int = 30) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
    try:
        out = subprocess.run([sys.executable, "-I", f.name], capture_output=True, text=True, timeout=timeout)
        return out.returncode == 0 and "OK" in out.stdout
    except subprocess.TimeoutExpired:
        return False


def generate(q: dict, level: str = "巩固", n: int = 2, *, distance: str = "中", bank=None) -> list[dict]:
    """生成并检验。verified 为真要同时满足：验证代码通过、照抄检验通过、题眼检验通过。教师审定在此之后。"""
    raw = call_llm(build_prompt(q, level, n, distance=distance, bank=bank))
    m = re.search(r"\[.*\]", raw, re.S)
    items = json.loads(m.group()) if m else []
    out = []
    for k, it in enumerate(items):
        code_ok = verify(it.get("verify_code", ""))
        chk = {}
        try:
            cm = re.search(r"\{.*\}", call_llm(build_check_prompt(q, it)), re.S)
            chk = json.loads(cm.group()) if cm else {}
        except Exception as e:   # 检验调用失败按未通过处理
            chk = {"reason": f"检验未完成：{e}"}
        ok = bool(code_ok and chk.get("copy_ok") and chk.get("tiyan_ok"))
        out.append({"id": f'{q["id"]}-V{level[0]}{k + 1}', "parent": q["id"], "source": "变式", "level": level,
                    "distance": distance, "changed": it.get("changed", ""), "tiyan": [it.get("tiyan", "")],
                    "stem_html": it.get("stem", ""), "answer_html": it.get("answer", ""),
                    "solution_html": it.get("solution", ""), "verified": ok,
                    "checks": {"code": code_ok, "copy": bool(chk.get("copy_ok")), "tiyan": bool(chk.get("tiyan_ok")),
                               "reason": chk.get("reason", "")},
                    "units": q["units"], "sections": q["sections"], "competencies": q["competencies"]})
    return out
