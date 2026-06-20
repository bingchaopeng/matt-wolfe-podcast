// Background page for Edge - exports YouTube cookies to local server
// MV2 with persistent background page - works reliably in Edge

var SERVER = "http://127.0.0.1:9876";

function formatCookie(c) {
  var d = c.domain || ".youtube.com";
  var df = d.charAt(0) === "." ? "TRUE" : "FALSE";
  var hf = c.httpOnly ? "#HttpOnly_" : "";
  return hf + d + "\t" + df + "\t" + (c.path || "/") + "\t" + (c.secure ? "TRUE" : "FALSE") + "\t" + Math.max(Math.floor(c.expirationDate || 0), 0) + "\t" + c.name + "\t" + (c.value || "");
}

function exportCookies() {
  chrome.cookies.getAll({}, function(cookies) {
    var yt = cookies.filter(function(c) { return c.domain && c.domain.indexOf("youtube.com") !== -1; });
    if (yt.length < 5) {
      console.log("[CE] Not enough cookies:", yt.length);
      return;
    }

    var lines = [
      "# Netscape HTTP Cookie File",
      "# Exported by Cookie Auto-Exporter for Edge",
      "# Generated: " + new Date().toISOString(),
      ""
    ];
    yt.forEach(function(c) { lines.push(formatCookie(c)); });
    lines.push("");

    var xhr = new XMLHttpRequest();
    xhr.open("POST", SERVER + "/cookies", true);
    xhr.setRequestHeader("Content-Type", "text/plain");
    xhr.onload = function() {
      console.log("[CE] Sent " + yt.length + " cookies -> " + xhr.responseText);
    };
    xhr.send(lines.join("\n"));

    var essential = ["SAPISID","APISID","SSID","HSID","SID","__Secure-1PSID","__Secure-3PSID"];
    var found = yt.filter(function(c) { return essential.indexOf(c.name) !== -1; }).length;
    console.log("[CE] " + yt.length + " cookies (" + found + "/" + essential.length + " essential)");
  });
}

// Export immediately + retries
console.log("[CE] Loaded");
exportCookies();
setTimeout(exportCookies, 3000);
setTimeout(exportCookies, 8000);
setTimeout(exportCookies, 15000);
setTimeout(exportCookies, 30000);

chrome.runtime.onInstalled.addListener(function() { exportCookies(); });
chrome.runtime.onStartup.addListener(function() { exportCookies(); });
