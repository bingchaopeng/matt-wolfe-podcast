// YouTube Cookie Auto-Exporter for yt-dlp
// Sends cookies to local bridge server at http://127.0.0.1:9876

const SERVER = "http://127.0.0.1:9876";

function formatCookie(c) {
  const d = c.domain || ".youtube.com";
  const df = d.startsWith(".") ? "TRUE" : "FALSE";
  const hf = c.httpOnly ? "#HttpOnly_" : "";
  return `${hf}${d}\t${df}\t${c.path || "/"}\t${c.secure ? "TRUE" : "FALSE"}\t${Math.max(Math.floor(c.expirationDate || 0), 0)}\t${c.name}\t${c.value || ""}`;
}

async function exportCookies() {
  try {
    const all = await chrome.cookies.getAll({});
    const yt = all.filter(c => c.domain && c.domain.includes("youtube.com"));
    if (yt.length < 5) {
      console.log("[CE] Not enough YT cookies:", yt.length);
      return;
    }

    const content = [
      "# Netscape HTTP Cookie File",
      "# Exported by Cookie Auto-Exporter",
      `# Generated: ${new Date().toISOString()}`,
      "",
      ...yt.map(formatCookie),
      ""
    ].join("\n");

    const r = await fetch(`${SERVER}/cookies`, {
      method: "POST",
      headers: {"Content-Type": "text/plain"},
      body: content
    });
    const text = await r.text();
    console.log("[CE] Sent", yt.length, "cookies ->", text);
  } catch(e) {
    console.log("[CE] Error:", e.message);
  }
}

// Wake up handlers
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.action === "wakeUp") {
    console.log("[CE] Woken up by content script");
    reply({ok: true});
  }
  if (msg.action === "exportCookies") {
    exportCookies().then(() => reply({ok: true}));
    return true;
  }
});

// Also try on events
chrome.runtime.onInstalled.addListener(() => { console.log("[CE] Installed"); exportCookies(); });
chrome.runtime.onStartup.addListener(() => { console.log("[CE] Startup"); exportCookies(); });
chrome.action.onClicked.addListener(() => { exportCookies(); });
