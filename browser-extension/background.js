// BYK Music masaüstü uygulamasıyla yalnızca bu bilgisayar üzerinden (127.0.0.1) iletişim kurar.
const APP = "http://127.0.0.1:47815";

async function call(path, body) {
  const options = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : { method: "GET" };
  const res = await fetch(APP + path, options);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

// Yalnızca kullanıcı açılır penceredeki "oturumu aktar" düğmesine bastığında çağrılır.
function youtubeCookies() {
  return new Promise((resolve) => chrome.cookies.getAll({ domain: "youtube.com" }, (list) => resolve(list || [])));
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "cookies") {
    youtubeCookies()
      .then((cookies) => call("/cookies", { cookies }))
      .then((data) => sendResponse({ ok: !!data.ok, data }))
      .catch(() => sendResponse({ ok: false, offline: true }));
    return true;
  }
  const route = { ping: ["/ping"], detect: ["/detect", msg.payload], add: ["/add", msg.payload] }[msg.type];
  if (!route) return false;
  call(...route)
    .then((data) => sendResponse({ ok: true, data }))
    .catch(() => sendResponse({ ok: false }));
  return true; // yanıt eşzamansız gönderilecek
});
