import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
// Huruf di-host SENDIRI (bukan dari CDN Google Fonts). Dua alasan nyata:
//  1. Mandor lapangan memakai aplikasi ini di lokasi tanpa sinyal (Fase 35 antrean offline);
//     dengan CDN, judul & angka jatuh ke huruf sistem sehingga tampilan berubah-ubah.
//  2. Pemuatan CDN sempat gagal di jaringan kantor (permintaan woff2 Space Grotesk ditolak),
//     dan tampilannya jadi tidak konsisten antar halaman/kunjungan tanpa sebab yang jelas.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/600.css";
import "@fontsource/space-grotesk/700.css";
import "@fontsource/roboto-mono/400.css";
import "@fontsource/roboto-mono/500.css";
import "@/index.css";
import App from "@/App";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);

// Fase 35 — Papan Mandor tahan sinyal hilang: service worker menyimpan kerangka aplikasi
// supaya mandor tetap bisa membuka/menyegarkan aplikasi di lokasi tanpa sinyal. Strategi
// network-first (lihat public/service-worker.js) sehingga versi online selalu yang terbaru.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {
      /* offline shell hanyalah lapis tambahan; aplikasi tetap jalan tanpanya */
    });
  });
}
