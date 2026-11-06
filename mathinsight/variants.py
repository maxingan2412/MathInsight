"""大模型生成同构变式题(可选功能，需要配置 API)。

做法
----
1. 注入核心想法：把原题的「题眼」(卡点 + 打通)作为核心想法写进提示词。没有核心想法时，
   模型生成的变式往往只换数字、形似神不似。
2. 限定知识边界：只允许使用原题所在教材小节及之前学过的工具。
3. 指定难度方向：同级巩固 / 降一级铺垫 / 升一级拔高(可借鉴强基计划题的设问方式)。
4. 先验证再入库：模型须同时给出答案和可执行的 Python 验证代码；verify() 运行通过的
   变式才写入题库，并标记 source="变式"、parent=原题号，供老师审定。

环境变量
--------
MI_LLM_BASE_URL   兼容 Chat Completions 协议的接口地址（以 /v1 结尾）
MI_LLM_API_KEY    密钥
MI_LLM_MODEL      模型名
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

LEVELS = {"铺垫": "比原题低一个难度层级，拆掉一个难点，适合基础薄弱的学生先建立信心",
          "巩固": "与原题难度相同，核心想法不变，换情境、换数据或换设问方式",
          "拔高": "比原题高一个难度层级，可以增加一个参数、改为探究或存在性设问，可参考强基计划题目的设问方式"}

PROMPT = """你是一位经验丰富的高中数学命题教师。请根据下面的原题，命制 {n} 道「{level}」变式题。

【原题】
{stem}

【原题答案】
{answer}

【核心想法（题眼）】
{core}

【知识范围】只允许使用以下教材小节及更早学过的知识：{sections}

【要求】
1. 变式必须保留核心想法，而不是只替换数字；难度要求：{level_desc}。
2. 每道题给出：题干、答案、简要解析、以及一段可以独立运行的 Python 验证代码
   (用 sympy 或枚举验证答案，验证通过时打印 OK)。
3. 只输出 JSON 数组，每个元素包含字段 stem, answer, solution, verify_code。题干中的数学式用 $...$ 包裹。
"""


def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def build_prompt(q: dict, level: str = "巩固", n: int = 2) -> str:
    sections = "、".join(f'{s["book"]} {s["sec"]} {s.get("name", "")}' for s in q["sections"]) or "高中数学"
    core = "\n".join(q.get("tiyan", [])) or "（无题眼记录，请先归纳本题的关键步骤再命题）"
    return PROMPT.format(n=n, level=level, stem=strip_html(q["stem_html"]), answer=strip_html(q["answer_html"]),
                         core=core, sections=sections, level_desc=LEVELS[level])


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


def generate(q: dict, level: str = "巩固", n: int = 2) -> list[dict]:
    raw = call_llm(build_prompt(q, level, n))
    m = re.search(r"\[.*\]", raw, re.S)
    items = json.loads(m.group()) if m else []
    out = []
    for k, it in enumerate(items):
        ok = verify(it.get("verify_code", ""))
        out.append({"id": f'{q["id"]}-V{level[0]}{k + 1}', "parent": q["id"], "source": "变式", "level": level,
                    "stem_html": it.get("stem", ""), "answer_html": it.get("answer", ""),
                    "solution_html": it.get("solution", ""), "verified": ok,
                    "units": q["units"], "sections": q["sections"], "competencies": q["competencies"]})
    return out
