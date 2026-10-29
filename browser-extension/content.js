// YouTube sayfasında açık olan videoyu algılar, videonun altındaki düğme satırına
// "BYK · MP3 · MP4" düğmesi ekler ve BYK Music masaüstü uygulamasına iletir.
(() => {
  const SETTINGS = { showButton: true, detect: true };
  let lastUrl = "";

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
      document.querySelector("ytd-watch-metadata h1 yt-formatted-string") ||
      document.querySelector("ytmusic-player-bar .title") ||
      document.querySelector("yt-dynamic-sizing-formatted-string, h1.ytd-playlist-header-renderer");
    const text = (el && el.textContent.trim()) || document.title;
    return text.replace(/^\(\d+\)\s*/, "").replace(/\s*-\s*YouTube( Music)?$/, "").trim();
  }

  // ------------------------------------------------ videonun yanındaki düğme
  function buildButton() {
    const box = document.createElement("div");
    box.id = "byk-inline";
    box.innerHTML = `
      <span class="byk-mark" title="BYK Music ile indir">♫</span>
      <button class="byk-opt" data-f="mp3" title="MP3 olarak indir">MP3</button>
      <span class="byk-sep"></span>
      <button class="byk-opt" data-f="mp4" title="MP4 olarak indir">MP4</button>`;
    box.querySelectorAll(".byk-opt").forEach((b) =>
      b.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const item = current();
        if (!item) return;
        const label = b.textContent;
        b.disabled = true;
        const r = await send("add", { url: item.url, title: title(), format: b.dataset.f });
        b.textContent = r.ok ? "✓" : "!";
        b.title = r.ok ? "BYK Music'e eklendi" : "BYK Music açık değil";
        box.classList.toggle("byk-err", !r.ok);
        setTimeout(() => {
          b.textContent = label;
          b.disabled = false;
          box.classList.remove("byk-err");
        }, 2200);
      })
    );
    return box;
  }

  function placeButton() {
    const existing = document.getElementById("byk-inline");
    const item = current();
    if (!SETTINGS.showButton || !item || item.kind !== "video") {
      if (existing) existing.remove();
      return;
    }
    // YouTube'un Beğen / Paylaş düğmelerinin bulunduğu satır
    const anchor =
      document.querySelector("ytd-watch-metadata #actions #top-level-buttons-computed") ||
      document.querySelector("ytd-watch-metadata #actions-inner") ||
      document.querySelector("ytd-watch-metadata #title");
    if (!anchor) return;
    if (existing && existing.previousElementSibling === anchor) return;
    if (existing) existing.remove();
    anchor.insertAdjacentElement("afterend", buildButton());
  }

  // ------------------------------------------------------ algılama
  function update() {
    placeButton();
    const item = current();
    if (!item || item.url === lastUrl) return;
    lastUrl = item.url;
    const key = item.url;
    // Başlığın yüklenmesi için kısa bir süre bekle
    setTimeout(() => {
      const now = current();
      if (SETTINGS.detect && now && now.url === key) send("detect", { url: key, title: title() });
    }, 1500);
  }

  chrome.storage.local.get(SETTINGS, (s) => {
    Object.assign(SETTINGS, s);
    update();
    document.addEventListener("yt-navigate-finish", update);
    window.addEventListener("popstate", update);
    setInterval(update, 1500); // YouTube sayfa içeriğini sonradan yüklediği için
  });

  chrome.storage.onChanged.addListener((changes) => {
    for (const [k, v] of Object.entries(changes)) SETTINGS[k] = v.newValue;
    update();
  });
})();
