// offlineSync — MESIN ANTREAN kerja lapangan (Fase 35, diperluas Fase 50B).
//
// Aturan yang dijaga di sini:
//  * Aksi & foto tersimpan dulu di perangkat, terkirim sendiri saat jaringan kembali.
//  * Tidak ada pengajuan DOBEL: setiap pekerjaan antrean punya `client_ref` dan backend
//    memutar ulang hasil lama bila ref itu sudah pernah diterima.
//  * Antrean tidak pernah berbohong: kalau server MENOLAK (mis. gerbang mutu terkunci),
//    statusnya jadi "ditolak" beserta alasan asli server — bukti TIDAK dihapus.
//
// Fase 50B — SATU antrean untuk semua pekerjaan lapangan. Sebelumnya hanya pengajuan hasil
// kerja unit (`build_submit`/`build_start`) yang bisa mengantre, padahal tiga pekerjaan yang
// PALING sering dilakukan di lokasi tanpa sinyal justru absensi harian, buku harian proyek,
// dan temuan punch list. Untuk ketiganya dulu hanya ada dua pilihan buruk: tekan ulang lalu
// data masuk dua kali (absensi ganda = upah ganda), atau tidak tekan ulang lalu pekerjaan
// seharian hilang tanpa jejak. Sekarang semuanya lewat satu pintu, ber-`client_ref`, dan
// terlihat di satu panel antrean.
import api from "@/services/apiClient";
import * as odb from "@/utils/offlineDb";

const listeners = new Set();
let flushing = false;

const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
const iso = () => new Date().toISOString();

// Label antrean TIDAK ditulis di sini: kamus datanya ada di SSOT `/api/reference`
// (grup `offline_queue_kind` & `offline_queue_status`) dan dibaca lewat useReference()
// di panel antrean, supaya tidak ada dua versi label untuk hal yang sama.

// Peta jenis pekerjaan antrean → endpoint & nama field foto pada kontrak endpoint itu.
// Ditulis SEKALI di sini supaya panel antrean, dialog, dan mesin kirim memakai satu aturan.
export const KINDS = {
  build_submit: { method: "post", photoField: "photo_file_ids" },
  build_start: { method: "post", photoField: null },
  attendance_submit: { method: "post", endpoint: "/labor/attendance", photoField: null },
  field_diary: { method: "post", endpoint: "/field/diary", photoField: "photos" },
  punch_create: { method: "post", endpoint: "/field/punchlist", photoField: "photos" },
  punch_status: { method: "post", photoField: "photos" },
  warranty_claim: { method: "post", endpoint: "/handover/claims", photoField: "photo_file_ids" },
  warranty_fix: { method: "post", photoField: "photo_file_ids" },
};

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function ping() {
  listeners.forEach((f) => {
    try { f(); } catch { /* pendengar rusak tidak boleh menghentikan antrean */ }
  });
}

export function isOnline() {
  return typeof navigator === "undefined" ? true : navigator.onLine !== false;
}

/** Penanda kiriman: dipakai juga saat ONLINE supaya percobaan ulang tetap idempoten. */
export function newRef() {
  return `q-${uid()}`;
}

/** Simpan foto di perangkat; kembalikan id lokal `local:<id>` untuk dipakai UI. */
export async function storePhoto({ blob, name, type, ownerId, watermark, geo }) {
  const id = `local:${uid()}`;
  await odb.putBlob({ id, blob, name: name || "foto.jpg", type: type || "image/jpeg",
    owner_id: ownerId || null, watermark: watermark || null, geo: geo || null,
    created_at: iso() });
  return id;
}

export function isLocalPhoto(id) {
  return String(id || "").startsWith("local:");
}

export function hasLocalPhoto(ids) {
  return (ids || []).some(isLocalPhoto);
}

export async function queueSubmit({ item, note, checklist, geo, photos }) {
  const job = {
    id: uid(), kind: "build_submit", client_ref: newRef(),
    item_id: item.id, unit_code: item.unit_code, step_code: item.step_code,
    name: item.name, payload: { note, checklist: checklist || [], geo: geo || null },
    photos: photos || [], status: "pending", attempts: 0, last_error: null,
    created_at: iso(),
  };
  await odb.putJob(job);
  ping();
  return job;
}

export async function queueStart(item) {
  const job = {
    id: uid(), kind: "build_start", client_ref: newRef(),
    item_id: item.id, unit_code: item.unit_code, step_code: item.step_code,
    name: item.name, payload: {}, photos: [], status: "pending", attempts: 0,
    last_error: null, created_at: iso(),
  };
  await odb.putJob(job);
  ping();
  return job;
}

/**
 * Antre pekerjaan lapangan APA PUN (Fase 50B).
 *
 * `title` dipakai panel antrean untuk menjelaskan pekerjaan dalam bahasa manusia
 * ("Absensi 12 Agu · Cluster Asri"), karena mandor tidak bisa menilai antrean dari id.
 */
export async function queueJob({ kind, endpoint, payload, photos, title, clientRef }) {
  const spec = KINDS[kind];
  if (!spec) throw new Error(`Jenis antrean tidak dikenal: ${kind}`);
  const job = {
    id: uid(), kind, client_ref: clientRef || newRef(),
    endpoint: endpoint || spec.endpoint, title: title || null,
    payload: payload || {}, photos: photos || [], status: "pending", attempts: 0,
    last_error: null, created_at: iso(),
  };
  if (!job.endpoint) throw new Error(`Antrean ${kind} butuh endpoint.`);
  await odb.putJob(job);
  ping();
  return job;
}

