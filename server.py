#!/usr/bin/env python3
"""八字命理分析 Web 服务 — 基于 china-testing/bazi 纯规则引擎"""
import subprocess, re, os, sys, html

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", 8889))
HERE = os.path.dirname(os.path.abspath(__file__))


# ============================================================
#  ANSI → HTML  增强版 — 颜色鲜明、表头突出
# ============================================================
def ansi_to_html(text: str) -> str:
    text = html.escape(text)

    color_map = {
        # 前景色 — 在白底/黑底都鲜明
        '30': 'color:#c9d1d9',          # 黑→浅灰正文
        '31': 'color:#ff6b6b',          # 红
        '32': 'color:#3fb950',          # 绿
        '33': 'color:#e3b341',          # 黄
        '34': 'color:#79c0ff',          # 蓝
        '35': 'color:#bc8cff',          # 紫
        '36': 'color:#f0883e',          # 青→橙金  原本 CLI 表头用 cyan
        '37': 'color:#f0f6fc',          # 白
        # 背景色
        '40': 'background:#0d1117',
        '41': 'background:#da3633',
        '42': 'background:#238636',
        '43': 'background:#9e6a03',
        '44': 'background:#1f6feb',
        '45': 'background:#8250df',
        '46': 'background:#08785a',
        '47': 'background:#c9d1d9',
        # 字形
        '1': 'font-weight:800',
        '4': 'text-decoration:underline',
    }

    def replace_ansi(m):
        codes = m.group(1).split(';')
        styles = [color_map.get(c, '') for c in codes if c in color_map]
        styles = [s for s in styles if s]
        return '</span><span style="%s">' % ';'.join(styles) if styles else '</span><span>'

    text = re.sub(r'\x1b\[([0-9;]*)m', replace_ansi, text)
    # 清理空 span
    text = re.sub(r'<span></span>', '', text)
    return f'<span>{text}</span>'


