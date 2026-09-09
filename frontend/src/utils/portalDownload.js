import portalApi from "@/services/portalClient";

/**
 * Unduh/buka berkas milik PEMBELI dari portal.
 *
 * Kenapa tidak `<a href="…?auth=token">`: cara itu menempelkan token sesi pembeli ke URL
 * (masuk riwayat peramban & log proxy), dan galatnya muncul sebagai halaman JSON mentah —
 * pembeli melihat `{"detail":"…"}` alih-alih kalimat yang bisa ditindak. Pola ini sama
 * dengan `utils/fileDownload.js` di sisi staf (pelajaran Fase 50 pada tombol PDF BAST),
 * hanya memakai klien portal supaya kredensial staf & pembeli tidak pernah bercampur.
 */
export async function portalDownload(url, { fallbackName = "berkas", open = true } = {}) {
  const res = await portalApi.get(url, { responseType: "blob" });
  const disp = String(res.headers?.["content-disposition"] || "");
  const match = /filename=([^;]+)/i.exec(disp);
  const name = (match ? match[1] : fallbackName).replace(/["']/g, "").trim();
  const type = res.headers?.["content-type"] || "application/octet-stream";
  const href = URL.createObjectURL(new Blob([res.data], { type }));
  if (open) {
    window.open(href, "_blank", "noopener");
  } else {
    const a = document.createElement("a");
    a.href = href;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  setTimeout(() => URL.revokeObjectURL(href), 30000);
  return name;
}

/** Pesan galat yang JUJUR walau jawabannya bertipe blob (mis. 404 "bukan milik Anda"). */
export async function portalBlobError(err, fallback = "Berkas gagal dibuka.") {
  const data = err?.response?.data;
  if (data && typeof data.text === "function") {
    try {
      const parsed = JSON.parse(await data.text());
      if (parsed?.detail) return parsed.detail;
    } catch (e) {
      return fallback;
    }
  }
  return data?.detail || fallback;
}
