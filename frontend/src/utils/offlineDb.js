// offlineDb — penyimpanan ANTREAN KERJA LAPANGAN di perangkat (IndexedDB), Fase 35.
//
// Kenapa IndexedDB dan bukan localStorage: foto bukti harus disimpan sebagai Blob
// (localStorage hanya teks & ±5MB). Antrean WAJIB bertahan walau aplikasi ditutup atau
// HP mati — kalau tidak, pekerjaan sehari di lokasi tanpa sinyal bisa hilang.
const DB_NAME = "sipro-offline";
const DB_VERSION = 1;
export const JOBS = "jobs";
export const BLOBS = "blobs";

let dbPromise = null;

export function supported() {
  return typeof indexedDB !== "undefined";
}

function openDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(JOBS)) {
        const s = db.createObjectStore(JOBS, { keyPath: "id" });
        s.createIndex("status", "status");
        s.createIndex("created_at", "created_at");
      }
      if (!db.objectStoreNames.contains(BLOBS)) {
        db.createObjectStore(BLOBS, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

async function run(store, mode, fn) {
  if (!supported()) throw new Error("Perangkat ini tidak mendukung penyimpanan offline.");
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const os = tx.objectStore(store);
    let out;
    try {
      out = fn(os);
    } catch (e) {
      reject(e);
      return;
    }
    tx.oncomplete = () => resolve(out && out.result !== undefined ? out.result : out);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

function asList(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result || []);
    request.onerror = () => reject(request.error);
  });
}

// ------------------------------------------------------------------ pekerjaan (jobs)
export async function putJob(job) {
  await run(JOBS, "readwrite", (os) => os.put(job));
  return job;
}

export async function listJobs() {
  const db = await openDb();
  const tx = db.transaction(JOBS, "readonly");
  const rows = await asList(tx.objectStore(JOBS).getAll());
  return rows.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
}

export async function getJob(id) {
  const db = await openDb();
  const tx = db.transaction(JOBS, "readonly");
  return new Promise((resolve, reject) => {
    const r = tx.objectStore(JOBS).get(id);
    r.onsuccess = () => resolve(r.result || null);
    r.onerror = () => reject(r.error);
  });
}

export async function deleteJob(id) {
  const job = await getJob(id);
  for (const pid of (job?.photos || [])) {
    if (String(pid).startsWith("local:")) await deleteBlob(pid);
  }
  await run(JOBS, "readwrite", (os) => os.delete(id));
}

// ------------------------------------------------------------------ foto (blobs)
export async function putBlob(rec) {
  await run(BLOBS, "readwrite", (os) => os.put(rec));
  return rec.id;
}

export async function getBlob(id) {
  const db = await openDb();
  const tx = db.transaction(BLOBS, "readonly");
  return new Promise((resolve, reject) => {
    const r = tx.objectStore(BLOBS).get(id);
    r.onsuccess = () => resolve(r.result || null);
    r.onerror = () => reject(r.error);
  });
}

export async function deleteBlob(id) {
  await run(BLOBS, "readwrite", (os) => os.delete(id));
}

export async function listBlobs() {
  const db = await openDb();
  const tx = db.transaction(BLOBS, "readonly");
  return asList(tx.objectStore(BLOBS).getAll());
}

/** Total ukuran foto tertahan (untuk memberi tahu pengguna, bukan menebak). */
export async function pendingBytes() {
  const rows = await listBlobs();
  return rows.reduce((n, r) => n + (r.blob?.size || 0), 0);
}
