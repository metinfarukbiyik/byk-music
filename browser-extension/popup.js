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

document.getElementById("sync").addEventListener("click", () => {
  const btn = document.getElementById("sync");
  const state = document.getElementById("syncState");
  btn.disabled = true;
  state.className = "";
  state.textContent = "Aktarılıyor…";
  chrome.runtime.sendMessage({ type: "cookies" }, (r) => {
    btn.disabled = false;
    if (r && r.ok) {
      state.className = "ok";
      state.textContent = "Oturum aktarıldı. BYK Music'te kitaplığınız açılıyor.";
    } else if (r && r.offline) {
      state.className = "err";
      state.textContent = "BYK Music açık değil. Uygulamayı başlatıp yeniden deneyin.";
    } else {
      state.className = "err";
      state.textContent = "Bu tarayıcıda YouTube'a giriş yapılmamış. Önce youtube.com'da oturum açın.";
    }
  });
});
