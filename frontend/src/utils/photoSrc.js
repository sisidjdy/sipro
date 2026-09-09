// photoSrc — SATU tempat penentu URL gambar lapangan (staf & portal pembeli).
//
// Bug yang diperbaiki (Fase 28b): drawer kavling merender `\`${API}/files/${nilai}\``
// padahal nilai yang tersimpan bisa berupa **data URL base64** warisan Buku Harian /
// Punch List lama — hasilnya `/api/files/data:image/png;base64,...` → 404 & gambar rusak.
//
// Kontrak foto dari backend: `{ file_id, inline, label, date, scope }`.
//   * `file_id` → berkas nyata di object storage (butuh token pada query karena
//     tag <img> tidak bisa mengirim header Authorization).
//   * `inline`  → data URL warisan, dipakai apa adanya.
//
// Fase 30b: `variant: "thumb"` meminta versi kecil (±480 px) yang dibuat saat unggah —
// dipakai untuk GRID galeri supaya kuota pembeli tidak habis, sedangkan lightbox tetap
// memuat gambar penuh.
import { API, TOKEN_KEY } from "@/services/apiClient";
import { PORTAL_TOKEN_KEY } from "@/services/portalClient";

const rawValue = (photo) => {
  if (!photo) return "";
  if (typeof photo === "string") return photo;
  return photo.inline || photo.file_id || "";
};

/** URL <img src> untuk satu foto. `portal` memakai endpoint & token pembeli. */
export function photoSrc(photo, { portal = false, variant = null } = {}) {
  const v = String(rawValue(photo) || "");
  if (!v) return "";
  if (v.startsWith("data:") || v.startsWith("http")) return v;
  const token = localStorage.getItem(portal ? PORTAL_TOKEN_KEY : TOKEN_KEY) || "";
  const base = portal ? `${API}/portal/files/${v}` : `${API}/files/${v}`;
  const q = new URLSearchParams({ auth: token });
  if (variant) q.set("variant", variant);
  return `${base}?${q.toString()}`;
}

/** URL berkas apa pun (PDF bukti, lampiran) untuk dibuka di tab baru oleh staf. */
export function fileUrl(fileId, { variant = null } = {}) {
  if (!fileId) return "";
  return photoSrc({ file_id: fileId }, { variant });
}

/** Normalisasi bentuk lama (string / field `photo`) menjadi daftar objek foto. */
export function toPhotoList(doc, { label = "Dokumentasi", date = null, scope = "proyek" } = {}) {
  const list = Array.isArray(doc?.photos) && doc.photos.length
    ? doc.photos
    : (doc?.photo ? [doc.photo] : []);
  return list.map((v) => (typeof v === "string"
    ? { file_id: v.startsWith("data:") ? null : v, inline: v.startsWith("data:") ? v : null,
      label, date, scope }
    : v));
}

export const scopeLabel = (scope) => (scope === "unit" ? "kavling ini" : "lapangan proyek");