# ============================================================
#  智能解析 — 提取关键结论，给分节打标签
# ============================================================
def enrich_output(raw_text: str) -> str:
    """将原始纯文本输出变成结构化 HTML"""
    colored = ansi_to_html(raw_text)

    # ---- 提取关键信息 ----
    summary_items = []

    # 命主
    m = re.search(r'(男命|女命)', raw_text)
    gender = m.group(1) if m else ''

    # 四柱
    m = re.search(r'四柱：(\S+)', raw_text)
    pillars = m.group(1) if m else ''

    # 五行分数
    scores = {}
    for m in re.finditer(r'(金|木|水|火|土)(\d+)', raw_text):
        scores[m.group(1)] = int(m.group(2))
    score_summary = ' '.join(f'{k}{v}' for k, v in
                             sorted(scores.items(), key=lambda x: -x[1])) if scores else ''

    # 强弱
    m = re.search(r'强弱\s*(\d+)', raw_text)
    strength = m.group(1) if m else ''
    has_root = '强根:有' in raw_text
    strength_label = '身强' if (strength and int(strength) > 29 and has_root) else \
                     '身弱' if (strength and int(strength) <= 29) else ''

    # 调候
    m = re.search(r'调候：\s*(.+)', raw_text)
    tiaohou = m.group(1).strip() if m else ''
    # 提取喜忌
    xi = []
    ji = []
    for m in re.finditer(r'(\d)喜?([甲乙丙丁戊己庚辛壬癸]+)', tiaohou):
        xi.append(m.group(2))
    for m in re.finditer(r'忌([甲乙丙丁戊己庚辛壬癸]+)', tiaohou):
        ji.append(m.group(1))
    yong_shen = ','.join(xi) if xi else ''
    ji_shen = ','.join(ji) if ji else ''

    # 格局
    ges = []
    if '建禄格' in raw_text:
        ges.append('建禄格')
    if '阳刃格' in raw_text:
        ges.append('阳刃格')
    ge_summary = '、'.join(ges) if ges else ''

    # 湿度
    m = re.search(r'湿度\[[-\d,]+\]\s*([-\d]+)', raw_text)
    shidu = m.group(1) if m else ''

    # 组装摘要
    summary_html = '<div class="summary-card">'
    summary_html += '<div class="summary-title">📋 分析结论速览</div>'
    summary_html += '<div class="summary-grid">'

    if gender and pillars:
        summary_html += f'<div class="sg-item"><span class="sg-label">命主</span><span class="sg-val">{gender} · {pillars}</span></div>'
    if strength_label or strength:
        val = f'{strength_label}（得分{strength}）' if strength_label else f'得分{strength}'
        root_note = ' · 有根' if has_root else ''
        summary_html += f'<div class="sg-item"><span class="sg-label">强弱</span><span class="sg-val">{val}{root_note}</span></div>'
    if score_summary:
        summary_html += f'<div class="sg-item"><span class="sg-label">五行</span><span class="sg-val scores">{score_summary}</span></div>'
    if ge_summary:
        summary_html += f'<div class="sg-item"><span class="sg-label">格局</span><span class="sg-val ge">{ge_summary}</span></div>'
    if yong_shen:
        summary_html += f'<div class="sg-item"><span class="sg-label">用神</span><span class="sg-val yong">{yong_shen}</span></div>'
    if ji_shen:
        summary_html += f'<div class="sg-item"><span class="sg-label">忌神</span><span class="sg-val ji">{ji_shen}</span></div>'
    if tiaohou:
        summary_html += f'<div class="sg-item"><span class="sg-label">调候</span><span class="sg-val tiao">{tiaohou}</span></div>'
    if shidu:
        summary_html += f'<div class="sg-item"><span class="sg-label">湿度</span><span class="sg-val">{shidu}</span></div>'

    summary_html += '</div></div>'

    # ---- 给分节打标签 ----
    # 把 ------------------------------------------------------------ 变成彩色分隔条
    colored = re.sub(
        r'(<span[^>]*>)\s*(-{30,})\s*(</span>)',
        r'<hr class="section-divider">',
        colored
    )
    # 次级分隔 ========
    colored = re.sub(
        r'(<span[^>]*>)\s*(={5,})\s*(</span>)',
        r'<hr class="sub-divider">',
        colored
    )

    # 高亮章节标题行
    for keyword, label in [
        ('格局选用', '🎯 格局选用'),
        ('大运：', '📅 大运流年'),
        ('六亲分析', '👨‍👩‍👧‍👦 六亲分析'),
        ('比肩分析', '👤 比肩分析'),
        ('劫财分析', '🤝 劫财分析'),
        ('偏印分析', '🧠 偏印分析'),
        ('正印分析', '📚 正印分析'),
        ('调候：', '🌡️ 调候用神'),
        ('建禄格', '🏠 建禄格详解'),
        ('阳刃格', '⚔️ 阳刃格详解'),
        ('神：', '⭐ 神煞'),
    ]:
        colored = colored.replace(keyword,
            f'<span class="section-tag">{label}</span> ', 1 if keyword == '大运：' else -1)

    # 高亮"大运"后面的干支列表
    colored = re.sub(
        r'(<span class="section-tag">📅 大运流年</span>\s*)',
        r'\1<span class="dayun-header">',
        colored
    )

    return summary_html + '\n<pre class="bazi-output">' + colored + '</pre>'


# ============================================================
def run_bazi(year, month, day, hour, is_male=True, is_gregorian=True):
    bazi_py = os.path.join(HERE, 'bazi.py')
    cmd = [sys.executable, bazi_py, str(year), str(month), str(day), str(hour)]
    if is_gregorian:
        cmd.append('-g')
    if not is_male:
        cmd.append('-n')
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                cwd=HERE, timeout=30, encoding='utf-8',
                                errors='replace')
        return result.stdout if result.returncode == 0 else f"错误:\n{result.stderr}"
    except Exception as e:
        return f"运行错误: {e}"


# ============================================================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/' or path == '/index.html':
            html_path = os.path.join(HERE, 'templates', 'index.html')
            with open(html_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self._respond(200, 'text/html; charset=utf-8', content)
        else:
            self._respond(404, 'text/plain', 'Not Found')

    def do_POST(self):
        if urlparse(self.path).path != '/analyze':
            self._respond(404, 'text/plain', 'Not Found')
            return
        length = int(self.headers.get('Content-Length', 0))
        body = parse_qs(self.rfile.read(length).decode('utf-8'))
        year = body.get('year', ['1979'])[0]
        month = body.get('month', ['7'])[0]
        day = body.get('day', ['31'])[0]
        hour = body.get('hour', ['8'])[0]
        gender = body.get('gender', ['male'])[0]
        cal = body.get('cal', ['gregorian'])[0]
        is_male = gender == 'male'
        is_gregorian = cal == 'gregorian'
        raw = run_bazi(year, month, day, hour, is_male, is_gregorian)
        body_html = enrich_output(raw)
        html_page = RESULT_PAGE.replace('{BODY}', body_html).replace('{CAL}', cal)\
            .replace('{YEAR}', year).replace('{MONTH}', month)\
            .replace('{DAY}', day).replace('{HOUR}', hour)\
            .replace('{GENDER}', 'male' if is_male else 'female')
        self._respond(200, 'text/html; charset=utf-8', html_page)

    def _respond(self, code, ctype, body):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))


