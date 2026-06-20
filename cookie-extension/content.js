// Content script - wakes up the background service worker on YouTube pages
console.log("[CE-content] Loaded on YouTube, waking up service worker...");
chrome.runtime.sendMessage({action: "wakeUp"});
chrome.runtime.sendMessage({action: "exportCookies"});
