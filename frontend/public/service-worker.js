/* SIPRO service worker — Fase 35 (Papan Mandor tahan sinyal hilang).
 *
 * Kenapa perlu: mandor bekerja di lokasi yang sering kehilangan sinyal. Tanpa ini,
 * menyegarkan/membuka aplikasi saat offline = halaman kosong, dan pekerjaan sehari
 * bisa hilang. Service worker menyimpan "kerangka aplikasi" (HTML + JS/CSS) sehingga
 * aplikasi tetap terbuka; ANTREAN pengajuan & foto ditangani IndexedDB di sisi aplikasi.
 *
 * Strategi sengaja NETWORK-FIRST supaya saat online pengguna selalu dapat versi terbaru
 * (tidak ada bundel basi), dan cache hanya dipakai sebagai jaring saat jaringan mati.
 * Permintaan /api/* TIDAK PERNAH di-cache: data operasional harus jujur — kalau offline,
 * aplikasi menampilkan cuplikan terakhir beserta waktunya, bukan menyamar sebagai data kini.
 */
/* eslint-disable no-restricted-globals */
const CACHE = "sipro-shell-v1";
const SHELL = ["/", "/index.html"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => null))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

function skip(url, request) {
  if (request.method !== "GET") return true;
  if (url.origin !== self.location.origin) return true;
  if (url.pathname.startsWith("/api/")) return true;
  // Aset dev-server (hot reload / websocket) tidak boleh disentuh.
  if (url.pathname.includes("hot-update") || url.pathname.startsWith("/ws")
      || url.pathname.startsWith("/sockjs-node")) return true;
  return false;
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (skip(url, event.request)) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const fresh = await fetch(event.request);
      if (fresh && fresh.status === 200 && fresh.type !== "opaque") {
        cache.put(event.request, fresh.clone()).catch(() => null);
      }
      return fresh;
    } catch (err) {
      const hit = await cache.match(event.request);
      if (hit) return hit;
      if (event.request.mode === "navigate") {
        const shell = await cache.match("/index.html") || await cache.match("/");
        if (shell) return shell;
      }
      throw err;
    }
  })());
});
