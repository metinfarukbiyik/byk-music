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

// ------------------------------------------------------------------------------
// Kurulum bildirimi ve kendini güncelleme
// Eklenti yüklendiğinde ya da tarayıcı açıldığında BYK Music'e haber verir; uygulama
// daha yeni bir eklenti sürümüyle geldiyse dosyalar zaten güncellenmiştir, eklenti
// kendini yeniden yükleyerek yeni sürüme geçer.
function browserName() {
  const ua = navigator.userAgent;
  if (ua.includes("Firefox/")) return "firefox";
  if (ua.includes("Edg/")) return "edge";
  if (ua.includes("OPR/")) return "opera";
  if (ua.includes("Vivaldi")) return "vivaldi";
  if (navigator.brave) return "brave";
  return "chrome";
}

function newer(a, b) {
  const pa = String(a || "0").split(".").map(Number);
  const pb = String(b || "0").split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) > (pb[i] || 0);
  }
  return false;
}

async function hello() {
  try {
    const me = chrome.runtime.getManifest().version;
    const data = await call("/hello", { version: me, browser: browserName() });
    if (data && newer(data.extension_version, me)) chrome.runtime.reload();
  } catch (e) {
    // BYK Music kapalıysa sessizce bekle
  }
}

chrome.runtime.onInstalled.addListener(hello);
chrome.runtime.onStartup.addListener(hello);
chrome.alarms.create("byk-hello", { periodInMinutes: 10 });
chrome.alarms.onAlarm.addListener((alarm) => alarm.name === "byk-hello" && hello());
