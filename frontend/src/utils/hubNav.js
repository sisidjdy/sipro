// hubNav.js — navigasi yang SADAR HUB (Fase 40c).
//
// Cacat NYATA yang ditutup (terlihat saat uji browser sesi ini): halaman yang dipakai DUA
// KALI — sebagai rute lama (`/build-calendar`) dan sebagai tab di hub `/build` — menuliskan
// keadaannya ke URL dengan pathname HARDCODE:
//
//     nav({ pathname: "/build-calendar", search: `?${q}` }, { replace: true })
//
// Akibatnya membuka `/build?hub=kalender` LANGSUNG TERPENTAL ke `/build-calendar`: tab yang
// baru diklik pemakai lenyap, konteks hub hilang, dan tombol Kembali terasa rusak.
//
// Perbaikannya bukan "berhenti sinkron ke URL" (tautan yang bisa dibagikan itu fitur nyata),
// melainkan menulis ke pathname YANG SEDANG DIPAKAI serta menjaga penanda `hub`.

export const BUILD_HUB_PATH = "/build";

/** Rute lama -> kunci tab di hub Pembangunan (lihat `pages/BuildHubPage.js`). */
export const BUILD_HUB_TABS = {
  "/construction": "progres",
  "/build-calendar": "kalender",
  "/field": "lapangan",
  "/build-calibration": "kalibrasi",
};

/** Pathname untuk menulis ulang query SENDIRI: tetap di hub bila memang sedang di hub. */
export function selfPath(currentPathname, legacyPath) {
  return currentPathname === BUILD_HUB_PATH ? BUILD_HUB_PATH : legacyPath;
}

/** Pertahankan penanda tab hub saat query ditulis ulang dari nol. */
export function keepHub(currentSearch, params) {
  const hub = new URLSearchParams(currentSearch).get("hub");
  if (hub) params.set("hub", hub);
  return params;
}

/** Tautan lintas layar: bila sedang di dalam hub, cukup pindah TAB (jangan keluar hub). */
export function crossLink(currentPathname, targetPath, search = "") {
  const tab = BUILD_HUB_TABS[targetPath];
  const clean = String(search || "").replace(/^\?/, "");
  if (currentPathname === BUILD_HUB_PATH && tab) {
    const q = new URLSearchParams(clean);
    q.set("hub", tab);
    return `${BUILD_HUB_PATH}?${q.toString()}`;
  }
  return clean ? `${targetPath}?${clean}` : targetPath;
}
