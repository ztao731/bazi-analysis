#!/usr/bin/env python3
"""八字命理分析 Web 服务 — 基于 china-testing/bazi 纯规则引擎"""
import subprocess, re, os, sys, html

# ---------- 轻量 HTTP 服务器（零额外依赖）----------
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", 8889))
HERE = os.path.dirname(os.path.abspath(__file__))


def ansi_to_html(text: str) -> str:
    """将 ANSI 转义序列转换为 HTML 样式"""
    # 先做 HTML 转义
    text = html.escape(text)

    # 颜色映射
    color_map = {
        '30': 'color:#1a1a1a', '31': 'color:#e74c3c', '32': 'color:#27ae60',
        '33': 'color:#f39c12', '34': 'color:#2980b9', '35': 'color:#8e44ad',
        '36': 'color:#16a085', '37': 'color:#ecf0f1',
        '40': 'background:#1a1a1a', '41': 'background:#e74c3c',
        '42': 'background:#27ae60', '43': 'background:#f39c12',
        '44': 'background:#2980b9', '45': 'background:#8e44ad',
        '46': 'background:#16a085', '47': 'background:#ecf0f1',
        '1': 'font-weight:bold',
    }

    def replace_ansi(m):
        codes = m.group(1).split(';')
        styles = [color_map.get(c, '') for c in codes if c in color_map]
        styles = [s for s in styles if s]
        if not styles:
            return '</span><span>'
        return f'</span><span style="{";".join(styles)}">'

    # 处理 ANSI CSI 序列 \033[...m
    text = re.sub(r'\x1b\[([0-9;]*)m', replace_ansi, text)
    # 清理：把空的 <span> 去掉
    text = text.replace('<span></span>', '')
    text = text.replace('<span></span>', '')
    return f'<span>{text}</span>'


def run_bazi(year, month, day, hour, is_male=True, is_gregorian=True):
    """调用原始 bazi.py 命令行工具"""
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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/' or path == '/index.html':
            html_path = os.path.join(HERE, 'templates', 'index.html')
            with open(html_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self._respond(200, 'text/html; charset=utf-8', content)
        elif path == '/style.css':
            self._respond(200, 'text/css; charset=utf-8', CSS)
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
        styled = ansi_to_html(raw)
        wrap = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>八字分析</title>
<style>{CSS}</style></head><body><header><a href="/">← 返回</a></header><pre class="bazi-output">{styled}</pre></body></html>"""
        self._respond(200, 'text/html; charset=utf-8', wrap)

    def _respond(self, code, ctype, body):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))


CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
header{padding:16px 20px;border-bottom:1px solid #21262d}
header a{color:#58a6ff;text-decoration:none;font-size:14px}
.form-wrap{max-width:500px;margin:40px auto;padding:0 20px}
h1{text-align:center;font-size:24px;margin-bottom:8px;color:#f0f6fc}
.subtitle{text-align:center;font-size:13px;color:#8b949e;margin-bottom:32px}
.row{display:flex;gap:12px;margin-bottom:16px}
.row label{flex:1}
label{display:block;font-size:13px;color:#8b949e;margin-bottom:6px}
input,select{width:100%;padding:10px 14px;border-radius:8px;border:1px solid #30363d;background:#161b22;color:#c9d1d9;font-size:15px}
input:focus,select:focus{outline:none;border-color:#58a6ff;box-shadow:0 0 0 3px rgba(88,166,255,.15)}
.btn{width:100%;padding:13px;border:none;border-radius:8px;background:#238636;color:#fff;font-size:16px;cursor:pointer;margin-top:8px}
.btn:hover{background:#2ea043}
.btn:active{background:#196c2e}
pre.bazi-output{max-width:1000px;margin:24px auto;padding:24px;background:#0d1117;color:#c9d1d9;font-family:'Courier New',monospace;font-size:13px;line-height:1.7;white-space:pre-wrap;word-break:break-all;overflow-x:auto}
pre.bazi-output span{white-space:pre-wrap}
footer{text-align:center;padding:20px;font-size:12px;color:#484f58}
@media(max-width:480px){.row{flex-direction:column}}
"""

if __name__ == '__main__':
    httpd = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'八字分析服务已启动: http://0.0.0.0:{PORT}')
    httpd.serve_forever()