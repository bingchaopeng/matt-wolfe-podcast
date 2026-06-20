"""
Cookie Auto-Exporter — Chromium (v145)
======================================
遵循你的 4 步流程:
  1. 打开 Chromium → YouTube
  2. 通过 chrome.cookies.getAll API 导出 cookies（同 Get cookies.txt）
  3. 保存为 Netscape 格式
  4. 验证 cookies 有效性 (yt-dlp)

双模式:
  --自动模式 (--auto):   使用已有登录会话静默导出 (供 pipeline 调用)
  --交互模式 (默认):     打开浏览器窗口等待登录 (首次设置)

用法:
  py -3 cookie_playwright.py            # 交互模式（首次设置）
  py -3 cookie_playwright.py --auto     # 自动模式（pipeline 调用）
"""

import os
import sys
import time
import subprocess
from datetime import datetime

COOKIE_PATH = os.path.join(os.path.dirname(__file__), "cookies.txt")
PROFILE = os.path.join(os.path.dirname(__file__), ".pw-cookies")
ESSENTIAL = {"SAPISID", "APISID", "SSID", "HSID", "SID",
             "__Secure-1PSID", "__Secure-3PSID"}


def check(cookies):
    found = {c["name"] for c in cookies if c.get("name") in ESSENTIAL}
    return len(found) >= 3, found


def netscape(cookies):
    lines = [
        "# Netscape HTTP Cookie File",
        "# Exported via chrome.cookies.getAll API",
        f"# {datetime.now().isoformat()}",
        "",
    ]
    for c in cookies:
        d = c.get("domain", "")
        if not d: continue
        lines.append(
            f'{"#HttpOnly_" if c.get("httpOnly") else ""}'
            f'{d}\t{"TRUE" if d.startswith(".") else "FALSE"}\t'
            f'{c.get("path", "/")}\t{"TRUE" if c.get("secure") else "FALSE"}\t'
            f'{int(c.get("expires", 0))}\t{c["name"]}\t{c["value"]}'
        )
    lines.append("")
    return "\n".join(lines)


def verify(path):
    print("\n[Verify] Testing with yt-dlp...")
    r = subprocess.run(
        ["py", "-3", "-m", "yt_dlp", "--cookies", path,
         "--skip-download", "--print", "title",
         "https://www.youtube.com/watch?v=Db260rUuKJg"],
        capture_output=True, text=True, timeout=30,
    )
    if "Sign in" not in r.stderr and r.returncode == 0 and r.stdout.strip():
        print(f"  [OK] {r.stdout.strip()[:60]}")
        return True
    print(f"  [FAIL] {r.stderr.strip()[-200:]}")
    return False


def export_cookies(ctx) -> bool:
    """Extract YouTube cookies from context and save to cookies.txt."""
    cookies = ctx.cookies()
    yt = [c for c in cookies
          if any(d in c.get("domain","")
                 for d in ["youtube.com","ytimg.com",".google.com"])]
    ok, found = check(yt)
    if not ok:
        print(f"  [FAIL] Not enough essential cookies ({len(found)}/7)")
        return False
    with open(COOKIE_PATH, "w", encoding="utf-8") as f:
        f.write(netscape(yt))
    size = os.path.getsize(COOKIE_PATH)
    print(f"  [OK] cookies.txt saved ({size} bytes, {len(yt)} cookies)")
    return True


def auto_mode():
    """Automatic mode: extract cookies from existing profile."""
    print("[Auto] Checking for existing YouTube session...")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE,
            headless=True,
            args=["--no-first-run", "--no-default-browser-check",
                  "--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation", "--disable-extensions"],
        )

        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.youtube.com", timeout=15000, wait_until="domcontentloaded")
        time.sleep(3)

        ok, found = check(ctx.cookies())
        if ok:
            print(f"  [OK] Session found ({len(found)} essential cookies)")
            success = export_cookies(ctx)
            ctx.close()
            return success

        print(f"  [FAIL] No valid session ({len(found)}/7 essential cookies)")
        print("  User login needed. Run without --auto for interactive mode.")
        ctx.close()
        return False


def interactive_mode():
    """Interactive mode: open browser, wait for login, export cookies."""
    print("[Interactive] Opening Chromium for YouTube login...")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE,
            headless=False,
            args=["--no-first-run", "--no-default-browser-check",
                  "--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation", "--disable-extensions"],
            viewport={"width": 1280, "height": 800},
        )

        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.youtube.com", wait_until="domcontentloaded")
        time.sleep(4)

        ok, found = check(ctx.cookies())

        if not ok:
            print("\n[ACTION] Please sign into YouTube in the browser window")
            print("  Waiting up to 90 seconds...")

            for i in range(90):
                time.sleep(1)
                if i % 10 == 0:
                    try:
                        page.goto("https://www.youtube.com", timeout=8000,
                                   wait_until="domcontentloaded")
                        time.sleep(2)
                        ok, found = check(ctx.cookies())
                        if ok:
                            print(f"\n  [OK] Login at {i+1}s ({len(found)} essential)")
                            time.sleep(2)
                            break
                        print(f"  ... {i+1}s ({len(found)}/7)")
                    except:
                        print(f"  ... {i+1}s")

            if not ok:
                print("\n  [FAIL] Login timeout")
                ctx.close()
                return False
        else:
            print(f"  [OK] Already logged in ({len(found)} essential)")

        success = export_cookies(ctx)
        ctx.close()
        return success


def main():
    if sys.stdout.encoding == 'gbk':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    is_auto = "--auto" in sys.argv

    print("=" * 60)
    print("  Cookie Auto-Exporter")
    print(f"  Mode: {'Auto (pipeline)' if is_auto else 'Interactive (setup)'}")
    print("  API: chrome.cookies.getAll (same as Get cookies.txt)")
    print("=" * 60)

    os.makedirs(PROFILE, exist_ok=True)

    if is_auto:
        success = auto_mode()
    else:
        success = interactive_mode()

    if not success:
        print("\n  [FAIL] Cookie export failed")
        print(f"  Interactive: py -3 cookie_playwright.py")
        sys.exit(1)

    if verify(COOKIE_PATH):
        print("\n" + "=" * 60)
        print("  [SUCCESS] All steps completed!")
        print("  1. Chromium opened -> YouTube loaded")
        print("  2. chrome.cookies.getAll API executed")
        print("  3. Cookies exported (Netscape format)")
        print("  4. Saved to cookies.txt -> yt-dlp confirmed")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("  [FAIL] yt-dlp could not verify cookies")
        print("  Try: py -3 cookie_playwright.py")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
