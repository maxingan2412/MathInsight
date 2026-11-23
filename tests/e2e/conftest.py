"""演示网站端到端测试的公共夹具。

没装 playwright 时整个目录不收集，仓库根目录直接跑 pytest 仍只有原来的用例。
"""
import functools
import hashlib
import http.server
import json
import math
import os
import re
import tempfile
import threading
from pathlib import Path

try:
    import playwright  # noqa: F401
    import pytest_playwright  # noqa: F401
except ImportError:  # 发布流程的环境里没有 playwright
    collect_ignore_glob = ["*"]
else:
    import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
EVIDENCE = Path(os.environ.get("MI_E2E_EVIDENCE") or Path(tempfile.gettempdir()) / "mi-e2e-evidence")
PAGE_SIZE = 20  # 题库每页题数（页面约定）


# ---------- 数据（一律从 bank/ 与 web/data/ 读） ----------
def load_js(name):
    s = (WEB / "data" / name).read_text(encoding="utf-8").strip()
    s = s[s.index("=") + 1:].strip().rstrip(";")
    return json.loads(s)


def load_papers():
    return json.loads((ROOT / "bank" / "papers.json").read_text(encoding="utf-8"))


def load_questions():
    out = []
    with open(ROOT / "bank" / "questions.jsonl", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def plain_text(html):
    return re.sub(r"<[^>]+>", "", str(html or "")).replace("&nbsp;", " ").strip()


def answer_letters(q):
    m = re.search(r'<span class="key">([\s\S]*?)</span>', q.get("answer_html") or "")
    t = plain_text(m.group(1) if m else q.get("answer_html"))
    r = re.match(r"^[^A-D]*([A-D]+)", t)
    return r.group(1) if r else ""


def pages_of(n):
    return max(1, math.ceil(n / PAGE_SIZE))


def data_digest():
    h = hashlib.sha256()
    for p in sorted((WEB / "data").glob("*.js")) + [ROOT / "bank" / "papers.json", ROOT / "bank" / "questions.jsonl"]:
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


if "collect_ignore_glob" not in globals():

    # ---------- 本地服务：仓库根目录，与线上 Pages 的目录结构一致 ----------
    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    @pytest.fixture(scope="session")
    def server():
        handler = functools.partial(_Quiet, directory=str(ROOT))
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        yield "http://127.0.0.1:%d" % httpd.server_address[1]
        httpd.shutdown()
        httpd.server_close()

    @pytest.fixture(scope="session")
    def site(server):
        return server + "/web/index.html"

    @pytest.fixture(scope="session", autouse=True)
    def data_guard(request):
        """数据在测试中途被重建时提示：该轮失败需重跑确认。"""
        before = data_digest()
        yield
        if data_digest() != before:
            tr = request.config.pluginmanager.get_plugin("terminalreporter")
            msg = "注意：测试期间 web/data 或 bank 发生变化，本轮失败需重跑确认"
            if tr:
                tr.write_line(msg, yellow=True)
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            (EVIDENCE / "数据中途变化.txt").write_text(msg + "\n", encoding="utf-8")

    @pytest.fixture(scope="session")
    def papers():
        return load_papers()

    @pytest.fixture(scope="session")
    def questions():
        return load_questions()

    @pytest.fixture(scope="session")
    def web_bank():
        return load_js("bank.js")

    @pytest.fixture(scope="session")
    def web_class():
        return load_js("class.js")

    # ---------- 浏览器 ----------
    @pytest.fixture(scope="session")
    def browser_type_launch_args(browser_type_launch_args):
        args = dict(browser_type_launch_args)
        if os.path.exists("/usr/bin/google-chrome") and not args.get("channel"):
            args["channel"] = "chrome"
        args.setdefault("headless", True)
        return args

    @pytest.fixture(scope="session")
    def browser_context_args(browser_context_args):
        return {**browser_context_args, "viewport": {"width": 1440, "height": 900}, "locale": "zh-CN"}

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(item, call):
        outcome = yield
        rep = outcome.get_result()
        setattr(item, "rep_" + rep.when, rep)

    class MI:
        """包一层 page：记录控制台错误、页面异常、失败请求和对话框。"""

        def __init__(self, page, site, server):
            self.page, self.site, self.server = page, site, server
            self.errors, self.dialogs = [], []
            self.dialog_accept = True
            self.favicon = []  # 浏览器自动请求的 /favicon.ico，单独记，由专门用例判定
            page.on("console", self._console)
            page.on("pageerror", lambda e: self.errors.append("pageerror: %s" % e))
            page.on("requestfailed", lambda r: self._bad(r.url, "requestfailed: %s %s" % (r.url, r.failure)))
            page.on("response", lambda r: r.status >= 400 and self._bad(r.url, "HTTP %d: %s" % (r.status, r.url)))
            page.on("dialog", self._dialog)

        def _bad(self, url, msg):
            (self.favicon if url.endswith("/favicon.ico") else self.errors).append(msg)

        def _console(self, m):
            if m.type != "error":
                return
            url = (m.location or {}).get("url", "")
            self._bad(url, "console: %s (%s)" % (m.text, url))

        def _dialog(self, d):
            self.dialogs.append((d.type, d.message))
            d.accept() if self.dialog_accept else d.dismiss()

        def goto(self, route, wait=None):
            """打开 #/route；同一页内只换哈希，不重载。"""
            h = "#/" + route.lstrip("#/")
            if self.page.url.split("#")[0] == self.site and self.hash() != h:
                self.navigating(lambda: self.page.evaluate("h => { location.hash = h; }", h), wait)
            else:
                self.fresh(route, wait)

        def navigating(self, action, wait=None):
            """执行会触发路由重绘的操作，等旧视图被清掉、新视图出现。"""
            self.page.evaluate("() => { const m = document.createElement('i'); m.id = '__stale'; document.getElementById('view').appendChild(m); }")
            action()
            self.page.wait_for_selector("#__stale", state="detached", timeout=10000)
            if wait:
                self.page.wait_for_selector(wait, state="attached")

        def fresh(self, route, wait=None):
            """整页重载（用于验证 localStorage 持久化）。"""
            self.page.goto("about:blank")
            self.page.goto(self.site + "#/" + route.lstrip("#/"))
            if wait:
                self.page.wait_for_selector(wait, state="attached")

        def hash(self):
            return self.page.evaluate("location.hash")

        def series(self, el_id):
            return self.page.evaluate(
                """id => { const el = document.getElementById(id); if (!el) return null;
                const c = echarts.getInstanceByDom(el); if (!c) return null;
                return c.getOption().series.map(s => ({type: s.type, name: s.name || null,
                  data: (s.data || []).map(d => (d && typeof d === 'object' && !Array.isArray(d) && 'value' in d) ? d.value : d)})); }""",
                el_id,
            )

        def chart_ink(self, el_id):
            """图表里非透明像素数（canvas）或图形节点数（svg）。"""
            return self.page.evaluate(
                """id => { const el = document.getElementById(id); if (!el) return -1;
                const svg = el.querySelector('svg'); if (svg) return svg.querySelectorAll('path,rect,circle,polyline,polygon,text').length;
                let n = 0; el.querySelectorAll('canvas').forEach(cv => { if (!cv.width || !cv.height) return;
                  const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data;
                  for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++; }); return n; }""",
                el_id,
            )

        def katex_report(self, root="#view"):
            """返回 (已渲染公式数, katex-error 数, 残留 $ 的片段)。只看可见元素。"""
            return self.page.evaluate(
                """sel => { const r = document.querySelector(sel); if (!r) return [0, 0, []];
                const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
                const ok = [...r.querySelectorAll('.katex')].filter(vis).length;
                const bad = [...r.querySelectorAll('.katex-error')].filter(vis).length;
                const left = []; const w = document.createTreeWalker(r, NodeFilter.SHOW_TEXT);
                let n; while ((n = w.nextNode())) { const p = n.parentElement;
                  if (!p || p.closest('.katex, script, style, textarea') || !vis(p)) continue;
                  if (n.nodeValue.includes('$')) left.push(n.nodeValue.trim().slice(0, 80)); }
                return [ok, bad, left]; }""",
                root,
            )

        def assert_clean(self):
            assert not self.errors, "控制台错误或失败请求：\n" + "\n".join(self.errors[:20])

    @pytest.fixture
    def mi(page, site, server, request):
        m = MI(page, site, server)
        yield m
        rep = getattr(request.node, "rep_call", None)
        if rep is not None and rep.failed:
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            name = re.sub(r"[^\w一-鿿.-]+", "_", request.node.nodeid.split("::", 1)[-1])
            try:
                page.screenshot(path=str(EVIDENCE / ("失败_" + name + ".png")), full_page=True)
                (EVIDENCE / ("失败_" + name + ".txt")).write_text(
                    "用例：%s\n最后地址：%s\n控制台与请求错误：\n%s\n\n%s\n"
                    % (request.node.nodeid, page.url, "\n".join(m.errors) or "（无）", rep.longreprtext[-4000:]),
                    encoding="utf-8",
                )
            except Exception:
                pass
