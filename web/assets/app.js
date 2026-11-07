/* MathInsight 前端：原生 JS，hash 路由，ECharts + KaTeX */
(function () {
  'use strict';
  var C = window.MI_CLASS, B = window.MI_BANK;
  if (!C || !B) { document.getElementById('view').innerHTML = '<div class="empty">数据文件未加载（web/data/class.js、bank.js）</div>'; return; }

  /* ---------- 基础 ---------- */
  var PAL = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
  var SEQ = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#1c5cab', '#0d366b'];
  var DIV = ['#1c5cab', '#86b6ef', '#f0efec', '#f0a3a2', '#d03b3b'];
  var FONT = 'system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif';
  var UNITS = C.meta.units, COMPS = C.meta.competencies;
  var QMAP = new Map(B.questions.map(function (q) { return [q.id, q]; }));
  var NAME = {}; C.students.forEach(function (s) { NAME[s.id] = s.name; });
  var view = document.getElementById('view');
  var charts = [];

  echarts.registerTheme('mi', {
    color: PAL, backgroundColor: 'transparent',
    textStyle: { fontFamily: FONT, color: '#52514e' },
    title: { textStyle: { color: '#0b0b0b', fontWeight: 600, fontSize: 13 } },
    legend: { textStyle: { color: '#52514e' } },
    categoryAxis: { axisLine: { lineStyle: { color: '#c3c2b7' } }, axisTick: { show: false }, axisLabel: { color: '#52514e' }, splitLine: { show: false } },
    valueAxis: { axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#898781' }, splitLine: { lineStyle: { color: '#e1e0d9' } } },
    tooltip: { backgroundColor: '#fff', borderColor: '#e4e6ea', textStyle: { color: '#0b0b0b', fontSize: 12 } }
  });

  function chart(el, opt, initOpts) {
    if (typeof el === 'string') el = document.getElementById(el);
    if (!el) return null;
    var c = echarts.init(el, 'mi', initOpts);
    opt.animation = false;
    c.setOption(opt);
    charts.push(c);
    return c;
  }
  function disposeCharts() { charts.forEach(function (c) { c.dispose(); }); charts = []; }
  window.addEventListener('resize', function () { charts.forEach(function (c) { c.resize(); }); });
  window.addEventListener('beforeprint', function () { charts.forEach(function (c) { c.resize(); }); });

  function tex(el) {
    if (!el || !window.renderMathInElement) return;
    renderMathInElement(el, {
      delimiters: [{ left: '$$', right: '$$', display: true }, { left: '$', right: '$', display: false }],
      throwOnError: false, strict: 'ignore'
    });
  }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function pct(x, d) { return x == null ? '—' : (x * 100).toFixed(d == null ? 0 : d) + '%'; }
  function fix(x, d) { return x == null ? '—' : Number(x).toFixed(d == null ? 1 : d); }
  function sum(a) { return a.reduce(function (s, x) { return s + x; }, 0); }
  function mean(a) { return a.length ? sum(a) / a.length : 0; }
  function quantile(sorted, p) { var i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i); return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo); }
  function uniq(a) { return Array.from(new Set(a)); }
  function byId(id) { return document.getElementById(id); }
  function plainText(html) { return String(html || '').replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim(); }
  function dateStr(ts) { var d = new Date(ts); return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2) + ' ' + ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2); }
  function isToday(ts) { var d = new Date(ts), n = new Date(); return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate(); }
  function chipUnit(u) { return '<span class="chip blue">' + esc(u) + '</span>'; }
  function roleBadge(r) { return '<span class="badge ' + (r === '挑战' ? 'role-tiao' : 'role-gu') + '">' + esc(r) + '</span>'; }
  function qBadges(q) {
    var s = '<span class="badge type">' + esc(q.type) + '</span><span class="badge region">' + esc(q.region) + ' ' + q.year + ' ' + esc(q.kind) + '</span>';
    if (q.optional) s += '<span class="badge optional">选做</span>';
    return s;
  }
  /* 选择题答案字母 */
  function answerLetters(q) {
    var m = /<span class="key">([\s\S]*?)<\/span>/.exec(q.answer_html || '');
    var t = plainText(m ? m[1] : q.answer_html);
    var r = /^[^A-D]*([A-D]+)/.exec(t);
    return r ? r[1] : '';
  }
  /* ---------- 填空题数值判分（递归下降求值，不用 eval） ---------- */
  var NUM_TOL = 1e-6;
  function NumErr(msg) { this.message = msg || '没看懂这个写法，请检查'; }
  function hasNumAnswer(q) { return q.type === '填空' && Array.isArray(q.answer_num) && q.answer_num.length > 0; }
  function normNumInput(s) {
    return String(s || '')
      .replace(/[！-～]/g, function (c) { return String.fromCharCode(c.charCodeAt(0) - 0xFEE0); })
      .replace(/　/g, ' ').replace(/[−–—﹣]/g, '-').replace(/[×·∙⋅]/g, '*').replace(/÷/g, '/')
      .replace(/²/g, '^2').replace(/³/g, '^3').replace(/Π/g, 'π').toLowerCase();
  }
  function numTokens(s) {
    var t = [], i = 0, m;
    while (i < s.length) {
      var c = s[i];
      if (/\s/.test(c)) { i++; continue; }
      if ((m = /^(\d+\.?\d*|\.\d+)/.exec(s.slice(i)))) { t.push({ k: 'num', v: parseFloat(m[1]) }); i += m[1].length; continue; }
      if (s.substr(i, 2) === 'pi') { t.push({ k: 'pi' }); i += 2; continue; }
      if (s.substr(i, 4) === 'sqrt') { t.push({ k: 'root', n: 2 }); i += 4; continue; }
      if (c === 'π') t.push({ k: 'pi' });
      else if (c === '√') t.push({ k: 'root', n: 2 });
      else if (c === '∛') t.push({ k: 'root', n: 3 });
      else if (c === '∜') t.push({ k: 'root', n: 4 });
      else if ('+-*/^()'.indexOf(c) >= 0) t.push({ k: c });
      else if (c === '%' || c === '°') t.push({ k: c });
      else throw new NumErr();
      i++;
    }
    return t;
  }
  /* 解析一空：返回 { v: 数值, unit: '' | '%' | '°' } */
  function evalBlank(src) {
    var t = numTokens(src), p = 0;
    function peek() { return t[p]; }
    function is(k) { return p < t.length && t[p].k === k; }
    function startsAtom() { return is('num') || is('pi') || is('root') || is('('); }
    function expr() {
      var v = term();
      while (is('+') || is('-')) { var op = t[p++].k, r = term(); v = op === '+' ? v + r : v - r; }
      return v;
    }
    function term() {
      var v = unary(), divided = false;
      for (;;) {
        if (is('*') || is('/')) {
          var op = t[p++].k, r = unary();
          if (op === '/') { if (r === 0) throw new NumErr(); v /= r; divided = true; } else v *= r;
        } else if (startsAtom()) {
          if (is('num')) throw new NumErr();  // 两个数直接相连，如 π2、(1)2
          if (divided) throw new NumErr('写法有歧义，请加括号，如 2/(3π) 或 (2/3)π');
          v *= unary();
        } else return v;
      }
    }
    function unary() {
      if (is('-')) { p++; return -unary(); }
      if (is('+')) { p++; return unary(); }
      return power();
    }
    function power() {
      var b = atom();
      if (is('^')) { p++; var e = unary(); var r = Math.pow(b, e); if (!isFinite(r)) throw new NumErr(); return r; }
      return b;
    }
    function atom() {
      var tok = peek();
      if (!tok) throw new NumErr();
      if (tok.k === 'num') { p++; return tok.v; }
      if (tok.k === 'pi') { p++; return Math.PI; }
      if (tok.k === '(') { p++; var v = expr(); if (!is(')')) throw new NumErr(); p++; return v; }
      if (tok.k === 'root') {
        p++;
        var x = atom();  // √ 只作用于紧跟的一个数、π、括号或根式：√2/2 = (√2)/2
        if (x < 0) throw new NumErr();
        return tok.n === 2 ? Math.sqrt(x) : Math.pow(x, 1 / tok.n);
      }
      throw new NumErr();
    }
    if (!t.length) throw new NumErr();
    var v = expr(), unit = '';
    if (is('%') || is('°')) unit = t[p++].k;
    if (p !== t.length || !isFinite(v)) throw new NumErr();
    return { v: v, unit: unit };
  }
  function numClose(x, a) { return Math.abs(x - a) <= NUM_TOL * Math.max(1, Math.abs(a)); }
  /* 判分：返回 { result, marks } ；输入看不懂时抛 NumErr */
  function gradeNum(q, input) {
    var raw = normNumInput(input).trim();
    if (!raw) throw new NumErr('请先填写答案');
    var parts = raw.split(/[,;、]/).map(function (s) { return s.trim(); });
    while (parts.length > 1 && !parts[parts.length - 1]) parts.pop();
    var ans = q.answer_num;
    if (parts.length !== ans.length) throw new NumErr(ans.length > 1 ? '本题有 ' + ans.length + ' 个空，请按顺序用逗号或分号隔开' : '本题只有 1 个空，请只填一个数');
    var vals = parts.map(evalBlank);
    var marks = vals.map(function (b, i) {
      // 带 % 或 ° 时两种读法都认：20% 既可对 0.2 也可对「____%」里的 20；30° 既可对 30 也可对 π/6
      var cands = b.unit === '%' ? [b.v / 100, b.v] : b.unit === '°' ? [b.v, b.v * Math.PI / 180] : [b.v];
      return cands.some(function (x) { return numClose(x, ans[i]); });
    });
    var k = marks.filter(Boolean).length;
    return { result: k === ans.length ? 'right' : k > 0 ? 'partial' : 'wrong', marks: marks };
  }
  /* 正确答案的展示：取 key 标签内容，没有就取整段答案去掉段落标签与句末句号 */
  function keyAnswerHtml(q) {
    var re = /<span class="key">([\s\S]*?)<\/span>/g, m, out = [];
    while ((m = re.exec(q.answer_html || ''))) out.push(m[1]);
    if (out.length) return out.join('；');
    return String(q.answer_html || '').replace(/<\/?p>/g, '').replace(/[。．]\s*$/, '');
  }

  function lastStudent() { try { return localStorage.getItem('mi_last_student') || C.students[0].id; } catch (e) { return C.students[0].id; } }
  function setLastStudent(id) { try { localStorage.setItem('mi_last_student', id); } catch (e) { } }
  function cardHtml(title, sub, body, cls) {
    return '<div class="card ' + (cls || '') + '"><div class="card-title">' + title + '</div>' + (sub ? '<div class="card-sub">' + sub + '</div>' : '') + body + '</div>';
  }
  var AXIS_UNITS = { type: 'category', data: UNITS, axisLabel: { interval: 0, rotate: 32, fontSize: 11 } };
  var PCT_AXIS = { type: 'value', min: 0, max: 1, axisLabel: { formatter: function (v) { return Math.round(v * 100) + '%'; } } };
  function radarOpt(indicators, series, max) {
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, icon: 'circle' },
      radar: { indicator: indicators.map(function (n) { return { name: n, max: max || 1 }; }), radius: '62%', center: ['50%', '47%'], axisName: { color: '#52514e', fontSize: 11 }, splitArea: { areaStyle: { color: ['#fff', '#f8f9fb'] } }, splitLine: { lineStyle: { color: '#e1e0d9' } }, axisLine: { lineStyle: { color: '#e1e0d9' } } },
      series: [{ type: 'radar', symbolSize: 5, data: series.map(function (s, i) { return { name: s.name, value: s.value, lineStyle: { width: 2, type: s.dashed ? 'dashed' : 'solid' }, areaStyle: { opacity: s.dashed ? 0.05 : 0.18 }, itemStyle: { color: s.color || PAL[i % PAL.length] } }; }) }]
    };
  }
  function pieOpt(obj, radius) {
    var data = Object.keys(obj).map(function (k) { return { name: k, value: obj[k] }; }).sort(function (a, b) { return b.value - a.value; });
    return {
      tooltip: { trigger: 'item', formatter: function (p) { return p.name + '：' + p.value + '（' + p.percent + '%）'; } },
      legend: { bottom: 0, icon: 'circle', itemWidth: 10, textStyle: { fontSize: 11 } },
      series: [{ type: 'pie', radius: radius || ['40%', '70%'], center: ['50%', '44%'], data: data, itemStyle: { borderColor: '#fff', borderWidth: 2 }, label: { position: 'inside', formatter: function (p) { return p.percent >= 7 ? p.percent.toFixed(0) + '%' : ''; }, fontSize: 11, color: '#fff' }, labelLine: { show: false } }]
    };
  }

  /* ---------- 路由 ---------- */
  var PAGES = {};
  function route() {
    var raw = (location.hash || '#/overview').replace(/^#\/?/, '');
    var qs = raw.split('?'); var parts = qs[0].split('/').filter(Boolean);
    var name = parts[0] || 'overview', arg = parts[1] ? decodeURIComponent(parts[1]) : null;
    var query = {}; (qs[1] || '').split('&').forEach(function (kv) { if (!kv) return; var p = kv.split('='); query[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || ''); });
    if (!PAGES[name]) { location.hash = '#/overview'; return; }
    if ((name === 'student' || name === 'practice') && !C.profiles[arg]) { location.hash = '#/' + name + '/' + lastStudent(); return; }
    if (name === 'report' && arg !== 'ALL' && !C.profiles[arg]) { location.hash = '#/report/' + lastStudent(); return; }
    if (name === 'student' || name === 'practice' || (name === 'report' && arg !== 'ALL')) setLastStudent(arg);
    document.body.classList.toggle('report-mode', name === 'report');
    disposeCharts();
    view.innerHTML = '';
    document.querySelectorAll('#nav a').forEach(function (a) {
      a.classList.toggle('active', a.dataset.route === name || (name === 'report' && arg !== 'ALL' && a.dataset.route === 'student'));
      if (a.dataset.route === 'student') a.setAttribute('href', '#/student/' + lastStudent());
      if (a.dataset.route === 'practice') a.setAttribute('href', '#/practice/' + lastStudent());
    });
    window.scrollTo(0, 0);
    PAGES[name](arg, query);
  }
  window.addEventListener('hashchange', route);

  /* ---------- 1. 班级总览 ---------- */
  PAGES.overview = function () {
    var ov = C.overview, em = ov.exam_means, last = em[em.length - 1], prev = em[em.length - 2];
    var delta = prev ? last.mean - prev.mean : 0;
    var h = '<div class="page-head"><div><h1 class="page-title">班级总览 · ' + esc(C.meta.class) + '</h1><div class="page-desc">' + UNITS.length + ' 个知识板块 · ' + COMPS.length + ' 大核心素养 · 模型掌握度 = 学生做本板块典型高考题的预计得分率</div></div><div class="page-actions"><a class="btn" href="#/report/ALL">打印全班报告</a></div></div>';
    h += '<div class="grid cols-4 kpis">' +
      kpi('学生数', C.students.length, '人', '班级人数', '#2a78d6', '◉') +
      kpi('考试次数', C.exams.length, '次', esc(C.exams[0].date) + ' ～ ' + esc(C.exams[C.exams.length - 1].date), '#1baf7a', '▤') +
      kpi('题库', B.stats.papers + ' 套 / ' + B.stats.questions + ' 题', '', esc(Object.keys(B.stats.by_region).map(function (k) { return k + ' ' + B.stats.by_region[k]; }).join(' · ')), '#6250d6', '▣') +
      kpi('最近一次均分', fix(last.mean), '/ ' + last.full, esc(last.title) + ' · 较上次 <span class="' + (delta >= 0 ? 'up' : 'down') + '">' + (delta >= 0 ? '+' : '') + fix(delta) + '</span>', '#eb6834', '✎') +
      '</div>';
    h += '<div class="grid cols-2">' +
      cardHtml('班级板块掌握度', '蓝：模型掌握度均值（σ(θ+δ−b̄)）；橙：历次考试该板块实际得分率；悬停看证据量', '<div class="chart" id="c-units"></div>') +
      cardHtml('六大核心素养（班级均值）', '雷达半径 = 班级平均掌握度；阴影范围 = ±1 个标准差', '<div class="chart" id="c-comp"></div>') +
      '</div>';
    h += '<div class="grid cols-2">' +
      cardHtml('历次考试均分走势', '满分 ' + last.full, '<div class="chart short" id="c-exams"></div>') +
      cardHtml('薄弱板块', '相对偏移 δ 班级均值最低且实际得分率低于全卷平均的板块（两条同时满足）', '<ul class="weak-list mt">' + ov.weak_units.map(function (u) { var d = ov.units.filter(function (x) { return x.unit === u; })[0]; return '<li><span>' + chipUnit(u) + '</span><span>实际得分率 <b>' + pct(d.rate) + '</b> · 模型掌握度 ' + pct(d.mean) + ' · δ̄ ' + fix(d.delta_mean, 2) + '</span></li>'; }).join('') + '</ul><div class="small muted mt">详见下方「薄弱板块诊断」</div>') +
      '</div>';
    h += '<div class="grid"><div class="card"><div class="card-title">学生 × 板块 掌握度热力图</div><div class="card-sub">横轴学生（按学号），纵轴板块；颜色越深掌握越好；点击格子进入该学生档案</div><div class="chart" id="c-heat" style="height:' + (UNITS.length * 26 + 110) + 'px"></div></div></div>';
    h += '<h2 class="page-title" style="font-size:17px;margin:6px 0 12px">薄弱板块诊断</h2>';
    ov.diagnoses.forEach(function (d, i) {
      h += '<div class="card diag mb"><div class="card-title"><span>' + chipUnit(d.unit) + ' 得分率 ' + pct(d.rate) + '（全卷平均 ' + pct(d.overall) + '）· 主要成因：<span class="chip bad">' + esc(d.main_competency) + '</span></span></div>' +
        '<div class="diag-text">' + esc(d.text) + '</div>' +
        '<div class="grid cols-4" style="margin-bottom:10px">' +
        '<div><div class="card-sub">两路证据合成：素养证据分</div><div class="chart short" id="d-ev-' + i + '"></div></div>' +
        '<div><div class="card-sub">模型路：班级素养偏移 γ̄ 与本板块素养权重</div><div class="chart short" id="d-gm-' + i + '"></div></div>' +
        '<div><div class="card-sub">教师路：错因分布</div><div class="chart short" id="d-er-' + i + '"></div></div>' +
        '<div><div class="card-sub">板块内最弱小节</div><ul class="weak-list">' + d.weakest_sections.map(function (s) { return '<li><span>' + esc(s.section) + '</span><b>' + pct(s.rate) + '</b></li>'; }).join('') + '</ul></div>' +
        '</div><div class="diag-sugg"><b>教学建议：</b>' + esc(d.suggestion) + '</div></div>';
    });
    view.innerHTML = h;

    chart('c-units', {
      tooltip: { trigger: 'axis', formatter: function (ps) { var u = ov.units[ps[0].dataIndex]; return '<b>' + u.unit + '</b><br>模型掌握度均值 ' + pct(u.mean) + '（σ ' + fix(u.std, 2) + '，区间 ' + pct(u.min) + '～' + pct(u.max) + '）<br>实际得分率 ' + pct(u.rate) + '<br>班级相对偏移 δ̄ ' + fix(u.delta_mean, 3) + '<br>证据量（题量加权）' + fix(u.evidence); } },
      legend: { bottom: 0, icon: 'circle' }, grid: { left: 8, right: 12, top: 16, bottom: 54, containLabel: true },
      xAxis: AXIS_UNITS, yAxis: PCT_AXIS,
      series: [
        { name: '模型掌握度', type: 'bar', barGap: '10%', data: ov.units.map(function (u) { return u.mean; }), itemStyle: { borderRadius: [4, 4, 0, 0] } },
        { name: '实际得分率', type: 'bar', data: ov.units.map(function (u) { return u.rate; }), itemStyle: { borderRadius: [4, 4, 0, 0] } }
      ]
    });
    chart('c-comp', radarOpt(COMPS, [
      { name: '班级均值', value: ov.competencies.map(function (c) { return c.mean; }) },
      { name: '均值 + σ', value: ov.competencies.map(function (c) { return Math.min(1, c.mean + c.std); }), dashed: true, color: '#1baf7a' },
      { name: '均值 − σ', value: ov.competencies.map(function (c) { return Math.max(0, c.mean - c.std); }), dashed: true, color: '#eb6834' }
    ]));
    var hm = ov.heatmap, hdata = [];
    hm.values.forEach(function (row, si) { row.forEach(function (v, ui) { hdata.push([si, ui, v]); }); });
    var heat = chart('c-heat', {
      tooltip: { formatter: function (p) { return NAME[hm.students[p.data[0]]] + '（' + hm.students[p.data[0]] + '）<br>' + hm.units[p.data[1]] + '：' + pct(p.data[2]); } },
      grid: { left: 8, right: 70, top: 8, bottom: 8, containLabel: true },
      xAxis: { type: 'category', data: hm.students.map(function (s) { return NAME[s]; }), axisLabel: { interval: 0, rotate: 50, fontSize: 10 }, splitArea: { show: false } },
      yAxis: { type: 'category', data: hm.units, inverse: true, axisLabel: { fontSize: 11 } },
      visualMap: { min: 0, max: 1, calculable: true, orient: 'vertical', right: 0, top: 'middle', itemHeight: 160, inRange: { color: SEQ }, text: ['高', '低'], textStyle: { fontSize: 11 } },
      series: [{ type: 'heatmap', data: hdata, itemStyle: { borderColor: '#fff', borderWidth: 1 }, emphasis: { itemStyle: { borderColor: '#0b0b0b', borderWidth: 2 } } }]
    });
    heat.on('click', function (p) { location.hash = '#/student/' + hm.students[p.data[0]]; });
    chart('c-exams', {
      tooltip: { trigger: 'axis', formatter: function (ps) { var e = em[ps[0].dataIndex]; return e.title + '<br>均分 ' + fix(e.mean) + ' / ' + e.full + '（' + pct(e.mean / e.full) + '）'; } },
      grid: { left: 8, right: 40, top: 20, bottom: 10, containLabel: true },
      xAxis: { type: 'category', data: em.map(function (e) { return e.title.replace('高三', ''); }), boundaryGap: false },
      yAxis: { type: 'value', min: 0, max: last.full, name: '分' },
      series: [{ type: 'line', data: em.map(function (e) { return e.mean; }), symbolSize: 8, lineStyle: { width: 2 }, areaStyle: { opacity: 0.08 }, label: { show: true, position: 'top', formatter: function (p) { return fix(p.value); }, color: '#52514e' } }]
    });
    ov.diagnoses.forEach(function (d, i) {
      chart('d-ev-' + i, {
        tooltip: { trigger: 'axis' }, grid: { left: 8, right: 12, top: 10, bottom: 10, containLabel: true },
        xAxis: { type: 'category', data: COMPS, axisLabel: { interval: 0, rotate: 32, fontSize: 10 } }, yAxis: { type: 'value', min: 0, max: 1 },
        series: [{ type: 'bar', data: COMPS.map(function (c) { return { value: d.evidence[c] || 0, itemStyle: { color: c === d.main_competency ? '#e34948' : '#2a78d6', borderRadius: [4, 4, 0, 0] } }; }), label: { show: true, position: 'top', fontSize: 10, formatter: function (p) { return p.value ? fix(p.value, 2) : ''; } }, barMaxWidth: 26 }]
      });
      chart('d-gm-' + i, {
        tooltip: { trigger: 'axis' }, legend: { bottom: 0, icon: 'circle', itemWidth: 10, textStyle: { fontSize: 10 } }, grid: { left: 8, right: 8, top: 10, bottom: 28, containLabel: true },
        xAxis: { type: 'category', data: COMPS, axisLabel: { interval: 0, rotate: 32, fontSize: 10 } }, yAxis: { type: 'value' },
        series: [
          { name: '班级素养偏移 γ̄', type: 'bar', data: COMPS.map(function (c) { var v = d.class_gamma[c] || 0; return { value: v, itemStyle: { color: v < 0 ? '#d03b3b' : '#2a78d6', borderRadius: 3 } }; }), barMaxWidth: 20 },
          { name: '本板块素养权重', type: 'line', data: COMPS.map(function (c) { return d.weight_share[c] || 0; }), symbolSize: 6, lineStyle: { width: 2, color: '#eda100' }, itemStyle: { color: '#eda100' } }
        ]
      });
      chart('d-er-' + i, pieOpt(d.errors, ['36%', '66%']));
    });
  };
  function kpi(label, value, unit, foot, color, ico) {
    return '<div class="card kpi"><div class="kpi-ico" style="background:' + color + '">' + ico + '</div><div class="kpi-label">' + label + '</div><div class="kpi-value">' + value + (unit ? '<small>' + unit + '</small>' : '') + '</div><div class="kpi-foot">' + foot + '</div></div>';
  }

  /* ---------- 2. 学生档案 ---------- */
  function studentListHtml(cur, base) {
    return '<div class="card student-list"><input class="input" id="stu-search" type="text" placeholder="搜索姓名 / 学号"><div class="list" id="stu-list">' +
      C.students.map(function (s) { return '<a class="item ' + (s.id === cur ? 'active' : '') + '" href="#/' + base + '/' + s.id + '" data-key="' + esc(s.name + ' ' + s.id).toLowerCase() + '"><span>' + esc(s.name) + '</span><span class="sid">' + s.id + '</span></a>'; }).join('') + '</div></div>';
  }
  function bindStudentSearch() {
    var inp = byId('stu-search'); if (!inp) return;
    inp.addEventListener('input', function () {
      var k = inp.value.trim().toLowerCase();
      document.querySelectorAll('#stu-list .item').forEach(function (a) { a.style.display = (!k || a.dataset.key.indexOf(k) >= 0) ? '' : 'none'; });
    });
  }
  function questionCard(q, extra, opts) {
    opts = opts || {};
    var h = '<div class="qcard" id="qc-' + esc(q.id) + '"><div class="qcard-head"><span class="qid">' + esc(q.id) + '</span>' + qBadges(q) + '<span>' + q.score + ' 分</span><span>难度 ' + fix(q.difficulty, 2) + '</span>' + (q.tiyan_tag ? '<span class="chip violet">题眼：' + esc(q.tiyan_tag) + '</span>' : '') + '<span class="spacer"></span>' + (extra || '') + '</div>' +
      '<div class="qbody">' + (q.stem_html || '') + '</div>' +
      '<div class="small muted mt">' + q.units.map(chipUnit).join('') + ' ' + (q.sections || []).map(function (s) { return '<span class="chip gray">' + esc(s.book + ' ' + s.sec + ' ' + s.name) + '</span>'; }).join('') + '</div>';
    if (opts.toggles) {
      h += '<div class="qtoggles">' +
        (q.tiyan && q.tiyan.length ? '<button class="btn sm" data-tg="tiyan" data-q="' + esc(q.id) + '">题眼</button>' : '') +
        '<button class="btn sm" data-tg="answer" data-q="' + esc(q.id) + '">答案</button>' +
        (q.solution_html ? '<button class="btn sm" data-tg="solution" data-q="' + esc(q.id) + '">详解</button>' : '') + '</div>' +
        '<div class="qsec qbody" data-sec="tiyan" style="display:none"><div class="qsec-title">题眼（卡点与打通）</div><ul class="tiyan-list">' + (q.tiyan || []).map(function (t) { return '<li>' + t + '</li>'; }).join('') + '</ul></div>' +
        '<div class="qsec qbody" data-sec="answer" style="display:none"><div class="qsec-title">答案</div>' + (q.answer_html || '') + '</div>' +
        '<div class="qsec qbody" data-sec="solution" style="display:none"><div class="qsec-title">详解</div>' + (q.solution_html || '') + '</div>';
    }
    return h + '</div>';
  }
  function bindToggles(root) {
    root.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-tg]'); if (!b) return;
      var card = byId('qc-' + b.dataset.q), sec = card.querySelector('[data-sec="' + b.dataset.tg + '"]');
      var show = sec.style.display === 'none';
      sec.style.display = show ? '' : 'none';
      b.classList.toggle('primary', show);
      if (show && !sec.dataset.tex) { tex(sec); sec.dataset.tex = '1'; }
    });
  }

  PAGES.student = function (sid) {
    setLastStudent(sid);
    var p = C.profiles[sid];
    var h = '<div class="two-col">' + studentListHtml(sid, 'student') + '<div>';
    h += '<div class="card mb"><div class="page-head" style="margin-bottom:8px"><div class="profile-head"><div class="avatar">' + esc(p.name.slice(0, 1)) + '</div><div><div class="profile-name">' + esc(p.name) + ' <span class="muted small">' + sid + '</span></div><div class="profile-meta">' + esc(C.meta.class) + ' · 总体能力 θ = ' + fix(p.theta, 2) + '（班内第 ' + thetaRank(sid) + ' 名） · 最近 ' + esc(p.trend[p.trend.length - 1].title) + ' ' + p.trend[p.trend.length - 1].total + ' 分 / 第 ' + p.trend[p.trend.length - 1].rank + ' 名</div></div></div>' +
      '<div class="page-actions"><a class="btn primary" href="#/practice/' + sid + '">去练习</a><button class="btn" id="s-ai">阶段复盘：复制给 AI</button><a class="btn" href="#/report/' + sid + '">打印报告</a></div></div><div id="s-ai-box"></div>' +
      '<div class="tag-row"><span class="lbl">强项</span>' + p.strong.map(function (u) { return '<span class="chip good">' + esc(u) + '</span>'; }).join('') + '<span class="lbl" style="margin-left:14px">弱项</span>' + p.weak.map(function (u) { return '<span class="chip bad">' + esc(u) + '</span>'; }).join('') +
      '<span class="lbl" style="margin-left:14px">评语标签</span>' + p.tags.map(function (t) { return '<span class="chip ' + (t.sign === '+' ? 'good' : 'bad') + '">' + esc(t.category) + ' · ' + esc(t.tag) + '</span>'; }).join('') + '</div></div>';
    h += '<div class="grid cols-2">' +
      cardHtml('板块掌握度雷达', '本人 vs 班级均值', '<div class="chart" id="s-unit-radar"></div>') +
      cardHtml('六大素养雷达', '本人 vs 班级均值', '<div class="chart" id="s-comp-radar"></div>') + '</div>';
    h += '<div class="grid cols-2">' +
      cardHtml('成绩与名次走势', '左轴：得分（实线本人，虚线班级均分）；右轴：名次（越上越靠前）', '<div class="chart" id="s-trend"></div>') +
      cardHtml('错因分布', '近几次考试教师标注的错因', '<div class="chart" id="s-err"></div>') + '</div>';
    h += '<div class="grid cols-2">' +
      cardHtml('板块掌握度与班内百分位', '条：掌握度；菱形：班级均值；右侧：班内百分位（P）', '<div class="chart" id="s-units" style="height:' + (UNITS.length * 28 + 60) + 'px"></div>') +
      '<div>' + cardHtml('教师评价与自动标签', '', (p.comments.length ? p.comments.map(function (c) { return '<div class="comment"><span class="date">' + esc(c.date) + '</span>' + esc(c.text) + '</div>'; }).join('') : '<div class="muted">暂无评语</div>') + '<div class="tag-row">' + p.tags.map(function (t) { return '<span class="chip ' + (t.sign === '+' ? 'good' : 'bad') + '">' + (t.sign === '+' ? '＋' : '－') + ' ' + esc(t.category) + ' · ' + esc(t.tag) + '</span>'; }).join('') + '</div>') +
      '<div style="height:16px"></div>' + cardHtml('个性化建议', '', '<ol class="advice-list">' + p.advice.map(function (a) { return '<li>' + esc(a) + '</li>'; }).join('') + '</ol>') + '</div></div>';
    var n = sum(p.practice.groups.map(function (g) { return g.items.length; }));
    h += '<div class="card"><div class="card-title"><span>推荐练习（' + n + ' 题）</span><a class="btn primary sm" href="#/practice/' + sid + '">去练习</a></div><div class="card-sub">按弱项板块推荐；「预计得分率」是模型预测该生本题的得分率，巩固题偏易、挑战题偏难</div>';
    p.practice.groups.forEach(function (g) {
      h += '<h3 style="font-size:14px;margin:12px 0 8px">' + chipUnit(g.unit) + ' 掌握度 ' + pct(g.mastery) + '</h3>';
      g.items.forEach(function (it) {
        var q = QMAP.get(it.qid); if (!q) return;
        h += questionCard(q, '<span class="chip gray">预计得分率 ' + pct(it.pred) + '</span>' + roleBadge(it.role) + ' <a class="btn sm" href="#/practice/' + sid + '?q=' + esc(it.qid) + '">去练习</a>', { hideTail: true });
      });
    });
    h += '</div></div></div>';
    view.innerHTML = h;
    bindStudentSearch();
    tex(view);
    byId('s-ai').addEventListener('click', function () { var st = loadState(sid); aiShowPack(byId('s-ai-box'), aiPackReview(p, st), function () { aiLog(sid, st, { qid: '', scene: 'review', ts: Date.now() }); }, '你的成绩走势、弱项、错因和练习记录'); });

    chart('s-unit-radar', radarOpt(UNITS, [{ name: p.name, value: p.units.map(function (u) { return u.mastery; }) }, { name: '班级均值', value: p.units.map(function (u) { return u.class_mean; }), dashed: true, color: '#898781' }]));
    chart('s-comp-radar', radarOpt(COMPS, [{ name: p.name, value: p.competencies.map(function (u) { return u.mastery; }), color: '#1baf7a' }, { name: '班级均值', value: p.competencies.map(function (u) { return u.class_mean; }), dashed: true, color: '#898781' }]));
    chart('s-trend', {
      tooltip: { trigger: 'axis', formatter: function (ps) { var t = p.trend[ps[0].dataIndex]; return t.title + '<br>得分 ' + t.total + ' / ' + t.full + '（班级均分 ' + fix(t.class_mean) + '）<br>名次 第 ' + t.rank + ' / ' + C.students.length; } },
      legend: { bottom: 0, icon: 'circle' }, grid: { left: 8, right: 36, top: 24, bottom: 30, containLabel: true },
      xAxis: { type: 'category', data: p.trend.map(function (t) { return t.title.replace('高三', ''); }), boundaryGap: false },
      yAxis: [{ type: 'value', min: 0, max: p.trend[0].full, axisLabel: { formatter: '{value} 分' } }, { type: 'value', inverse: true, min: 1, max: C.students.length, splitLine: { show: false }, axisLabel: { formatter: '第{value}' } }],
      series: [
        { name: '得分', type: 'line', data: p.trend.map(function (t) { return t.total; }), symbolSize: 8, lineStyle: { width: 2 }, label: { show: true, position: 'top', color: '#52514e' } },
        { name: '班级均分', type: 'line', data: p.trend.map(function (t) { return t.class_mean; }), symbol: 'none', lineStyle: { width: 2, type: 'dashed', color: '#898781' }, itemStyle: { color: '#898781' } },
        { name: '名次', type: 'line', yAxisIndex: 1, data: p.trend.map(function (t) { return t.rank; }), symbol: 'diamond', symbolSize: 9, lineStyle: { width: 2, color: '#eb6834' }, itemStyle: { color: '#eb6834' } }
      ]
    });
    chart('s-err', pieOpt(p.errors));
    var us = p.units.slice().sort(function (a, b) { return b.mastery - a.mastery; });
    chart('s-units', {
      tooltip: { trigger: 'axis', formatter: function (ps) { var u = us[ps[0].dataIndex]; return '<b>' + u.unit + '</b><br>掌握度 ' + pct(u.mastery) + '（班级均值 ' + pct(u.class_mean) + '）<br>相对偏移 δ ' + fix(u.delta, 2) + '<br>班内百分位 P' + Math.round(u.percentile * 100) + '<br>证据量 ' + fix(u.evidence); } },
      legend: { bottom: 0, icon: 'circle' }, grid: { left: 8, right: 56, top: 6, bottom: 28, containLabel: true },
      xAxis: PCT_AXIS, yAxis: { type: 'category', data: us.map(function (u) { return u.unit; }), inverse: true, axisLabel: { fontSize: 11 } },
      series: [
        { name: '掌握度', type: 'bar', data: us.map(function (u) { return { value: u.mastery, itemStyle: { color: u.mastery >= u.class_mean ? '#2a78d6' : '#eb6834', borderRadius: [0, 4, 4, 0] } }; }), barMaxWidth: 16, label: { show: true, position: 'right', formatter: function (pp) { return pct(pp.value) + '  P' + Math.round(us[pp.dataIndex].percentile * 100); }, fontSize: 11, color: '#52514e' } },
        { name: '班级均值', type: 'scatter', data: us.map(function (u) { return u.class_mean; }), symbol: 'diamond', symbolSize: 10, itemStyle: { color: '#0b0b0b' } }
      ]
    });
  };
  function thetaRank(sid) {
    var arr = Object.keys(C.profiles).map(function (k) { return C.profiles[k].theta; }).sort(function (a, b) { return b - a; });
    return arr.indexOf(C.profiles[sid].theta) + 1;
  }

  /* ---------- 3. 横向对比 ---------- */
  PAGES.compare = function (arg, query) {
    var ov = C.overview, unit = query.unit && UNITS.indexOf(query.unit) >= 0 ? query.unit : ov.weak_units[0] || UNITS[0];
    var picked = (query.s || '').split(',').filter(function (x) { return C.profiles[x]; }).slice(0, 3);
    if (!picked.length) picked = [C.students[0].id, C.students[1].id];
    var h = '<div class="page-head"><div><h1 class="page-title">横向对比</h1><div class="page-desc">按板块看全班分布与排名；选 2～3 名学生叠加雷达对比</div></div></div>';
    h += '<div class="card mb"><div class="filters"><label>板块 <select class="select" id="cmp-unit">' + UNITS.map(function (u) { return '<option value="' + esc(u) + '"' + (u === unit ? ' selected' : '') + '>' + esc(u) + '</option>'; }).join('') + '</select></label><span class="muted small" id="cmp-stat"></span></div>' +
      '<div class="grid cols-3" style="margin-bottom:0"><div><div class="card-sub">全班掌握度分布（箱线图 + 直方图）</div><div class="chart" id="cmp-dist"></div></div><div class="span-2"><div class="card-sub">排名表（按掌握度降序，点击姓名进入档案）</div><div class="table-scroll" style="max-height:300px" id="cmp-table"></div></div></div></div>';
    h += '<div class="card"><div class="card-title">学生雷达叠加</div><div class="card-sub">点选 2～3 名学生（再点取消）</div><div id="cmp-pick" class="mb">' + C.students.map(function (s) { return '<span class="chip pick' + (picked.indexOf(s.id) >= 0 ? ' on' : '') + '" data-id="' + s.id + '">' + esc(s.name) + '</span>'; }).join('') + '</div>' +
      '<div class="grid cols-2" style="margin-bottom:0"><div><div class="card-sub">板块掌握度</div><div class="chart tall" id="cmp-radar-u"></div></div><div><div class="card-sub">六大素养</div><div class="chart tall" id="cmp-radar-c"></div></div></div>' +
      '<div class="table-scroll mt" id="cmp-stu-table"></div></div>';
    view.innerHTML = h;
    function nav() { location.hash = '#/compare?unit=' + encodeURIComponent(unit) + '&s=' + picked.join(','); }
    byId('cmp-unit').addEventListener('change', function () { unit = this.value; nav(); });
    byId('cmp-pick').addEventListener('click', function (e) {
      var c = e.target.closest('.chip'); if (!c) return;
      var id = c.dataset.id, i = picked.indexOf(id);
      if (i >= 0) { if (picked.length <= 1) return; picked.splice(i, 1); } else { if (picked.length >= 3) picked.shift(); picked.push(id); }
      nav();
    });
    // 分布
    var rows = C.students.map(function (s) { var u = C.profiles[s.id].units.filter(function (x) { return x.unit === unit; })[0]; return { id: s.id, name: s.name, m: u.mastery, p: u.percentile, d: u.delta, e: u.evidence }; }).sort(function (a, b) { return b.m - a.m; });
    var vals = rows.map(function (r) { return r.m; }).slice().sort(function (a, b) { return a - b; });
    var box = [vals[0], quantile(vals, .25), quantile(vals, .5), quantile(vals, .75), vals[vals.length - 1]];
    var bins = []; for (var i = 0; i < 10; i++) bins.push(0);
    vals.forEach(function (v) { bins[Math.min(9, Math.floor(v * 10))]++; });
    byId('cmp-stat').textContent = '均值 ' + pct(mean(vals)) + ' · 中位数 ' + pct(box[2]) + ' · 四分位 ' + pct(box[1]) + '～' + pct(box[3]) + ' · 极差 ' + pct(box[0]) + '～' + pct(box[4]);
    chart('cmp-dist', {
      tooltip: { trigger: 'item' },
      grid: [{ left: 40, right: 12, top: 10, height: 50 }, { left: 40, right: 12, top: 80, bottom: 30 }],
      xAxis: [{ gridIndex: 0, type: 'value', min: 0, max: 1, show: false }, { gridIndex: 1, type: 'category', data: bins.map(function (_, i) { return (i * 10) + '–' + (i * 10 + 10) + '%'; }), axisLabel: { fontSize: 10, interval: 0, rotate: 30 } }],
      yAxis: [{ gridIndex: 0, type: 'category', data: ['分布'], show: false }, { gridIndex: 1, type: 'value', name: '人数', minInterval: 1 }],
      series: [
        { type: 'boxplot', xAxisIndex: 0, yAxisIndex: 0, data: [box], itemStyle: { color: '#e4effc', borderColor: '#2a78d6' }, tooltip: { formatter: function () { return '最小 ' + pct(box[0]) + '<br>Q1 ' + pct(box[1]) + '<br>中位 ' + pct(box[2]) + '<br>Q3 ' + pct(box[3]) + '<br>最大 ' + pct(box[4]); } } },
        { type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: bins, itemStyle: { borderRadius: [4, 4, 0, 0] }, barCategoryGap: '15%', tooltip: { formatter: function (p) { return p.name + '：' + p.value + ' 人'; } } }
      ]
    });
    byId('cmp-table').innerHTML = '<table class="table"><thead><tr><th>#</th><th>学生</th><th>掌握度</th><th class="num">百分位</th><th class="num">相对偏移 δ</th><th class="num">证据量</th></tr></thead><tbody>' +
      rows.map(function (r, i) { return '<tr><td>' + (i + 1) + '</td><td><a href="#/student/' + r.id + '">' + esc(r.name) + '</a> <span class="muted small">' + r.id + '</span></td><td><span class="bar-inline" style="width:' + Math.round(r.m * 120) + 'px"></span>' + pct(r.m) + '</td><td class="num">P' + Math.round(r.p * 100) + '</td><td class="num" style="color:' + (r.d < 0 ? '#a32626' : '#006300') + '">' + (r.d >= 0 ? '+' : '') + fix(r.d, 2) + '</td><td class="num">' + fix(r.e) + '</td></tr>'; }).join('') + '</tbody></table>';
    // 雷达叠加
    var ps = picked.map(function (id) { return C.profiles[id]; });
    chart('cmp-radar-u', radarOpt(UNITS, ps.map(function (p, i) { return { name: p.name, value: p.units.map(function (u) { return u.mastery; }), color: PAL[i] }; }).concat([{ name: '班级均值', value: ps[0].units.map(function (u) { return u.class_mean; }), dashed: true, color: '#898781' }])));
    chart('cmp-radar-c', radarOpt(COMPS, ps.map(function (p, i) { return { name: p.name, value: p.competencies.map(function (u) { return u.mastery; }), color: PAL[i] }; }).concat([{ name: '班级均值', value: ps[0].competencies.map(function (u) { return u.class_mean; }), dashed: true, color: '#898781' }])));
    byId('cmp-stu-table').innerHTML = '<table class="table"><thead><tr><th>板块</th>' + ps.map(function (p) { return '<th class="num">' + esc(p.name) + '</th>'; }).join('') + '<th class="num">班级均值</th></tr></thead><tbody>' +
      UNITS.map(function (u, i) { return '<tr><td>' + esc(u) + '</td>' + ps.map(function (p) { return '<td class="num">' + pct(p.units[i].mastery) + ' <span class="muted small">P' + Math.round(p.units[i].percentile * 100) + '</span></td>'; }).join('') + '<td class="num">' + pct(ps[0].units[i].class_mean) + '</td></tr>'; }).join('') +
      '<tr><td><b>总体能力 θ</b></td>' + ps.map(function (p) { return '<td class="num"><b>' + fix(p.theta, 2) + '</b></td>'; }).join('') + '<td class="num">0.00</td></tr></tbody></table>';
  };

  /* ---------- 4. 试卷分析 ---------- */
  PAGES.papers = function (arg, query) {
    var all = C.paper_analysis.concat([C.next_paper.analysis]);
    var cur = query.exam && all.some(function (a) { return a.id === query.exam; }) ? query.exam : all[0].id;
    var a = all.filter(function (x) { return x.id === cur; })[0];
    var exam = (C.exams.concat([C.next_paper.exam])).filter(function (e) { return e.id === cur; })[0];
    var h = '<div class="page-head"><div><h1 class="page-title">试卷分析</h1><div class="page-desc">单卷：板块分值占比对照高考参考分布、主题与素养占比、难度曲线；多卷：覆盖矩阵与累计覆盖</div></div></div>';
    h += '<div class="tabs">' + all.map(function (x) { return '<button class="' + (x.id === cur ? 'on' : '') + '" data-exam="' + x.id + '">' + esc(x.title) + '</button>'; }).join('') + '</div>';
    h += '<div class="stage-note"><b>' + esc(exam.title) + '</b>' + (exam.date ? ' · ' + esc(exam.date) : '') + ' · 阶段「' + esc(exam.stage) + '」 · 模板 ' + esc(exam.template) + ' · ' + esc(exam.stage_note) + '</div>';
    h += '<div class="grid cols-4 kpis">' + kpi('总分', a.total, '分', exam.items.length + ' 题', '#2a78d6', '▤') + kpi('平均难度', fix(a.mean_difficulty, 2), '', '0 易 ～ 1 难', '#eb6834', '◔') + kpi('覆盖教材小节', a.sections_covered.length, '节', '覆盖板块 ' + Object.keys(a.unit_share).filter(function (u) { return a.unit_share[u] > 0; }).length + ' / ' + UNITS.length, '#1baf7a', '▣') +
      '<div class="card kpi"><div class="kpi-label">板块覆盖判断</div><div class="small mt"><span class="muted">未覆盖</span> ' + (a.gaps.length ? a.gaps.map(function (u) { return '<span class="chip bad">' + esc(u) + '</span>'; }).join('') : '<span class="chip good">无</span>') + '</div><div class="small"><span class="muted">偏多</span> ' + (a.over.length ? a.over.map(function (u) { return '<span class="chip orange">' + esc(u) + '</span>'; }).join('') : '<span class="chip gray">无</span>') + '</div><div class="small"><span class="muted">偏少</span> ' + (a.under && a.under.length ? a.under.map(function (u) { return '<span class="chip violet">' + esc(u) + '</span>'; }).join('') : '<span class="chip gray">无</span>') + '</div></div></div>';
    h += '<div class="grid cols-2">' + cardHtml('板块分值占比 vs 高考参考', '参考分布 = 题库中历年高考卷的平均板块占比', '<div class="chart" id="p-unit"></div>') + cardHtml('难度曲线', '按题号的难度（0 易 ～ 1 难），颜色区分题型；虚线 = 全卷平均', '<div class="chart" id="p-curve"></div>') + '</div>';
    h += '<div class="grid cols-3">' + cardHtml('主题占比', '课标四大主题', '<div class="chart short" id="p-theme"></div>') + cardHtml('素养占比', '六大核心素养', '<div class="chart short" id="p-comp"></div>') + cardHtml('覆盖的教材小节', a.sections_covered.length + ' 节', '<ul class="section-list" style="max-height:220px;overflow:auto">' + a.sections_covered.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ul>') + '</div>';
    if (cur === 'NEXT') {
      h += '<div class="card mb"><div class="card-title">下一轮冲刺卷（系统自动组卷）· 题目列表</div><div class="card-sub">按阶段「' + esc(exam.stage) + '」的难度梯度，从题库中自动选题，优先覆盖前几次考试未覆盖的内容；点击题号展开题干</div><div id="next-list"></div></div>';
    } else {
      h += '<div class="card mb"><div class="card-title">本卷题目与全班得分率</div><div class="card-sub">点击题号展开题干</div><div id="next-list"></div></div>';
    }
    var pc = C.paper_compare;
    h += '<div class="grid cols-2"><div class="card span-2"><div class="card-title">多次考试覆盖矩阵</div><div class="card-sub">板块 × 考试的分值占比；右侧：累计覆盖板块数' + (pc.never_tested.length ? '；从未考到：' + pc.never_tested.map(esc).join('、') : '；所有板块均已考到') + '</div><div class="grid cols-3" style="margin-bottom:0"><div class="span-2"><div class="chart tall" id="p-matrix"></div></div><div><div class="chart tall" id="p-cum"></div></div></div></div></div>';
    view.innerHTML = h;
    view.querySelector('.tabs').addEventListener('click', function (e) { var b = e.target.closest('button[data-exam]'); if (b) location.hash = '#/papers?exam=' + b.dataset.exam; });

    chart('p-unit', {
      tooltip: { trigger: 'axis', valueFormatter: function (v) { return pct(v, 1); } }, legend: { bottom: 0, icon: 'circle' }, grid: { left: 8, right: 12, top: 16, bottom: 54, containLabel: true },
      xAxis: AXIS_UNITS, yAxis: { type: 'value', axisLabel: { formatter: function (v) { return Math.round(v * 100) + '%'; } } },
      series: [{ name: '本卷占比', type: 'bar', data: UNITS.map(function (u) { return a.unit_share[u] || 0; }), itemStyle: { borderRadius: [4, 4, 0, 0] } }, { name: '高考参考', type: 'bar', data: UNITS.map(function (u) { return a.gaokao_ref[u] || 0; }), itemStyle: { color: '#c3c2b7', borderRadius: [4, 4, 0, 0] } }]
    });
    var types = uniq(a.curve.map(function (c) { return c.type; }));
    chart('p-curve', {
      tooltip: { trigger: 'axis', formatter: function (ps) { var c = a.curve[ps[0].dataIndex]; var q = QMAP.get(c.qid); return '第 ' + c.no + ' 题 · ' + c.type + ' · ' + c.score + ' 分<br>' + c.qid + (q ? '（' + q.units.join('、') + '）' : '') + '<br>难度 ' + fix(c.difficulty, 2) + (C.item_rate[c.qid] != null && cur !== 'NEXT' ? '<br>全班得分率 ' + pct(C.item_rate[c.qid]) : ''); } },
      legend: { bottom: 0, icon: 'circle' }, grid: { left: 8, right: 12, top: 16, bottom: 30, containLabel: true },
      xAxis: { type: 'category', data: a.curve.map(function (c) { return c.no; }), name: '题号' }, yAxis: { type: 'value', min: 0, max: 1 },
      series: [{ name: '难度', type: 'line', data: a.curve.map(function (c) { return c.difficulty; }), symbol: 'none', lineStyle: { width: 2, color: '#c3c2b7' }, markLine: { silent: true, symbol: 'none', data: [{ yAxis: a.mean_difficulty }], lineStyle: { type: 'dashed', color: '#898781' }, label: { position: 'insideEndTop', formatter: '平均 ' + fix(a.mean_difficulty, 2), color: '#52514e' } } }].concat(types.map(function (t, i) {
        return { name: t, type: 'scatter', symbolSize: 10, itemStyle: { color: PAL[i] }, data: a.curve.map(function (c) { return c.type === t ? c.difficulty : null; }) };
      }))
    });
    chart('p-theme', pieOpt(mapPct(a.theme_share), ['38%', '66%']));
    chart('p-comp', pieOpt(mapPct(a.competency_share), ['38%', '66%']));
    // 题目列表
    var lst = byId('next-list');
    lst.innerHTML = '<table class="table"><thead><tr><th>#</th><th>题号</th><th>题型</th><th class="num">分值</th><th class="num">难度</th>' + (cur !== 'NEXT' ? '<th class="num">全班得分率</th>' : '') + '<th>板块</th><th>来源</th></tr></thead><tbody>' +
      a.curve.map(function (c) { var q = QMAP.get(c.qid); return '<tr><td>' + c.no + '</td><td><a href="#" data-open="' + esc(c.qid) + '">' + esc(c.qid) + '</a></td><td>' + esc(c.type) + '</td><td class="num">' + c.score + '</td><td class="num">' + fix(c.difficulty, 2) + '</td>' + (cur !== 'NEXT' ? '<td class="num">' + pct(C.item_rate[c.qid]) + '</td>' : '') + '<td>' + (q ? q.units.map(chipUnit).join('') : '') + '</td><td class="small muted">' + (q ? esc(q.region + ' ' + q.year + ' ' + q.kind) : '') + '</td></tr><tr style="display:none" data-row="' + esc(c.qid) + '"><td colspan="8"></td></tr>'; }).join('') + '</tbody></table>';
    lst.addEventListener('click', function (e) {
      var a2 = e.target.closest('a[data-open]'); if (!a2) return; e.preventDefault();
      var tr = lst.querySelector('tr[data-row="' + a2.dataset.open + '"]'), td = tr.firstElementChild;
      if (tr.style.display === 'none') { if (!td.innerHTML) { td.innerHTML = questionCard(QMAP.get(a2.dataset.open), '', { toggles: true }); tex(td); } tr.style.display = ''; } else tr.style.display = 'none';
    });
    bindToggles(lst);
    // 覆盖矩阵
    var mdata = [], mu = Object.keys(pc.matrix);
    mu.forEach(function (u, ui) { pc.matrix[u].forEach(function (v, ei) { mdata.push([ei, ui, v]); }); });
    var mx = Math.max.apply(null, mdata.map(function (d) { return d[2]; }));
    chart('p-matrix', {
      tooltip: { formatter: function (p) { return mu[p.data[1]] + ' · ' + pc.exams[p.data[0]] + '：' + pct(p.data[2], 1); } },
      grid: { left: 8, right: 70, top: 8, bottom: 8, containLabel: true },
      xAxis: { type: 'category', data: pc.exams.map(function (e) { var ex = C.exams.filter(function (x) { return x.id === e; })[0]; return ex ? ex.title.replace('高三', '') : e; }) },
      yAxis: { type: 'category', data: mu, inverse: true, axisLabel: { fontSize: 11 } },
      visualMap: { min: 0, max: mx, right: 0, top: 'middle', orient: 'vertical', itemHeight: 120, inRange: { color: SEQ }, formatter: function (v) { return Math.round(v * 100) + '%'; }, textStyle: { fontSize: 10 } },
      series: [{ type: 'heatmap', data: mdata, label: { show: true, formatter: function (p) { return p.data[2] ? Math.round(p.data[2] * 100) + '%' : '—'; }, fontSize: 10, color: '#0b0b0b' }, itemStyle: { borderColor: '#fff', borderWidth: 1 } }]
    });
    chart('p-cum', {
      tooltip: { trigger: 'axis' }, grid: { left: 8, right: 16, top: 46, bottom: 8, containLabel: true }, title: { text: '累计覆盖板块数', left: 'center', top: 4 },
      xAxis: { type: 'category', data: pc.exams, boundaryGap: false }, yAxis: { type: 'value', min: 0, max: UNITS.length, minInterval: 1 },
      series: [{ type: 'line', data: pc.cumulative_units, symbolSize: 8, lineStyle: { width: 2, color: '#1baf7a' }, itemStyle: { color: '#1baf7a' }, areaStyle: { opacity: .1 }, label: { show: true, position: 'top', color: '#52514e' } }]
    });
  };
  function mapPct(obj) { var o = {}; Object.keys(obj).forEach(function (k) { o[k] = Math.round(obj[k] * 1000) / 10; }); return o; }

  /* ---------- 5. 题库 ---------- */
  PAGES.bank = function (arg, query) {
    var Q = B.questions, PAGE = 20;
    var f = { region: query.region || '', year: query.year || '', type: query.type || '', unit: query.unit || '', paper: query.paper || '', kw: query.kw || '', page: parseInt(query.page || '1', 10) || 1 };
    function sel(id, label, opts, val) { return '<label>' + label + ' <select class="select" id="' + id + '"><option value="">全部</option>' + opts.map(function (o) { return '<option value="' + esc(o.v) + '"' + (String(o.v) === String(val) ? ' selected' : '') + '>' + esc(o.t) + '</option>'; }).join('') + '</select></label>'; }
    var h = '<div class="page-head"><div><h1 class="page-title">题库</h1><div class="page-desc">' + B.stats.papers + ' 套试卷 · ' + B.stats.questions + ' 题 · 题干 / 答案 / 详解 / 题眼</div></div></div>';
    h += '<div class="card mb"><div class="filters">' +
      sel('f-region', '地区', Object.keys(B.stats.by_region).map(function (r) { return { v: r, t: r + '（' + B.stats.by_region[r] + '）' }; }), f.region) +
      sel('f-year', '年份', B.stats.years.map(function (y) { return { v: y, t: y }; }), f.year) +
      sel('f-type', '题型', Object.keys(B.stats.by_type).map(function (t) { return { v: t, t: t + '（' + B.stats.by_type[t] + '）' }; }), f.type) +
      sel('f-unit', '板块', UNITS.map(function (u) { return { v: u, t: u + '（' + (B.stats.by_unit[u] || 0) + '）' }; }), f.unit) +
      sel('f-paper', '试卷', B.papers.map(function (p) { return { v: p.id, t: p.title + '（' + p.count + '）' }; }), f.paper) +
      '<label>关键词 <input type="text" id="f-kw" value="' + esc(f.kw) + '" placeholder="题干 / 题眼 / 小节，回车搜索"></label><button class="btn primary sm" id="f-go">筛选</button><button class="btn sm" id="f-clear">清空</button></div>' +
      '<div class="grid cols-4" style="margin-bottom:0"><div><div class="chart short" id="b-region"></div></div><div><div class="chart short" id="b-type"></div></div><div><div class="chart short" id="b-year"></div></div><div><div class="chart short" id="b-unit"></div></div></div></div>';
    h += '<div id="bank-result"></div>';
    view.innerHTML = h;
    function go() {
      var p = { region: byId('f-region').value, year: byId('f-year').value, type: byId('f-type').value, unit: byId('f-unit').value, paper: byId('f-paper').value, kw: byId('f-kw').value.trim() };
      location.hash = '#/bank?' + Object.keys(p).filter(function (k) { return p[k]; }).map(function (k) { return k + '=' + encodeURIComponent(p[k]); }).join('&');
    }
    byId('f-go').addEventListener('click', go);
    byId('f-kw').addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
    ['f-region', 'f-year', 'f-type', 'f-unit', 'f-paper'].forEach(function (id) { byId(id).addEventListener('change', go); });
    byId('f-clear').addEventListener('click', function () { location.hash = '#/bank'; });
    var kw = f.kw.toLowerCase();
    var res = Q.filter(function (q) {
      if (f.region && q.region !== f.region) return false;
      if (f.year && String(q.year) !== String(f.year)) return false;
      if (f.type && q.type !== f.type) return false;
      if (f.unit && q.units.indexOf(f.unit) < 0) return false;
      if (f.paper && q.paper !== f.paper) return false;
      if (kw) { var txt = (plainText(q.stem_html) + ' ' + q.tiyan_tag + ' ' + (q.tiyan || []).join(' ') + ' ' + q.id + ' ' + (q.sections || []).map(function (s) { return s.name + s.detail; }).join(' ')).toLowerCase(); if (txt.indexOf(kw) < 0) return false; }
      return true;
    });
    var cnt = function (arr, key) { var o = {}; arr.forEach(function (q) { var ks = key === 'units' ? q.units : [q[key]]; ks.forEach(function (k) { o[k] = (o[k] || 0) + 1; }); }); return o; };
    var barOpt = function (title, obj, order) {
      var keys = order ? order.filter(function (k) { return obj[k]; }) : Object.keys(obj);
      return { title: { text: title, left: 'center', top: 0 }, tooltip: { trigger: 'axis' }, grid: { left: 6, right: 6, top: 28, bottom: 6, containLabel: true }, xAxis: { type: 'category', data: keys, axisLabel: { fontSize: 10, interval: 0, rotate: keys.length > 4 ? 35 : 0 } }, yAxis: { type: 'value', minInterval: 1 }, series: [{ type: 'bar', data: keys.map(function (k) { return obj[k]; }), itemStyle: { borderRadius: [3, 3, 0, 0] }, barMaxWidth: 28, label: { show: keys.length <= 8, position: 'top', fontSize: 10, color: '#52514e' } }] };
    };
    chart('b-region', barOpt('按地区（当前筛选）', cnt(res, 'region')));
    chart('b-type', barOpt('按题型', cnt(res, 'type'), ['填空', '单选', '多选', '解答']));
    chart('b-year', barOpt('按年份', cnt(res, 'year'), B.stats.years.map(String)));
    chart('b-unit', barOpt('按板块', cnt(res, 'units'), UNITS));
    var pages = Math.max(1, Math.ceil(res.length / PAGE)); if (f.page > pages) f.page = pages;
    var slice = res.slice((f.page - 1) * PAGE, f.page * PAGE);
    function pager() {
      var s = '<div class="pager"><span class="muted small">共 ' + res.length + ' 题 · 第 ' + f.page + ' / ' + pages + ' 页</span>';
      for (var i = 1; i <= pages; i++) { if (pages > 12 && Math.abs(i - f.page) > 3 && i !== 1 && i !== pages) { if (Math.abs(i - f.page) === 4) s += '<span class="muted">…</span>'; continue; } s += '<button class="btn sm' + (i === f.page ? ' cur' : '') + '" data-page="' + i + '">' + i + '</button>'; }
      return s + '</div>';
    }
    var r = byId('bank-result');
    r.innerHTML = pager() + (slice.length ? slice.map(function (q) { var pp = B.papers.filter(function (x) { return x.id === q.paper; })[0]; return questionCard(q, '<span class="muted">' + esc(pp ? pp.title : q.paper) + ' 第 ' + q.no + ' 题</span>', { toggles: true }); }).join('') : '<div class="card empty">没有符合条件的题目</div>') + pager();
    r.addEventListener('click', function (e) { var b = e.target.closest('button[data-page]'); if (b) { var hh = location.hash.replace(/[&?]page=\d+/, ''); location.hash = hh + (hh.indexOf('?') >= 0 ? '&' : '?') + 'page=' + b.dataset.page; } });
    bindToggles(r);
    tex(r);
  };

  /* ---------- 6. 学生练习 ---------- */
  function loadState(sid) { try { return JSON.parse(localStorage.getItem('mi_practice_' + sid)) || { records: {}, goal: 5 }; } catch (e) { return { records: {}, goal: 5 }; } }
  function saveState(sid, st) { try { localStorage.setItem('mi_practice_' + sid, JSON.stringify(st)); } catch (e) { } }

  /* ---------- AI 学伴：学情上下文包（复制到任意大模型应用） ----------
     用题库原始 HTML 生成纯文本（保留 $…$ 公式），不含姓名、学号、班级名。
     提交前的包不含答案和详解。 */
  var FIG_NOTE = '【此处有图，见数鉴网页；可截图一起发给 AI】';
  function htmlToText(html) {
    var s = String(html || '').replace(/<span class="inf">[\s\S]*?<\/span>/gi, '');
    s = s.replace(/<svg[\s\S]*?<\/svg>/gi, FIG_NOTE).replace(/<img[^>]*>/gi, FIG_NOTE).replace(/<figcaption[\s\S]*?<\/figcaption>/gi, '');
    s = s.replace(/<\/(td|th)>/gi, ' | ').replace(/<\/tr>/gi, '\n').replace(/<br\s*\/?>/gi, '\n').replace(/<li[^>]*>/gi, '\n· ');
    s = s.replace(/<\/(p|div|li|h\d|figure|table|ul|ol)>/gi, '\n').replace(/<[^>]+>/g, '');
    s = s.replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
    s = s.replace(/(【此处有图[^】]*】\s*)+/g, FIG_NOTE + '\n');
    return s.split('\n').map(function (l) { return l.replace(/[ \t]+$/g, '').replace(/^\s*\|\s*/, '').replace(/\s*\|$/, ''); }).join('\n').replace(/\n{3,}/g, '\n\n').trim();
  }
  function cut(s, n) { return s.length > n ? s.slice(0, n).replace(/\s+\S*$/, '') + '……（已截断，完整内容见数鉴网页）' : s; }
  function diffWord(d) { d = +d; return d < 0.4 ? '易' : d < 0.65 ? '中' : '难'; }
  function siteBase() { return location.href.split('#')[0]; }
  function paperTitle(q) { var pp = B.papers.filter(function (x) { return x.id === q.paper; })[0]; return pp ? pp.title.replace(/普通高等学校招生全国统一考试/, '高考') : q.paper; }
  function aiWho(p, txt) { return String(txt || '').split(p.name).join('该生'); }
  var AI_INTRO = '我是一名高三学生，在用「数鉴」系统做数学练习。下面是系统整理的我的学情和题目信息（班级为虚构示例数据），请你当我的数学老师，一对一辅导我。数学式子请用 LaTeX 写。';

  function aiStudentText(p, unit) {
    var L = [], n = C.students.length;
    L.push('· 历次考试（满分 ' + p.trend[0].full + '，全班 ' + n + ' 人）：' + p.trend.map(function (t) { return examShort(t.title).replace('高三', '') + ' ' + t.total + ' 分、第 ' + t.rank + ' 名（班均 ' + fix(t.class_mean) + '）'; }).join('；'));
    var um = {}; p.units.forEach(function (u) { um[u.unit] = u; });
    var uTxt = function (u) { var x = um[u]; return x ? u + '（掌握度 ' + pct(x.mastery) + '，班级平均 ' + pct(x.class_mean) + '）' : u; };
    L.push('· 薄弱板块：' + p.weak.map(uTxt).join('、'));
    L.push('· 较强板块：' + p.strong.join('、'));
    var cs = p.competencies.slice().sort(function (a, b) { return (a.mastery - a.class_mean) - (b.mastery - b.class_mean); }).slice(0, 2);
    L.push('· 核心素养中相对最弱：' + cs.map(function (c) { return c.competency + '（' + pct(c.mastery) + '，班级平均 ' + pct(c.class_mean) + '）'; }).join('、'));
    var es = Object.keys(p.errors).sort(function (a, b) { return p.errors[b] - p.errors[a]; });
    if (es.length) L.push('· 考试中老师标注的错因：' + es.map(function (k) { return k + ' ' + p.errors[k] + ' 次'; }).join('、'));
    if (p.comments.length) L.push('· 老师评语：' + p.comments.map(function (c) { return aiWho(p, c.text); }).join(''));
    if (unit && um[unit] && p.weak.indexOf(unit) < 0) L.push('· 本题所在板块：' + uTxt(unit));
    return L.join('\n');
  }
  function aiClassText() {
    var ov = C.overview, last = C.exams[C.exams.length - 1], np = C.next_paper && C.next_paper.exam;
    var L = ['· 已考完 ' + C.exams.map(function (e) { return examShort(e.title).replace('高三', ''); }).join('、') + '（最近一次 ' + last.date + '）' + (np ? '；下一轮练习卷为' + np.stage + '阶段（' + np.stage_note.replace(/^[^：]*：/, '') + '）' : '')];
    L.push('· 全班薄弱板块：' + ov.weak_units.map(function (u) { var d = ov.units.filter(function (x) { return x.unit === u; })[0]; return u + '（全班得分率 ' + pct(d.rate) + '）'; }).join('、'));
    return L.join('\n');
  }
  function aiQuestionText(q, it) {
    var L = ['题目：' + paperTitle(q) + ' 第 ' + q.no + ' 题（' + q.type + '，' + q.score + ' 分，难度' + diffWord(q.difficulty) + '）'];
    L.push('知识点：' + (q.sections || []).map(function (s) { return s.book + ' ' + s.sec + ' ' + s.name + (s.detail ? '（' + s.detail + '）' : ''); }).join('；') + '；板块：' + q.units.join('、'));
    if (C.item_rate && C.item_rate[q.id] != null) L.push('全班这道题的得分率：' + pct(C.item_rate[q.id]));
    L.push('题干：\n' + htmlToText(q.stem_html));
    return L.join('\n');
  }
  function aiHintsText(it, q) {
    var lv = (it && it.hints ? it.hints : []).slice();
    (q.tiyan || []).forEach(function (t) { lv.push('题眼：' + htmlToText(t)); });
    return lv.map(function (t, i) { return (i + 1) + '. ' + htmlToText(t); }).join('\n');
  }
  function aiRecordText(q, rec) {
    var auto = rec.auto === 'num' || q.type === '单选' || q.type === '多选';
    var txt = { right: '全对', partial: '部分正确', wrong: auto ? '错误' : '不会或做错' }[rec.result];
    var mine = rec.answer || rec.text || '';
    return '我的作答：' + (mine ? mine : '（没写）') + '\n数鉴判定：' + txt + (auto ? '（系统自动判分）' : '（我对照答案自评）') + '；用了 ' + (rec.hints || 0) + ' 级提示';
  }
  function aiSimilar(q, st, k) {
    var u = q.units[0], secs = (q.sections || []).map(function (s) { return s.name; });
    return B.questions.filter(function (x) { return x.id !== q.id && x.units.indexOf(u) >= 0 && !(st.records || {})[x.id] && !/<svg|<img/i.test(x.stem_html); })
      .map(function (x) { var same = (x.sections || []).some(function (s) { return secs.indexOf(s.name) >= 0; }); return { q: x, c: Math.abs(x.difficulty - q.difficulty) - (same ? 0.3 : 0) + (x.type === q.type ? 0 : 0.1) }; })
      .sort(function (a, b) { return a.c - b.c; }).slice(0, k).map(function (o) { return o.q; });
  }
  var AI_SCENES = {
    stuck: { label: '卡住了，要提示', pre: true },
    explain: { label: '讲解与一题多解' },
    diagnose: { label: '帮我找错因', needWrong: true },
    more: { label: '举一反三' }
  };
  function aiPackPractice(scene, p, it, q, rec, st, liveText) {
    var S = [AI_INTRO, '', '【我的情况】', aiStudentText(p, it.unit), '', '【班级与阶段】', aiClassText(), '', '【这道题】', aiQuestionText(q, it)];
    if (scene === 'stuck') {
      if (liveText && liveText.trim()) S.push('', '我目前写到：' + liveText.trim());
      S.push('', '【请你这样帮我】',
        '1. 先问我想到了哪一步、卡在哪里，再给提示。',
        '2. 提示一次只给一级：先指方向，再点出卡点，最后才帮我打通关键一步。不要给出最终答案或完整解答，我会回数鉴提交判分。',
        '3. 结合我的弱项和常见错因提醒我（比如该检查哪里）。');
      var hs = aiHintsText(it, q);
      if (hs) S.push('', '【老师预先写好的提示阶梯（供你参考，我要提示时一次只给一级）】', hs);
      return S.join('\n');
    }
    S.push('', aiRecordText(q, rec), '核对过的答案：' + htmlToText(q.answer_html));
    if (q.solution_html) S.push('', '【数鉴的参考详解（已人工核对）】', cut(htmlToText(String(q.solution_html).replace(/<p class="note">说明：[\s\S]*?<\/p>/g, '')), 900));
    S.push('', '【请你这样帮我】');
    if (scene === 'explain') S.push(
      '1. 用我能听懂的话讲清这题的关键一步（为什么想到这样做）。',
      '2. 给出 2–3 种不同解法：考场常规解法、更本质的解法、可能的巧解；比较各自适用的情形，说明考场上选哪种。',
      '3. 每种解法的最终结论必须和上面「核对过的答案」一致。如果某种解法算出来不一致，请明确标出，不要硬凑。',
      '4. 结合我的弱项和常见错因，说说这类题以后要注意什么。',
      '5. 最后出一道同类变式题让我做，先不要给答案。');
    else if (scene === 'diagnose') S.push(
      '1. 根据我的作答推测我可能错在哪一步；如果看不出来，先问我一两个问题。',
      '2. 对照我的历史错因，判断这次是偶然失误还是老问题。',
      '3. 给出针对性的订正方法（不超过 3 条），并以「核对过的答案」为准检查你的分析。');
    else {
      var sim = aiSimilar(q, st, 2);
      S.push('1. 先用两三句话点出这题的方法要点。',
        '2. 然后带我做下面的同类题，一次一道：等我给出答案和过程后再点评，不要提前说答案。',
        '3. 你拿不准对错时，让我到数鉴题库核对（链接在每题后面）。');
      sim.forEach(function (x, i) { S.push('', '【同类题 ' + (i + 1) + '】' + paperTitle(x) + ' 第 ' + x.no + ' 题（' + x.type + '，难度' + diffWord(x.difficulty) + '）', htmlToText(x.stem_html), '核对：' + siteBase() + '#/bank?kw=' + encodeURIComponent(x.id)); });
    }
    return S.join('\n');
  }
  function aiPackReview(p, st) {
    var S = [AI_INTRO, '', '【我的情况】', aiStudentText(p), '', '【班级与阶段】', aiClassText()];
    var all = [], recs = st.records || {};
    p.practice.groups.forEach(function (g) { g.items.forEach(function (i) { if (QMAP.get(i.qid)) all.push({ g: g, i: i, q: QMAP.get(i.qid), r: recs[i.qid] }); }); });
    var done = all.filter(function (x) { return x.r; });
    S.push('', '【我在数鉴的练习记录】');
    if (done.length) {
      var right = done.filter(function (x) { return x.r.result === 'right'; }).length, nohint = done.filter(function (x) { return !x.r.hints && !x.r.ai; }).length;
      S.push('· 推荐练习 ' + all.length + ' 题，已做 ' + done.length + ' 题，全对 ' + right + ' 题；不看提示、不借助 AI 独立完成 ' + nohint + ' 题');
      p.practice.groups.forEach(function (g) { var d = done.filter(function (x) { return x.g === g; }); if (d.length) S.push('· ' + g.unit + '：做了 ' + d.length + ' 题，' + d.map(function (x) { return x.q.id + ' ' + { right: '对', partial: '半对', wrong: '错' }[x.r.result]; }).join('、')); });
    } else S.push('· 还没开始做推荐练习');
    S.push('', '【数鉴推荐给我的练习题（题号 · 板块 · 类型 · 难度）】');
    all.forEach(function (x) { S.push('· ' + x.q.id + ' · ' + x.g.unit + ' · ' + x.i.role + ' · ' + diffWord(x.q.difficulty) + (x.r ? ' · 已做' : '')); });
    S.push('', '【请你这样帮我做阶段复盘】',
      '1. 先问我最近的感受：哪类题最没把握、时间够不够。',
      '2. 分析我的成绩和名次走势，指出最该优先补的 1–2 个板块，说明理由（结合掌握度、错因和班级阶段）。',
      '3. 排一份下周练习计划：每天练什么板块、几道题、什么难度，以及每个板块要特别注意的问题。',
      '4. 优先从上面「推荐练习题」里选题（写题号），我会在数鉴里做并自动判分：' + siteBase() + '#/practice',
      '5. 每天留 1–2 道题不用提示、不问 AI，独立完成。');
    return S.join('\n');
  }
  function copyText(text, ok) {
    function fallback() { var t = document.createElement('textarea'); t.value = text; t.style.position = 'fixed'; t.style.opacity = '0'; document.body.appendChild(t); t.select(); var r = false; try { r = document.execCommand('copy'); } catch (e) { } document.body.removeChild(t); ok(r); }
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(function () { ok(true); }, fallback); else fallback();
  }
  function aiLog(sid, st, entry) { st.ai = st.ai || []; st.ai.push(entry); if (st.ai.length > 300) st.ai = st.ai.slice(-300); saveState(sid, st); }
  /* 在 box 里显示包的预览 + 复制按钮 */
  function aiShowPack(box, text, onCopy, what) {
    box.innerHTML = '<div class="ai-pack"><div class="ai-pack-head"><span>下面这段文字包含' + (what || '你的学情和这道题的信息') + '（不含姓名和学号），共 ' + text.length + ' 字。复制后粘到 DeepSeek、豆包、Kimi 等应用里，就能接着问。</span><span class="spacer"></span><button class="btn primary sm" data-ai="copy">复制</button><button class="btn sm" data-ai="close">收起</button></div><textarea class="ai-pack-text" readonly></textarea><div class="ai-pack-msg small muted"></div></div>';
    var ta = box.querySelector('textarea'); ta.value = text;
    box.querySelector('[data-ai="copy"]').addEventListener('click', function () {
      copyText(text, function (r) {
        var m = box.querySelector('.ai-pack-msg');
        if (r) { m.textContent = '已复制。粘到大模型应用里发送即可；做完记得回数鉴提交。'; m.className = 'ai-pack-msg small ok'; if (onCopy) onCopy(); }
        else { ta.focus(); ta.select(); m.textContent = '浏览器不允许自动复制，已全选文字，请按 Ctrl+C 复制。'; m.className = 'ai-pack-msg small warn'; if (onCopy) onCopy(); }
      });
    });
    box.querySelector('[data-ai="close"]').addEventListener('click', function () { box.innerHTML = ''; });
  }

  PAGES.practice = function (sid, query) {
    setLastStudent(sid);
    var p = C.profiles[sid], st = loadState(sid);
    var items = []; p.practice.groups.forEach(function (g) { g.items.forEach(function (it) { if (QMAP.get(it.qid)) items.push({ unit: g.unit, mastery: g.mastery, qid: it.qid, pred: it.pred, role: it.role, hints: it.hints || [], q: QMAP.get(it.qid) }); }); });
    var idx = 0;
    if (query.q) { var k = items.findIndex(function (x) { return x.qid === query.q; }); if (k >= 0) idx = k; }
    else { var k2 = items.findIndex(function (x) { return !st.records[x.qid]; }); if (k2 >= 0) idx = k2; }
    var h = '<div class="page-head"><div><h1 class="page-title">学生练习 · ' + esc(p.name) + ' <span class="muted small">' + sid + '</span></h1><div class="page-desc">先独立思考 → 需要时逐级看提示 → 提交后对照答案 → 最后看详解。提交前不显示答案。</div></div><div class="page-actions"><a class="btn" href="#/student/' + sid + '">查看档案</a><button class="btn" id="pr-reset">清空本人练习记录</button></div></div>';
    h += '<div class="practice-layout"><div><div class="card"><div class="practice-nav" id="pr-nav"></div><div id="pr-q"></div></div></div><div class="card monitor" id="pr-monitor"></div></div>';
    view.innerHTML = h;
    byId('pr-reset').addEventListener('click', function () { if (confirm('清空 ' + p.name + ' 的全部练习记录？')) { st = { records: {}, goal: st.goal }; saveState(sid, st); render(); } });

    var live = { picked: [], hintLevel: 0, submitted: false, text: '' };
    function render() { renderNav(); renderQ(); renderMonitor(); }
    function renderNav() {
      byId('pr-nav').innerHTML = items.map(function (it, i) { var r = st.records[it.qid]; return '<button class="' + (i === idx ? 'cur ' : '') + (r ? r.result : '') + '" data-i="' + i + '" title="' + esc(it.unit + ' · ' + it.qid) + '">' + (i + 1) + '</button>'; }).join('');
    }
    byId('pr-nav').addEventListener('click', function (e) { var b = e.target.closest('button[data-i]'); if (b) { idx = +b.dataset.i; live = { picked: [], hintLevel: 0, submitted: false, text: '' }; render(); } });

    function renderQ() {
      var it = items[idx], q = it.q, rec = st.records[q.id], done = !!rec || live.submitted;
      var choice = q.type === '单选' || q.type === '多选', numq = !choice && hasNumAnswer(q);
      var levels = it.hints.slice(); if (q.tiyan && q.tiyan.length) levels = levels.concat(q.tiyan.map(function (t) { return '【题眼】' + t; }));
      var h2 = '<div class="qcard-head"><span>第 ' + (idx + 1) + ' / ' + items.length + ' 题</span>' + chipUnit(it.unit) + roleBadge(it.role) + '<span class="chip gray">预计得分率 ' + pct(it.pred) + '</span><span class="qid">' + esc(q.id) + '</span>' + qBadges(q) + '<span>' + q.score + ' 分</span></div>';
      h2 += '<div class="qbody" style="font-size:15px">' + (q.stem_html || '') + '</div>';
      if (choice) {
        var ans = answerLetters(q), pickedSet = rec ? rec.answer : live.picked.join('');
        h2 += '<div class="muted small mt">' + (q.type === '多选' ? '多选：选全对得「全对」，只选对一部分且无错选得「部分」，有错选得「错」' : '单选：点选一个选项后提交') + '</div><div class="options">' + ['A', 'B', 'C', 'D'].map(function (L) {
          var cls = 'opt';
          if (done) { if (ans.indexOf(L) >= 0) cls += ' hit'; else if (pickedSet.indexOf(L) >= 0) cls += ' miss'; }
          else if (live.picked.indexOf(L) >= 0) cls += ' on';
          return '<button class="' + cls + '" data-opt="' + L + '"' + (done ? ' disabled' : '') + '>' + L + '</button>';
        }).join('') + '</div>';
      } else if (numq) {
        h2 += '<div class="muted small mt">填空' + (q.answer_num.length > 1 ? '（共 ' + q.answer_num.length + ' 空）' : '') + '：填数值后提交，系统自动判分</div>';
        h2 += '<input class="input num-answer" id="pr-num" autocomplete="off" placeholder="输入数值答案；多空用逗号或分号隔开，可写 1/3、2√3、√2/2、π/6、-0.5" value="' + esc(rec ? rec.answer || '' : live.text) + '"' + (done ? ' disabled' : '') + '>';
        if (live.err && !done) h2 += '<div class="result-box warn" id="pr-num-msg">' + esc(live.err) + '</div>';
      } else {
        h2 += '<textarea class="answer-box" id="pr-text" placeholder="写下你的答案或关键步骤（提交后对照参考答案自评）"' + (done ? ' disabled' : '') + '>' + esc(rec ? rec.text || '' : live.text) + '</textarea>';
      }
      // 提示阶梯
      var shown = rec ? Math.min(rec.hints || 0, levels.length) : live.hintLevel;
      if (levels.length) {
        h2 += '<div id="pr-hints">' + levels.slice(0, shown).map(function (t, i) { return '<div class="hint-box"><span class="lv">提示 ' + (i + 1) + '</span>' + t + '</div>'; }).join('') + '</div>';
      }
      h2 += '<div class="practice-actions">';
      if (!done) {
        h2 += (levels.length ? '<button class="btn" id="pr-hint"' + (shown >= levels.length ? ' disabled' : '') + '>提示（' + shown + '/' + levels.length + '）</button>' : '<span class="muted small">本题暂无提示</span>');
        h2 += '<button class="btn primary" id="pr-submit">提交</button>';
      }
      h2 += '</div>';
      if (!done) h2 += '<div class="ai-row"><span class="muted small">想问大模型？</span><button class="btn sm" data-scene="stuck">卡住了：复制题目和学情给 AI（不含答案）</button></div><div id="pr-ai"></div>';
      if (done) {
        if (rec) {
          var txt = { right: '全对', partial: '部分正确', wrong: '不会 / 错误' }[rec.result];
          h2 += '<div class="result-box ' + rec.result + '">结果：<b>' + txt + '</b>' + (choice ? '（你的选择 ' + (rec.answer || '—') + '，正确答案 ' + answerLetters(q) + '）' : rec.auto === 'num' ? '（你的答案 ' + esc(rec.answer || '—') + '，正确答案 ' + keyAnswerHtml(q) + (rec.marks && rec.marks.length > 1 ? '；' + rec.marks.map(function (ok, i) { return '第 ' + (i + 1) + ' 空' + (ok ? '对' : '错'); }).join('，') : '') + '）' : '') + ' · 用了 ' + (rec.hints || 0) + ' 级提示' + (rec.ai ? ' · 问过 AI 学伴' : '') + ' · ' + dateStr(rec.ts) + '</div>';
          h2 += '<div class="ai-row"><span class="muted small">带上下文问 AI：</span>' + Object.keys(AI_SCENES).filter(function (k) { var sc = AI_SCENES[k]; return !sc.pre && !(sc.needWrong && rec.result === 'right'); }).map(function (k) { return '<button class="btn sm" data-scene="' + k + '">' + AI_SCENES[k].label + '</button>'; }).join('') + '</div><div id="pr-ai"></div>';
        } else {
          h2 += '<div class="result-box pending">已提交，请对照参考答案自评：</div><div class="practice-actions"><button class="btn" data-grade="right">全对</button><button class="btn" data-grade="partial">部分</button><button class="btn" data-grade="wrong">不会</button></div>';
        }
        h2 += '<div class="qsec qbody"><div class="qsec-title">参考答案</div>' + (q.answer_html || '') + '</div>';
        if (q.solution_html) h2 += '<div class="qtoggles"><button class="btn sm" id="pr-sol">查看详解</button></div><div class="qsec qbody" id="pr-sol-box" style="display:none"><div class="qsec-title">详解</div>' + q.solution_html + '</div>';
      }
      h2 += '<div class="practice-actions" style="justify-content:space-between;margin-top:16px"><button class="btn" id="pr-prev"' + (idx === 0 ? ' disabled' : '') + '>上一题</button><button class="btn" id="pr-next"' + (idx >= items.length - 1 ? ' disabled' : '') + '>下一题</button></div>';
      var box = byId('pr-q'); box.innerHTML = h2; tex(box);
      box.querySelectorAll('button[data-opt]').forEach(function (b) { b.addEventListener('click', function () {
        var L = b.dataset.opt;
        if (q.type === '单选') live.picked = [L]; else { var i = live.picked.indexOf(L); if (i >= 0) live.picked.splice(i, 1); else live.picked.push(L); live.picked.sort(); }
        renderQ();
      }); });
      box.querySelectorAll('button[data-scene]').forEach(function (b) { b.addEventListener('click', function () {
        var scene = b.dataset.scene, text = aiPackPractice(scene, p, it, q, st.records[q.id], st, live.text);
        box.querySelectorAll('button[data-scene]').forEach(function (x) { x.classList.toggle('primary', x === b); });
        aiShowPack(byId('pr-ai'), text, function () { if (scene === 'stuck') live.ai = true; aiLog(sid, st, { qid: q.id, scene: scene, ts: Date.now() }); renderMonitor(); });
      }); });
      var hb = byId('pr-hint'); if (hb) hb.addEventListener('click', function () { live.hintLevel++; renderQ(); });
      var ta = byId('pr-text'); if (ta) ta.addEventListener('input', function () { live.text = ta.value; });
      var ni = byId('pr-num'); if (ni) {
        ni.addEventListener('input', function () { live.text = ni.value; });
        ni.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); var b = byId('pr-submit'); if (b) b.click(); } });
      }
      var sb = byId('pr-submit'); if (sb) sb.addEventListener('click', function () {
        if (choice) {
          if (!live.picked.length) { alert('请先选择选项'); return; }
          var ans = answerLetters(q), got = live.picked.join(''), result;
          if (got === ans) result = 'right';
          else if (q.type === '多选' && live.picked.every(function (L) { return ans.indexOf(L) >= 0; })) result = 'partial';
          else result = 'wrong';
          st.records[q.id] = { result: result, answer: got, hints: live.hintLevel, ai: !!live.ai, ts: Date.now() }; st.lastTs = Date.now(); saveState(sid, st);
        } else if (numq) {
          var g;
          try { g = gradeNum(q, live.text); } catch (e) {
            live.err = e instanceof NumErr ? e.message : '没看懂这个写法，请检查';
            renderQ(); var ni2 = byId('pr-num'); if (ni2) ni2.focus(); return;
          }
          live.err = '';
          st.records[q.id] = { result: g.result, answer: live.text.trim(), marks: g.marks, auto: 'num', hints: live.hintLevel, ai: !!live.ai, ts: Date.now() }; st.lastTs = Date.now(); saveState(sid, st);
        } else { live.submitted = true; }
        render();
      });
      box.querySelectorAll('button[data-grade]').forEach(function (b) { b.addEventListener('click', function () {
        st.records[q.id] = { result: b.dataset.grade, text: live.text, hints: live.hintLevel, ai: !!live.ai, ts: Date.now() }; st.lastTs = Date.now(); saveState(sid, st); live.submitted = false; render();
      }); });
      var sol = byId('pr-sol'); if (sol) sol.addEventListener('click', function () { var bx = byId('pr-sol-box'); var show = bx.style.display === 'none'; bx.style.display = show ? '' : 'none'; sol.textContent = show ? '收起详解' : '查看详解'; });
      byId('pr-prev').addEventListener('click', function () { if (idx > 0) { idx--; live = { picked: [], hintLevel: 0, submitted: false, text: '' }; render(); } });
      byId('pr-next').addEventListener('click', function () { if (idx < items.length - 1) { idx++; live = { picked: [], hintLevel: 0, submitted: false, text: '' }; render(); } });
    }
    function renderMonitor() {
      var recs = items.map(function (it) { return st.records[it.qid]; }).filter(Boolean);
      var doneN = recs.length, right = recs.filter(function (r) { return r.result === 'right'; }).length, partial = recs.filter(function (r) { return r.result === 'partial'; }).length;
      var today = recs.filter(function (r) { return isToday(r.ts); }).length, goal = st.goal || 5;
      var acc = doneN ? (right + partial * 0.5) / doneN : 0;
      var h3 = '<div class="card-title">学习监督</div><div class="card-sub">' + esc(p.name) + ' · 记录保存在本机浏览器</div>';
      h3 += '<div class="row"><span>完成率</span><span class="big">' + pct(items.length ? doneN / items.length : 0) + '</span></div><div class="progress"><span style="width:' + (items.length ? doneN / items.length * 100 : 0) + '%"></span></div><div class="small muted">' + doneN + ' / ' + items.length + ' 题</div>';
      h3 += '<div class="row mt"><span>正确率</span><span class="big">' + pct(acc) + '</span></div><div class="progress g"><span style="width:' + (acc * 100) + '%"></span></div><div class="small muted">全对 ' + right + ' · 部分 ' + partial + '（计 0.5）· 错 ' + (doneN - right - partial) + '</div>';
      h3 += '<div class="row mt"><span>今日目标</span><span class="big">' + today + ' / ' + goal + '</span></div><div class="progress"><span style="width:' + Math.min(100, today / goal * 100) + '%;background:' + (today >= goal ? '#0ca30c' : '#eda100') + '"></span></div><div class="goal-row small"><span class="muted">每日目标</span><input class="input" type="number" min="1" max="50" id="pr-goal" value="' + goal + '"> 题' + (today >= goal ? '<span class="chip good">已达成</span>' : '') + '</div>';
      var aiN = (st.ai || []).length, indep = recs.filter(function (r) { return !r.hints && !r.ai; }).length;
      h3 += '<div class="row mt"><span>独立完成</span><span>' + indep + ' / ' + doneN + ' 题</span></div><div class="small muted">不看提示、不问 AI 做完的题' + (aiN ? ' · 复制给 AI ' + aiN + ' 次' : '') + '</div>';
      h3 += '<div class="row mt"><span>最近练习</span><span>' + (st.lastTs ? dateStr(st.lastTs) : '尚未开始') + '</span></div>';
      h3 += '<div class="mt"><div class="small" style="font-weight:600;margin-bottom:4px">各板块进度</div>' + p.practice.groups.map(function (g) {
        var tot = g.items.filter(function (i) { return QMAP.get(i.qid); }).length, d = g.items.filter(function (i) { return st.records[i.qid]; }).length, r = g.items.filter(function (i) { return st.records[i.qid] && st.records[i.qid].result === 'right'; }).length;
        return '<div class="unit-prog"><div class="lbl"><span>' + esc(g.unit) + ' <span class="muted">掌握度 ' + pct(g.mastery) + '</span></span><span>' + d + '/' + tot + (d ? ' · 全对 ' + r : '') + '</span></div><div class="progress"><span style="width:' + (tot ? d / tot * 100 : 0) + '%"></span></div></div>';
      }).join('') + '</div>';
      var m = byId('pr-monitor'); m.innerHTML = h3;
      byId('pr-goal').addEventListener('change', function () { st.goal = Math.max(1, parseInt(this.value, 10) || 5); saveState(sid, st); renderMonitor(); });
    }
    render();
  };

  /* ---------- 7. 学生阶段报告（打印用，一人一页 A4） ---------- */
  var COMP_DESC = { '数学抽象': '从具体问题中提炼概念和规律', '逻辑推理': '有条理地推导和证明', '数学建模': '把实际问题转化成数学问题来解决', '直观想象': '借助图形理解和分析问题', '数学运算': '准确、熟练地完成计算', '数据分析': '从数据中提取信息、作出判断' };
  var ERR_DESC = { '计算失误': '思路对但算错', '思路缺失': '想不到解题方法', '审题错误': '条件看错或漏看', '知识遗忘': '公式、概念记不清', '表述不完整': '步骤不全，丢过程分' };
  var ADV_LBL = { '错因': '错题订正', '心态': '考试策略' };
  function examShort(t) { return String(t || '').replace(/（[^）]*）/g, '').replace(/\([^)]*\)/g, '').trim(); }
  function cnDate(d) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || ''); return m ? m[1] + ' 年 ' + (+m[2]) + ' 月 ' + (+m[3]) + ' 日' : esc(d || ''); }
  /* 班内位置：pc = 班里掌握度低于本人的同学比例 */
  function classPos(pc) {
    var n = C.students.length, rank = Math.min(n, Math.max(1, n - Math.round(pc * n)));
    var top = rank / n, bottom = (n - rank + 1) / n;
    if (top <= 0.4) return { t: '班里前 ' + Math.max(10, Math.ceil(top * 10 - 1e-9) * 10) + '%', c: 'good' };
    if (bottom <= 0.4) return { t: '班里后 ' + Math.max(10, Math.ceil(bottom * 10 - 1e-9) * 10) + '%', c: 'bad' };
    return { t: '班里中等', c: 'mid' };
  }
  function vsClass(m, cm) { var d = m - cm; return d >= 0.03 ? '高于班级平均（' + pct(cm) + '）' : d <= -0.03 ? '低于班级平均（' + pct(cm) + '）' : '与班级平均（' + pct(cm) + '）相当'; }
  function noModelSym(s) { return String(s || '').replace(/[θδσγβμ]/g, ''); }
  /* 强 / 弱板块：取档案里的 strong / weak（与建议、推荐练习一致），不足 3 个时按相对偏移补齐 */
  function pickUnits(p) {
    var by = {}; p.units.forEach(function (u) { by[u.unit] = u; });
    var strong = p.strong.filter(function (u) { return by[u]; }), weak = p.weak.filter(function (u) { return by[u]; });
    var rest = p.units.filter(function (u) { return strong.indexOf(u.unit) < 0 && weak.indexOf(u.unit) < 0; });
    rest.slice().sort(function (a, b) { return b.delta - a.delta; }).forEach(function (u) { if (strong.length < 3 && u.delta > 0) strong.push(u.unit); });
    rest.slice().sort(function (a, b) { return a.delta - b.delta; }).forEach(function (u) { if (weak.length < 3 && strong.indexOf(u.unit) < 0 && u.delta < 0) weak.push(u.unit); });
    return { strong: strong.map(function (u) { return by[u]; }), weak: weak.map(function (u) { return by[u]; }) };
  }
  function practiceItems(p) {
    var out = []; p.practice.groups.forEach(function (g) { g.items.forEach(function (it) { var q = QMAP.get(it.qid); if (q) out.push({ unit: g.unit, qid: it.qid, role: it.role, q: q }); }); });
    return out;
  }
  function reportHtml(sid, k) {
    var p = C.profiles[sid];
    var tr = p.trend.filter(function (t) { return t.total != null; });
    var last = tr[tr.length - 1], prev = tr[tr.length - 2];
    var lastExam = C.exams.filter(function (e) { return e.id === (last && last.exam); })[0] || C.exams[C.exams.length - 1];
    var first = examShort(C.exams[0].title), lastT = examShort(C.exams[C.exams.length - 1].title);
    var pre = '高三'; if (first.indexOf(pre) === 0 && lastT.indexOf(pre) === 0) lastT = lastT.slice(pre.length);
    var cover = C.exams.length > 1 ? first + '—' + lastT + '，共 ' + C.exams.length + ' 次' : first + '，共 1 次';
    var n = C.students.length;
    var h = '<div class="rp-paper" data-sid="' + sid + '">';
    // 抬头
    h += '<div class="rp-head"><div><div class="rp-brand">数鉴 · 学生阶段学情报告</div><div class="rp-class">' + esc(C.meta['class']) + '</div></div>' +
      '<div class="rp-who"><div class="rp-name">' + esc(p.name) + '<span>学号 ' + esc(sid) + '</span></div>' +
      '<div class="rp-meta">报告日期 ' + cnDate(lastExam.date) + ' · 覆盖考试 ' + esc(cover) + '</div></div></div>';
    // 成绩概况
    var chg = '', rchg = '';
    if (last && prev) {
      var d = Math.round((last.total - prev.total) * 10) / 10, r = prev.rank - last.rank;
      chg = d > 0 ? '比上次多 <b class="up">' + d + '</b> 分' : d < 0 ? '比上次少 <b class="down">' + (-d) + '</b> 分' : '与上次持平';
      rchg = r > 0 ? '名次上升 <b class="up">' + r + '</b> 名' : r < 0 ? '名次下降 <b class="down">' + (-r) + '</b> 名' : '名次不变';
    }
    h += '<div class="rp-sec"><div class="rp-h">一、成绩概况</div><div class="rp-score">' +
      '<div class="rp-kpi"><div class="rp-kpi-l">最近一次：' + esc(examShort(last.title)) + '</div><div class="rp-kpi-v">' + last.total + '<small> / ' + last.full + ' 分</small></div>' +
      '<div class="rp-kpi-r">班级第 <b>' + last.rank + '</b> 名（共 ' + n + ' 人）</div>' +
      (prev ? '<div class="rp-kpi-c">' + chg + '，' + rchg + '</div>' : '') +
      '<div class="rp-kpi-c muted">本次班级平均 ' + fix(last.class_mean) + ' 分</div></div>' +
      '<div class="rp-chart-trend" id="rp-trend-' + k + '"></div></div></div>';
    // 知识板块
    var pk = pickUnits(p);
    function urow(u) { var ps = classPos(u.percentile); return '<tr><td class="u">' + esc(u.unit) + '</td><td class="m">' + pct(u.mastery) + '</td><td class="cm">班均 ' + pct(u.class_mean) + '</td><td><span class="rp-pos ' + ps.c + '">' + ps.t + '</span></td></tr>'; }
    h += '<div class="rp-sec"><div class="rp-h">二、知识板块<span class="rp-note">掌握度：做该板块典型高考题的预计得分率</span><span class="rp-legend"><span class="sw b"></span>本人掌握度<span class="sw d"></span>班级平均<span class="lg good">绿字</span>擅长<span class="lg bad">红字</span>重点</span></div><div class="rp-units">' +
      '<div class="rp-ulist"><div class="rp-sub good">相对擅长的板块</div><table class="rp-ut">' + pk.strong.map(urow).join('') + '</table>' +
      '<div class="rp-sub bad">下阶段重点板块</div><table class="rp-ut">' + pk.weak.map(urow).join('') + '</table>' +
      '<div class="rp-tip">擅长与重点板块是和' + esc(p.name) + '自己的整体水平相比选出的，与下面的建议、推荐练习一一对应。</div></div>' +
      '<div class="rp-uchart"><div class="rp-chart-units" id="rp-units-' + k + '" style="height:' + (p.units.length * 16 + 8) + 'px"></div></div></div></div>';
    // 能力特点 + 失分原因
    var cs = p.competencies.slice().sort(function (a, b) { return b.delta - a.delta; });
    var cTop = cs[0], cLow = cs[cs.length - 1];
    var errs = Object.keys(p.errors || {}).map(function (e) { return { e: e, n: p.errors[e] }; }).sort(function (a, b) { return b.n - a.n; });
    var eTot = sum(errs.map(function (x) { return x.n; })), eMax = errs.length ? errs[0].n : 1;
    var errConc = errs.length ? '最主要的失分原因是「' + esc(errs[0].e) + '」（' + esc(ERR_DESC[errs[0].e] || '') + '），共 ' + errs[0].n + ' 次，占 ' + pct(errs[0].n / eTot) + (errs[1] ? '；其次是「' + esc(errs[1].e) + '」（' + errs[1].n + ' 次）' : '') + '。' : '近几次考试暂无错因记录。';
    h += '<div class="rp-two"><div class="rp-sec"><div class="rp-h">三、能力特点</div>' +
      '<div class="rp-comp"><span class="rp-tag good">相对突出</span><b>' + esc(cTop.competency) + '</b>：' + esc(COMP_DESC[cTop.competency] || '') + '。这是' + esc(p.name) + '六项数学能力中表现最好的一项，掌握度 ' + pct(cTop.mastery) + '，' + vsClass(cTop.mastery, cTop.class_mean) + '。</div>' +
      '<div class="rp-comp"><span class="rp-tag bad">相对薄弱</span><b>' + esc(cLow.competency) + '</b>：' + esc(COMP_DESC[cLow.competency] || '') + '。这是六项中最需要加强的一项，掌握度 ' + pct(cLow.mastery) + '，' + vsClass(cLow.mastery, cLow.class_mean) + '。</div>' +
      '</div><div class="rp-sec"><div class="rp-h">四、主要失分原因<span class="rp-note">近 ' + C.exams.length + ' 次考试教师标注</span></div>' +
      (errs.length ? '<div class="rp-errs">' + errs.map(function (x) { return '<div class="rp-err"><span class="en">' + esc(x.e) + '</span><span class="eb"><span style="width:' + Math.round(x.n / eMax * 100) + '%"></span></span><span class="ec">' + x.n + ' 次</span></div>'; }).join('') + '</div>' : '') +
      '<div class="rp-concl">' + errConc + '</div></div></div>';
    // 老师评语
    var cms = p.comments.slice().sort(function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : 0; }).slice(0, 2);
    h += '<div class="rp-sec"><div class="rp-h">五、老师评语</div>' + (cms.length ? cms.map(function (c) { return '<div class="rp-cmt"><span class="d">' + esc(c.date) + '</span>' + esc(c.text) + '</div>'; }).join('') : '<div class="muted">暂无评语</div>') + '</div>';
    // 下阶段建议
    h += '<div class="rp-sec"><div class="rp-h">六、下阶段建议</div><ol class="rp-adv">' + p.advice.map(function (a) {
      var m = /^【([^】]*)】\s*/.exec(a), lbl = m ? noModelSym(m[1]).trim() : '', body = noModelSym(m ? a.slice(m[0].length) : a);
      lbl = ADV_LBL[lbl] || lbl;
      return '<li>' + (lbl ? '<b>' + esc(lbl) + '：</b>' : '') + esc(body) + '</li>';
    }).join('') + '</ol></div>';
    // 推荐练习
    var items = practiceItems(p);
    h += '<div class="rp-sec"><div class="rp-h">七、推荐练习（' + items.length + ' 题）<span class="rp-note">可在网页“学生练习”中在线完成</span></div><div class="rp-prac">' +
      p.practice.groups.map(function (g) {
        var its = items.filter(function (x) { return x.unit === g.unit; }); if (!its.length) return '';
        return '<div class="rp-prow"><span class="pu">' + esc(g.unit) + '</span><span class="pi">' + its.map(function (x) { return '<span class="rp-q"><span class="id">' + esc(x.qid) + '</span>' + esc(x.q.type) + (x.role === '挑战' ? '·<em>挑战</em>' : '') + '</span>'; }).join('') + '</span></div>';
      }).join('') + '</div>';
    var st = loadState(sid), recs = items.map(function (x) { return st.records[x.qid]; }).filter(Boolean);
    if (recs.length) {
      var right = recs.filter(function (r) { return r.result === 'right'; }).length, part = recs.filter(function (r) { return r.result === 'partial'; }).length;
      h += '<div class="rp-done">练习完成情况：完成 ' + recs.length + ' 题（共 ' + items.length + ' 题），正确率 ' + pct((right + part * 0.5) / recs.length) + '（全对 ' + right + ' 题' + (part ? '，部分正确 ' + part + ' 题' : '') + '）</div>';
    }
    h += '</div>';
    h += '<div class="rp-foot">本报告由数鉴根据考试逐题得分与教师评价生成，供教师参考。示例数据为虚构。</div></div>';
    return h;
  }
  function reportCharts(sid, k) {
    var p = C.profiles[sid], tr = p.trend, n = C.students.length;
    var R = { renderer: 'svg' };
    var xs = tr.map(function (t) { return examShort(t.title).replace('高三', ''); });
    chart('rp-trend-' + k, {
      legend: { top: 0, right: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { fontSize: 10 } },
      grid: [{ left: 34, right: 14, top: 22, height: 62 }, { left: 34, right: 14, top: 104, height: 22 }],
      xAxis: [{ gridIndex: 0, type: 'category', data: xs, boundaryGap: true, axisLabel: { show: false } },
        { gridIndex: 1, type: 'category', data: xs, boundaryGap: true, position: 'bottom', axisLabel: { fontSize: 10, margin: 6 }, axisLine: { show: false } }],
      yAxis: [{ gridIndex: 0, type: 'value', min: 0, max: tr[0].full, interval: tr[0].full / 2, axisLabel: { fontSize: 9 } },
        { gridIndex: 1, type: 'value', inverse: true, min: 1, max: n, interval: n - 1, splitLine: { show: false }, axisLabel: { fontSize: 9, formatter: '第{value}' } }],
      series: [
        { name: '本人得分', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: tr.map(function (t) { return t.total; }), symbolSize: 6, lineStyle: { width: 2 }, label: { show: true, position: 'top', fontSize: 10, color: '#1c5cab', formatter: '{c} 分' } },
        { name: '班级平均分', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: tr.map(function (t) { return t.class_mean; }), symbol: 'none', lineStyle: { width: 1.5, type: 'dashed', color: '#898781' }, itemStyle: { color: '#898781' } },
        { name: '班级名次', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: tr.map(function (t) { return t.rank; }), symbol: 'diamond', symbolSize: 7, lineStyle: { width: 1.5, color: '#eb6834' }, itemStyle: { color: '#eb6834' }, label: { show: true, position: 'top', distance: 3, fontSize: 10, color: '#a2431c', formatter: '第{c}名' } }
      ]
    }, R);
    var pk = pickUnits(p), sN = pk.strong.map(function (u) { return u.unit; }), wN = pk.weak.map(function (u) { return u.unit; });
    var us = p.units.slice().sort(function (a, b) { return b.mastery - a.mastery; });
    chart('rp-units-' + k, {
      grid: { left: 4, right: 4, top: 2, bottom: 2, containLabel: true },
      xAxis: { type: 'value', min: 0, max: 1, show: false },
      yAxis: [{ type: 'category', inverse: true, data: us.map(function (u) { return u.unit; }), axisLine: { show: false },
        axisLabel: { fontSize: 10, formatter: function (v) { return sN.indexOf(v) >= 0 ? '{g|' + v + '}' : wN.indexOf(v) >= 0 ? '{r|' + v + '}' : v; }, rich: { g: { color: '#006300', fontWeight: 600, fontSize: 10 }, r: { color: '#a32626', fontWeight: 600, fontSize: 10 } } } },
        { type: 'category', inverse: true, position: 'right', data: us.map(function (u) { return pct(u.mastery); }), axisLine: { show: false }, axisLabel: { fontSize: 10, color: '#1d1d1b', margin: 6 } }],
      series: [
        { type: 'bar', data: us.map(function (u) { return u.mastery; }), barWidth: 8, itemStyle: { color: '#6da7ec', borderRadius: [0, 3, 3, 0] }, z: 2 },
        { type: 'scatter', data: us.map(function (u) { return u.class_mean; }), symbol: 'diamond', symbolSize: 7, itemStyle: { color: '#0b0b0b' }, z: 3 }
      ]
    }, R);
  }
  PAGES.report = function (arg) {
    var all = arg === 'ALL', ids = all ? C.students.map(function (s) { return s.id; }) : [arg];
    var h = '<div class="rp-toolbar">';
    if (all) {
      h += '<a class="btn sm" href="#/overview">← 返回总览</a><span class="rp-tb-info">全班报告 · 共 ' + ids.length + ' 人，每人一页</span>';
    } else {
      var i = C.students.findIndex(function (s) { return s.id === arg; }), pv = C.students[i - 1], nx = C.students[i + 1];
      h += '<a class="btn sm" href="#/student/' + arg + '">← 返回档案</a>' +
        (pv ? '<a class="btn sm" href="#/report/' + pv.id + '">‹ 上一位：' + esc(pv.name) + '</a>' : '<button class="btn sm" disabled>‹ 上一位</button>') +
        (nx ? '<a class="btn sm" href="#/report/' + nx.id + '">下一位：' + esc(nx.name) + ' ›</a>' : '<button class="btn sm" disabled>下一位 ›</button>') +
        '<span class="rp-tb-info">第 ' + (i + 1) + ' / ' + C.students.length + ' 位</span>';
    }
    h += '<span class="spacer"></span>' + (all ? '' : '<a class="btn sm" href="#/report/ALL">打印全班报告</a>') + '<button class="btn primary sm" id="rp-print">打印 / 存为 PDF</button></div>';
    h += '<div class="rp' + (all ? ' rp-all' : '') + '">' + ids.map(function (sid, k) { return reportHtml(sid, k); }).join('') + '</div>';
    view.innerHTML = h;
    ids.forEach(function (sid, k) { reportCharts(sid, k); });
    byId('rp-print').addEventListener('click', function () { charts.forEach(function (c) { c.resize(); }); window.print(); });
  };

  /* ---------- 启动 ---------- */
  byId('sidebar-foot').innerHTML = esc(C.meta.class) + '<br>数据生成于 mathinsight 分析引擎<br>示例数据，仅供演示';
  byId('topbar-right').innerHTML = '<span>' + esc(C.meta.class) + '</span><span class="chip blue">' + C.students.length + ' 名学生</span><span class="chip gray">' + C.exams.length + ' 次考试</span>';
  route();
})();
