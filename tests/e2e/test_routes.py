"""路由、导航、入口页：每个视图能打开、导航高亮正确、无控制台错误和失败请求。"""
import pytest

ROUTES = [
    ("overview", "#c-heat canvas", "overview"),
    ("student/S01", "#s-units canvas", "student"),
    ("compare", "#cmp-table table", "compare"),
    ("papers", "#next-list table", "papers"),
    ("bank", "#bank-result .pager", "bank"),
    ("practice/S01", "#pr-monitor .card-title", "practice"),
    ("report/S01", ".rp-paper", "student"),
]


@pytest.mark.parametrize("route,ready,nav", ROUTES, ids=[r[0] for r in ROUTES])
def test_route_loads_clean(mi, route, ready, nav):
    mi.fresh(route, ready)
    mi.page.wait_for_timeout(300)
    assert mi.page.locator("#view").inner_text().strip(), "视图为空"
    active = mi.page.eval_on_selector_all("#nav a.active", "as => as.map(a => a.dataset.route)")
    assert active == [nav]
    assert "数据文件未加载" not in mi.page.inner_text("#view")
    mi.assert_clean()


def test_sidebar_nav_clicks(mi, web_class):
    mi.fresh("overview", "#c-heat canvas")
    for route, ready in [("bank", "#bank-result .pager"), ("compare", "#cmp-table table"), ("papers", "#next-list table"),
                         ("student", "#s-units canvas"), ("practice", "#pr-monitor .card-title"), ("overview", "#c-heat canvas")]:
        mi.navigating(lambda: mi.page.click('#nav a[data-route="%s"]' % route), ready)
        assert mi.hash().startswith("#/" + route)
    mi.assert_clean()


def test_unknown_route_falls_back_to_overview(mi):
    mi.fresh("no-such-page", "#c-heat")
    assert mi.hash() == "#/overview"


def test_unknown_student_redirects_to_last_student(mi, web_class):
    sid = web_class["students"][3]["id"]
    mi.fresh("student/" + sid, "#s-units canvas")
    mi.goto("student/NOBODY")
    mi.page.wait_for_function("location.hash === '#/student/%s'" % sid)
    assert web_class["profiles"][sid]["name"] in mi.page.inner_text(".profile-name")
    # 导航里「学生档案」「学生练习」记住了上次的学生
    assert mi.page.get_attribute('#nav a[data-route="student"]', "href") == "#/student/" + sid
    assert mi.page.get_attribute('#nav a[data-route="practice"]', "href") == "#/practice/" + sid


def test_topbar_and_sidebar_counts(mi, web_class):
    mi.fresh("overview", "#c-heat canvas")
    top = mi.page.inner_text("#topbar-right")
    assert "%d 名学生" % len(web_class["students"]) in top
    assert "%d 次考试" % len(web_class["exams"]) in top
    assert web_class["meta"]["class"] in mi.page.inner_text("#sidebar-foot")


def test_root_index_redirects_to_app(mi, server):
    mi.page.goto(server + "/index.html")
    mi.page.wait_for_url("**/web/index.html**")
    mi.page.wait_for_selector("#c-heat canvas", state="attached")
    mi.assert_clean()


def test_video_page_and_link(mi, server):
    mi.fresh("overview", "#c-heat")
    href = mi.page.get_attribute("a.video-link", "href")
    with mi.page.expect_navigation():
        mi.page.click("a.video-link")
    assert mi.page.url == server + "/video.html", href
    v = mi.page.locator("video")
    assert v.count() == 1
    src = mi.page.evaluate("document.querySelector('video').currentSrc || document.querySelector('video source, video').src")
    resp = mi.page.request.get(src, headers={"Range": "bytes=0-1023"})
    assert resp.status in (200, 206), src
    mi.page.wait_for_function("document.querySelector('video').readyState >= 1", timeout=15000)
    dur = mi.page.evaluate("document.querySelector('video').duration")
    assert dur and dur > 30, "视频时长 %s 秒" % dur
    back = mi.page.locator('a[href="web/index.html"]')
    assert back.count() >= 1
    mi.assert_clean()


def test_favicon_not_404(mi, server):
    """浏览器会自动请求 /favicon.ico；页面没声明图标时线上同样 404，控制台会出一条错误。"""
    mi.fresh("overview", "#c-heat canvas")
    mi.page.wait_for_timeout(500)
    declared = mi.page.evaluate("!!document.querySelector('link[rel~=icon]')")
    assert declared or not mi.favicon, "页面没声明 favicon，浏览器请求 /favicon.ico 得到：%s" % mi.favicon
