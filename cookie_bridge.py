"""
Cookie Bridge: 自动导出 YouTube cookies 供 yt-dlp 使用

工作原理：
1. 用 Edge 浏览器加载专用扩展
2. 扩展自动提取 YouTube cookies 并发送到本地服务器
3. 服务器写入 cookies.txt (Netscape 格式)

前置条件（仅需一次）：
  在 Edge 浏览器中登录一次 YouTube → 之后全自动

用法：
  python cookie_bridge.py
"""

import os
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

COOKIE_PATH = os.path.join(os.path.dirname(__file__), "cookies.txt")
EXT_PATH = os.path.join(os.path.dirname(__file__), "cookie-extension-v2")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9876

received = []
stop = threading.Event()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        size = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(size).decode("utf-8")
        if self.path == "/cookies" and len(body) > 200:
            received.append(body)
            entries = len([l for l in body.split("\n") if l.strip() and not l.startswith("#")])
            print(f"\n[Bridge] Received {entries} cookies!", flush=True)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *a):
        pass


def server_thread():
    s = HTTPServer(("127.0.0.1", PORT), Handler)
    s.timeout = 0.5
    while not stop.is_set():
        try:
            s.handle_request()
        except:
            pass
    s.server_close()


def main():
    print("=" * 60)
    print("  Cookie Bridge - YouTube Cookie Auto-Exporter")
    print("=" * 60)

    # Kill old browsers
    subprocess.run(["taskkill", "/F", "/IM", "msedge.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
    time.sleep(2)

    # Start server
    t = threading.Thread(target=server_thread, daemon=True)
    t.start()
    time.sleep(0.5)

    # Start Edge with extension
    print("\n[1/3] Starting Edge with cookie auto-exporter...")
    p = subprocess.Popen(
        [EDGE_PATH, f"--load-extension={EXT_PATH}",
         "--no-first-run", "--no-default-browser-check",
         "https://www.youtube.com"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print(f"  Edge PID={p.pid}")

    print("\n[2/3] Waiting for cookie export...")
    for i in range(60):
        time.sleep(1)
        if received:
            break
        if i == 30:
            print("  (still waiting - first time may need Edge login)")

    stop.set()
    time.sleep(0.5)

    if not received:
        print("\n[3/3] FAILED: No cookies received.")
        print("\n需要先在 Edge 中登录一次 YouTube：")
        print("  1. Edge 浏览器应该已经打开了")
        print("  2. 在 Edge 中登录你的 YouTube 账号")
        print("  3. 登录后关掉 Edge，重新运行此脚本")
        print(f"\n  python cookie_bridge.py")
        return 1

    # Save cookies
    body = received[-1]
    with open(COOKIE_PATH, "w", encoding="utf-8") as f:
        f.write(body)
    entries = len([l for l in body.split("\n") if l.strip() and not l.startswith("#")])
    size = os.path.getsize(COOKIE_PATH)
    print(f"\n[3/3] Saved {entries} cookies to cookies.txt ({size} bytes)")

    # Verify
    print("\nVerifying cookies with yt-dlp...")
    r = subprocess.run(
        ["py", "-3", "-m", "yt_dlp", "--cookies", COOKIE_PATH,
         "--skip-download", "--print", "title",
         "https://www.youtube.com/watch?v=Db260rUuKJg"],
        capture_output=True, text=True, timeout=30,
    )
    if "Sign in" not in r.stderr and r.returncode == 0:
        print(f"  VERIFIED: {r.stdout.strip()[:60]}")
        print("\n[SUCCESS] Cookies are valid. Pipeline will run automatically.")
        return 0
    else:
        print(f"  FAILED: {r.stderr[-100:]}")
        print("\nCookies were exported but YouTube rejected them.")
        print("Please log into YouTube in Edge and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
