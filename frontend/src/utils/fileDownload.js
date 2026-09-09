import api from "@/services/apiClient";

/**
 * Unduh berkas dari endpoint yang mengirim berkas (XML/CSV/PDF).
 *
 * Kenapa ada helper: berkas pajak dikirim sebagai `StreamingResponse` dengan nama berkas di
 * header `Content-Disposition`. Bila nama itu diabaikan, pemakai menerima berkas bernama
 * "blob" yang tidak bisa dilacak masa pajaknya — jadi nama dari server SELALU dipakai.
 */
export async function downloadFile(url, { params, fallbackName = "berkas", open = false } = {}) {
  const res = await api.get(url, { params, responseType: "blob" });
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

/**
 * Ambil pesan galat yang JUJUR walau jawabannya bertipe blob.
 *
 * Ekspor pajak yang DITAHAN dijawab 409 berisi JSON ("Ekspor ditahan — NPWP pembeli belum
 * diisi…"). Karena permintaannya `responseType: "blob"`, axios menyerahkan Blob — tanpa
 * pembacaan ini pemakai hanya melihat "gagal mengunduh", bukan sebab yang bisa ditindak.
 */
export async function blobErrorDetail(err, fallback = "Permintaan gagal.") {
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