/**
 * Kirim SEKARANG bila online, ANTRE bila tidak — satu pintu untuk semua form lapangan.
 *
 * Kembalikan `{ queued: true, job }` bila masuk antrean, atau `{ queued: false, res }`
 * bila server sudah menerimanya. Foto yang masih tersimpan di perangkat (`local:…`)
 * memaksa pekerjaan masuk antrean, karena bukti harus terunggah lebih dulu.
 */
export async function submitOrQueue({ kind, endpoint, payload, photos = [], title }) {
  const spec = KINDS[kind] || {};
  const target = endpoint || spec.endpoint;
  const localPhotos = hasLocalPhoto(photos);
  if (!isOnline() || localPhotos) {
    const job = await queueJob({ kind, endpoint: target, payload, photos, title });
    return { queued: true, job };
  }
  const ref = newRef();
  const bodyPayload = { ...payload, client_ref: ref };
  if (spec.photoField && photos.length) bodyPayload[spec.photoField] = photos;
  try {
    const res = await api.post(target, bodyPayload);
    return { queued: false, res };
  } catch (e) {
    // Tidak ada jawaban server (sinyal mati di tengah kiriman) → simpan supaya tidak hilang.
    if (!e?.response) {
      const job = await queueJob({ kind, endpoint: target, payload, photos, title,
        clientRef: ref });
      return { queued: true, job, offlineError: true };
    }
    throw e;
  }
}

export async function list() {
  if (!odb.supported()) return [];
  try { return await odb.listJobs(); } catch { return []; }
}

export async function remove(id) {
  await odb.deleteJob(id);
  ping();
}

export async function retry(id) {
  const job = await odb.getJob(id);
  if (!job) return;
  await odb.putJob({ ...job, status: "pending", last_error: null });
  ping();
  return flush({ force: true });
}

async function uploadPhotos(job) {
  const ids = [];
  for (const pid of job.photos || []) {
    if (!isLocalPhoto(pid)) { ids.push(pid); continue; }
    const rec = await odb.getBlob(pid);
    if (!rec) continue;                       // sudah terunggah pada percobaan sebelumnya
    const fd = new FormData();
    fd.append("file", rec.blob, rec.name);
    fd.append("owner_type", "build");
    if (rec.owner_id) fd.append("owner_id", rec.owner_id);
    if (rec.watermark) fd.append("watermark", rec.watermark);
    if (rec.geo?.lat && rec.geo?.lng) {
      fd.append("lat", rec.geo.lat);
      fd.append("lng", rec.geo.lng);
      if (rec.geo.accuracy) fd.append("accuracy", rec.geo.accuracy);
      if (rec.geo.captured_at) fd.append("captured_at", rec.geo.captured_at);
    }
    const res = await api.post("/files/upload", fd);
    const newId = res.data?.data?.id;
    if (!newId) throw new Error("Server tidak mengembalikan id berkas.");
    ids.push(newId);
    // Ganti id lokal dengan id nyata SEKARANG supaya percobaan berikutnya tidak
    // mengunggah foto yang sama dua kali (bukti ganda = audit kotor).
    const swapped = (job.photos || []).map((p) => (p === pid ? newId : p));
    await odb.putJob({ ...job, photos: swapped });
    job.photos = swapped;
    await odb.deleteBlob(pid);
  }
  return ids;
}

async function send(job) {
  const ids = await uploadPhotos(job);
  if (job.kind === "build_submit") {
    await api.post(`/build/items/${job.item_id}/submit`, {
      note: job.payload.note,
      photo_file_ids: ids,
      geo: job.payload.geo || null,
      checklist: job.payload.checklist || [],
      client_ref: job.client_ref,
    });
    return;
  }
  if (job.kind === "build_start") {
    await api.post(`/build/items/${job.item_id}/start`);
    return;
  }
  // Fase 50B — pekerjaan lapangan lain: endpoint & nama field foto ikut dalam pekerjaan.
  const spec = KINDS[job.kind];
  if (!spec || !job.endpoint) throw new Error(`Jenis antrean tidak dikenal: ${job.kind}`);
  const payload = { ...(job.payload || {}), client_ref: job.client_ref };
  if (spec.photoField && ids.length) payload[spec.photoField] = ids;
  await api.post(job.endpoint, payload);
}

/** Kirim seluruh antrean. Aman dipanggil berkali-kali (tidak tumpang tindih). */
export async function flush() {
  if (flushing || !isOnline() || !odb.supported()) return { sent: 0, failed: 0 };
  flushing = true;
  let sent = 0;
  let failed = 0;
  try {
    const jobs = (await list()).filter((j) => j.status === "pending");
    for (const job of jobs) {
      await odb.putJob({ ...job, status: "sending", last_error: null });
      ping();
      try {
        await send(job);
        await odb.deleteJob(job.id);
        sent += 1;
      } catch (e) {
        const status = e?.response?.status;
        const detail = e?.response?.data?.detail || e?.message || "Gagal mengirim.";
        const fresh = (await odb.getJob(job.id)) || job;
        if (status && status >= 400 && status < 500) {
          // Server menolak dengan ALASAN (aturan Fase 31/32 tetap berlaku): tampilkan
          // apa adanya, jangan buang buktinya.
          await odb.putJob({ ...fresh, status: "rejected",
            last_error: typeof detail === "string" ? detail : JSON.stringify(detail),
            attempts: (fresh.attempts || 0) + 1 });
        } else {
          await odb.putJob({ ...fresh, status: "pending",
            last_error: typeof detail === "string" ? detail : "Gagal mengirim.",
            attempts: (fresh.attempts || 0) + 1 });
        }
        failed += 1;
        ping();
        if (!isOnline()) break;
      }
    }
  } finally {
    flushing = false;
    ping();
  }
  return { sent, failed };
}