# ============================================================
#  CSS
# ============================================================
CSS = r"""
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
/* ---- 顶部导航 ---- */
header{padding:12px 20px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:16px}
header a{color:#58a6ff;text-decoration:none;font-size:13px}
header .reinput{color:#8b949e;font-size:12px}

/* ========== 结论摘要卡片 ========== */
.summary-card{
  max-width:960px;margin:20px auto 0;padding:18px 24px;
  background:linear-gradient(135deg,#1a1f2e 0%,#161b22 100%);
  border:1px solid #30363d;border-radius:12px;
}
.summary-title{font-size:16px;font-weight:700;color:#f0f6fc;margin-bottom:14px}
.summary-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px 20px}
.sg-item{display:flex;align-items:baseline;gap:8px}
.sg-label{font-size:11px;color:#8b949e;min-width:32px;flex-shrink:0}
.sg-val{font-size:14px;color:#e6edf3;font-weight:600}
.sg-val.scores{font-family:'Courier New',monospace;font-size:13px;letter-spacing:2px}
.sg-val.ge{color:#f0883e;font-size:15px}
.sg-val.yong{color:#3fb950}
.sg-val.ji{color:#ff6b6b}
.sg-val.tiao{color:#79c0ff;font-size:12px}

/* ========== 分割线 ========== */
hr.section-divider{
  border:none;height:2px;
  background:linear-gradient(90deg,#30363d,#f0883e,#30363d);
  margin:20px 0;
}
hr.sub-divider{
  border:none;height:1px;
  background:linear-gradient(90deg,#21262d,#484f58,#21262d);
  margin:12px 0;
}

/* ========== 章节标签 ========== */
.section-tag{
  display:inline-block;
  background:#1a3a2a;color:#3fb950;
  font-size:12px;font-weight:700;
  padding:2px 8px;border-radius:4px;
  margin-right:4px;
}

/* ========== 正文输出区 ========== */
pre.bazi-output{
  max-width:960px;margin:12px auto 40px;padding:16px 24px;
  font-family:'SF Mono','Cascadia Code','Courier New',monospace;
  font-size:13px;line-height:1.7;
  white-space:pre-wrap;word-break:break-all;
  overflow-x:auto;
}
pre.bazi-output span{white-space:pre-wrap}

/* ========== 表单（首页） ========== */
.form-wrap{max-width:500px;margin:40px auto;padding:0 20px}
h1{text-align:center;font-size:24px;margin-bottom:8px;color:#f0f6fc}
.subtitle{text-align:center;font-size:13px;color:#8b949e;margin-bottom:32px}
.row{display:flex;gap:12px;margin-bottom:16px}
.row label{flex:1}
label{display:block;font-size:13px;color:#8b949e;margin-bottom:6px}
input,select{
  width:100%;padding:10px 14px;border-radius:8px;
  border:1px solid #30363d;background:#161b22;color:#c9d1d9;
  font-size:15px;appearance:none
}
input:focus,select:focus{outline:none;border-color:#58a6ff;box-shadow:0 0 0 3px rgba(88,166,255,.15)}
.btn{width:100%;padding:13px;border:none;border-radius:8px;background:#238636;color:#fff;font-size:16px;cursor:pointer;margin-top:8px}
.btn:hover{background:#2ea043}
footer{text-align:center;padding:20px;font-size:12px;color:#484f58}
@media(max-width:480px){.row{flex-direction:column}}
"""

# ============================================================
RESULT_PAGE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>八字分析结果</title>
<style>""" + CSS + """</style>
</head>
<body>
<header>
  <a href="/">← 返回</a>
  <span class="reinput">重新输入：{YEAR}年{MONTH}月{DAY}日 {HOUR}时 · {'男' if '{GENDER}'=='male' else '女'}命 · {'公历' if '{CAL}'=='gregorian' else '农历'}</span>
</header>
{BODY}
</body>
</html>"""

# ============================================================
if __name__ == '__main__':
    httpd = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'八字分析服务已启动: http://0.0.0.0:{PORT}')
    httpd.serve_forever()