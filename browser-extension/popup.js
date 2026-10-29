const DEFAULTS = { detect: true, showButton: true };

chrome.runtime.sendMessage({ type: "ping" }, (r) => {
  const ok = r && r.ok;
  document.getElementById("dot").className = "dot " + (ok ? "ok" : "err");
  document.getElementById("state").textContent = ok
    ? `${r.data.app} v${r.data.version} bağlı`
    : "BYK Music açık değil";
});

chrome.storage.local.get(DEFAULTS, (s) => {
  for (const key of Object.keys(DEFAULTS)) {
    const box = document.getElementById(key);
    box.checked = s[key];
    box.addEventListener("change", () => chrome.storage.local.set({ [key]: box.checked }));
  }
});
