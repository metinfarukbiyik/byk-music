// YouTube sayfasında açık olan videoyu algılar ve BYK Music'e iletir.
(() => {
  const SETTINGS = { showButton: true, detect: true, format: "mp3" };
  let lastUrl = "";
  let root = null;

  const send = (type, payload) =>
    new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type, payload }, (r) => resolve(r || { ok: false }));
      } catch (e) {
        resolve({ ok: false }); // eklenti yeniden yüklendiyse
      }
    });

  function current() {
    const u = new URL(location.href);
    const base = u.hostname.startsWith("music.") ? "https://music.youtube.com" : "https://www.youtube.com";
    let id = u.searchParams.get("v");
    if (!id && u.pathname.startsWith("/shorts/")) id = u.pathname.split("/")[2];
    const list = u.searchParams.get("list");
    if (id) return { kind: "video", url: `${base}/watch?v=${id}` };
    if (u.pathname === "/playlist" && list) return { kind: "playlist", url: `${base}/playlist?list=${list}` };
    return null;
  }

  function title() {
    const el =
      document.querySelector("h1.ytd-watch-metadata yt-formatted-string") ||
      document.querySelector("ytmusic-player-bar .title") ||
      document.querySelector("h1.ytd-playlist-header-renderer, yt-dynamic-sizing-formatted-string");
    const text = (el && el.textContent.trim()) || document.title;
    return text.replace(/^\(\d+\)\s*/, "").replace(/\s*-\s*YouTube( Music)?$/, "").trim();
  }

  function toast(text, ok) {
    if (!root) return;
    const status = root.querySelector(".byk-status");
    status.textContent = text;
    status.className = "byk-status " + (ok ? "ok" : "err");
    status.hidden = false;
    clearTimeout(status._t);
    status._t = setTimeout(() => (status.hidden = true), 3500);
  }

  async function add(format) {
    const item = current();
    if (!item) return;
    const r = await send("add", { url: item.url, title: title(), format });
    toast(r.ok ? "BYK Music'e gönderildi ✓" : "BYK Music açık değil. Uygulamayı başlatın.", r.ok);
  }

  function buildButton() {
    root = document.createElement("div");
    root.id = "byk-music-root";
    root.innerHTML = `
      <div class="byk-status" hidden></div>
      <div class="byk-bar">
        <span class="byk-logo">♫</span>
        <button class="byk-btn" data-f="mp3">MP3</button>
        <button class="byk-btn" data-f="mp4">MP4</button>
      </div>`;
    root.querySelectorAll(".byk-btn").forEach((b) => b.addEventListener("click", () => add(b.dataset.f)));
    root.title = "BYK Music ile indir";
    document.documentElement.appendChild(root);
  }

  function update() {
    const item = current();
    if (root) root.hidden = !SETTINGS.showButton || !item;
    if (!item) return;
    const key = item.url;
    if (key === lastUrl) return;
    lastUrl = key;
    // Başlığın yüklenmesi için kısa bir süre bekle
    setTimeout(() => {
      if (SETTINGS.detect && current() && current().url === key) send("detect", { url: key, title: title() });
    }, 1500);
  }

  chrome.storage.local.get(SETTINGS, (s) => {
    Object.assign(SETTINGS, s);
    buildButton();
    update();
    document.addEventListener("yt-navigate-finish", update);
    window.addEventListener("popstate", update);
    setInterval(update, 2000); // YouTube Music ve tek sayfa geçişleri için
  });

  chrome.storage.onChanged.addListener((changes) => {
    for (const [k, v] of Object.entries(changes)) SETTINGS[k] = v.newValue;
    lastUrl = "";
    update();
  });
})();
