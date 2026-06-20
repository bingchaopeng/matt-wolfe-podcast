"""
Chrome YouTube Cookie 自动刷新工具
用法: python refresh_cookies.py

工作方式：
1. 先尝试通过 Chrome DevTools Protocol 从运行中的 Chrome 提取
2. 如果 Chrome 没开调试端口，启动新 headless Chrome 实例
3. 提取 YouTube cookies 并保存为 cookies.txt
"""
import os
import json
import sys
import time
import subprocess
import tempfile
from urllib.request import urlopen

COOKIE_PATH = os.path.join(os.path.dirname(__file__), "cookies.txt")


def find_chrome():
    """查找 Chrome 可执行文件路径"""
    candidates = [
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def read_cookie_db_direct():
    """直接读取 Chrome cookie 数据库（需要管理员权限）"""
    try:
        import browser_cookie3
        cj = browser_cookie3.chrome(domain_name="youtube.com")
        cookies = list(cj)
        if not cookies:
            return None
        return cookies
    except Exception as e:
        print(f"  browser-cookie3: {e}")
        return None


def extract_via_cdp(user_data_dir=None):
    """启动 Chrome 并通过 CDP 提取 cookies"""
    chrome = find_chrome()
    if not chrome:
        print("  Chrome not found")
        return None

    port = 9222
    if not user_data_dir:
        user_data_dir = tempfile.mkdtemp(prefix="chrome_cookies_")

    try:
        cmd = [
            chrome,
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={user_data_dir}",
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "https://www.youtube.com",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)

        # Try CDP
        import websocket
        resp = urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5)
        data = json.loads(resp.read())
        ws_url = data["webSocketDebuggerUrl"]

        ws = websocket.create_connection(ws_url, timeout=10)
        msg_id = 1

        def send(method, params=None):
            nonlocal msg_id
            mid = msg_id
            msg_id += 1
            msg = {"id": mid, "method": method}
            if params:
                msg["params"] = params
            ws.send(json.dumps(msg))
            while True:
                r = json.loads(ws.recv())
                if r.get("id") == mid:
                    return r.get("result", {})

        # Navigate to YouTube and wait
        send("Page.navigate", {"url": "https://www.youtube.com"})
        time.sleep(5)

        # Get cookies
        result = send("Network.getCookies", {"urls": ["https://www.youtube.com"]})
        ws.close()
        proc.terminate()
        proc.wait(timeout=5)

        cookies = result.get("cookies", [])
        yt_cookies = [c for c in cookies if "youtube" in c.get("domain", "")]
        return yt_cookies or cookies

    except Exception as e:
        print(f"  CDP error: {e}")
        try:
            proc.terminate()
        except Exception:
            pass
        return None


def save_cookies(cookies):
    """将 cookies 保存为 Netscape 格式"""
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = getattr(c, "domain", c.get("domain", ".youtube.com"))
        if isinstance(domain, str) and not domain.startswith("."):
            domain = "." + domain

        path = getattr(c, "path", c.get("path", "/"))
        secure = getattr(c, "secure", c.get("secure", False))
        secure_str = "TRUE" if secure else "FALSE"

        expires = getattr(c, "expires", c.get("expires", 0))
        expires_str = str(int(expires)) if expires else "0"

        name = getattr(c, "name", c.get("name", ""))
        value = getattr(c, "value", c.get("value", ""))

        lines.append(f"{domain}\tTRUE\t{path}\t{secure_str}\t{expires_str}\t{name}\t{value}")

    with open(COOKIE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return len(lines) - 1


def refresh():
    """主入口：刷新 cookies"""
    print("Refreshing YouTube cookies...")

    # Method 1: Read from Chrome database (fast, might need admin)
    print("Method 1: browser-cookie3...")
    cookies = read_cookie_db_direct()
    if cookies and len(cookies) >= 5:
        count = save_cookies(cookies)
        print(f"  OK: {count} cookies saved")
        return True

    # Method 2: CDP via headless Chrome
    print("Method 2: CDP headless Chrome...")
    cookies = extract_via_cdp()
    if cookies and len(cookies) >= 5:
        count = save_cookies(cookies)
        print(f"  OK: {count} cookies saved")
        return True

    print("FAILED: No method could extract YouTube cookies")
    return False


if __name__ == "__main__":
    success = refresh()
    sys.exit(0 if success else 1)
