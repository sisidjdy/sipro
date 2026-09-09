/**
 * panelLoad — pemuat data TAHAN-BANTING untuk halaman yang berisi banyak panel.
 *
 * CACAT NYATA YANG DITUTUP (Fase 52), dengan bukti server:
 * `LeadProfilePage` memuat enam permintaan sekaligus lewat `Promise.all`. Satu penolakan
 * membatalkan kelimanya yang lain, lalu cabang `catch` menyimpulkan status dari error mana
 * pun yang menang duluan. Untuk `finance@` dan `finlead@` — dua peran yang PUNYA
 * `leads:view_all` — `GET /api/appointments?lead_id=…` menjawab 403 sementara
 * `GET /api/leads/{id}` menjawab 200. Akibatnya SELURUH halaman profil lead (10 tab) diganti
 * satu kotak merah bertuliskan "Peran Anda tidak diberi akses ke data lead — bukan hanya lead
 * ini", padahal lead-nya baru saja terbaca 200 dan yang ditolak hanya panel jadwal survei.
 * Layar bukan cuma mati: layar BERBOHONG, dan menuduh izin yang salah.
 *
 * Aturan yang dipaksakan berkas ini:
 *   1. Permintaan PRIMER (identitas objek yang dibuka) yang gagal = halaman memang tidak
 *      bisa ditampilkan; kalimatnya diambil DARI ERROR PERMINTAAN ITU, bukan dari error
 *      panel mana pun.
 *   2. Permintaan PANEL yang gagal = panel itu saja yang berkata jujur. Sisa halaman hidup.
 *   3. "Tidak boleh dilihat" (403) TIDAK BOLEH ditampilkan sebagai "belum ada data" atau
 *      angka 0 — itu jenis kebohongan yang membuat orang mencari data yang tidak hilang.
 *   4. Kalimat teknis backend yang menyebut NAMA IZIN INTERNAL ("tidak memiliki izin 'view'
 *      pada 'appointments'") tidak pernah diteruskan ke layar; ia hanya dipakai untuk LOGIKA.
 */

export const PANEL_OK = "ok";
export const PANEL_DENIED = "denied";      // 403 — tidak boleh dilihat
export const PANEL_MISSING = "missing";    // 404 — memang tidak ada
export const PANEL_FAILED = "failed";      // 5xx/400 — gagal dimuat
export const PANEL_OFFLINE = "offline";    // tidak ada respons sama sekali

// Pola pesan penegak izin di backend (`rbac.require_permission`). Bocornya ke layar sudah
// pernah dikeluhkan pemakai di /construction, /materials, dan /tax.
const INTERNAL_PERMISSION_RE = /(tidak memiliki izin|akses ditolak)/i;

/**
 * readDetail — membaca `detail` dari galat axios SEBAGAI KALIMAT.
 *
 * FastAPI mengirim tiga bentuk berbeda: string (HTTPException), daftar objek (galat
 * validasi 422), dan kadang objek. Menyambungnya langsung ke JSX melahirkan
 * `[object Object]` di layar — cacat yang berulang kali ditemukan di repo ini.
 */
export function readDetail(err) {
  const raw = err?.response?.data?.detail ?? err?.response?.data?.message;
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw)) {
    return raw.map((d) => (typeof d === "string" ? d : d?.msg || "")).filter(Boolean).join("; ");
  }
  if (raw && typeof raw === "object") return String(raw.msg || raw.detail || "");
  return "";
}

/** Apakah kalimat ini membocorkan nama izin internal? */
export function isInternalPermissionMessage(text) {
  return INTERNAL_PERMISSION_RE.test(String(text || ""));
}

/** Ubah satu galat permintaan menjadi keadaan panel yang bisa diceritakan dengan jujur. */
export function classifyRequestError(err) {
  const status = Number(err?.response?.status || 0);
  const rawDetail = readDetail(err);
  let state = PANEL_FAILED;
  if (!err?.response) state = PANEL_OFFLINE;
  else if (status === 403) state = PANEL_DENIED;
  else if (status === 404) state = PANEL_MISSING;
  return {
    state,
    status,
    ok: false,
    denied: state === PANEL_DENIED,
    missing: state === PANEL_MISSING,
    offline: state === PANEL_OFFLINE,
    failed: state === PANEL_FAILED || state === PANEL_OFFLINE,
    // `detail` = aman untuk DITAMPILKAN. `rawDetail` = hanya untuk LOGIKA.
    detail: isInternalPermissionMessage(rawDetail) ? "" : rawDetail,
    rawDetail,
    data: undefined,
    res: undefined,
  };
}

const DEFAULT_PICK = (res) => res?.data?.data;

/**
 * loadPanels — jalankan semua permintaan, JANGAN saling membatalkan.
 *
 * `map` = { kunci: () => api.get(...) }. Nilainya boleh fungsi (disarankan, supaya galat
 * saat menyusun permintaan pun tertangkap) atau promise langsung.
 * Hasil: { kunci: { state, ok, denied, missing, failed, offline, status, detail, rawDetail,
 *                   data, res } }.
 */
export async function loadPanels(map, options = {}) {
  const pick = options.pick || DEFAULT_PICK;
  const keys = Object.keys(map || {});
  const settled = await Promise.allSettled(keys.map((key) => {
    const entry = map[key];
    try {
      return typeof entry === "function" ? entry() : entry;
    } catch (e) {
      return Promise.reject(e);
    }
  }));
  const out = {};
  keys.forEach((key, i) => {
    const s = settled[i];
    out[key] = s.status === "fulfilled"
      ? {
        state: PANEL_OK, ok: true, denied: false, missing: false, failed: false, offline: false,
        status: Number(s.value?.status || 200), detail: "", rawDetail: "",
        data: pick(s.value), res: s.value,
      }
      : classifyRequestError(s.reason);
  });
  return out;
}

/** Baris tabel dari satu panel — selalu array, walau panelnya gagal. */
export function panelRows(panel) {
  return Array.isArray(panel?.data) ? panel.data : [];
}

/**
 * honestBadge — angka pada tab HANYA bila datanya benar-benar terbaca.
 *
 * Panel yang ditolak/gagal mengembalikan `undefined` (TabPage tidak menggambar lencana),
 * bukan `0`. Lencana "0" pada tab yang sebenarnya tidak boleh dibuka adalah pernyataan
 * palsu: pemakai membaca "tidak ada survei" padahal artinya "Anda tidak boleh melihatnya".
 */
export function honestBadge(panel, count) {
  if (!panel || !panel.ok) return undefined;
  const n = count === undefined ? panelRows(panel).length : Number(count || 0);
  return n || undefined;
}

/**
 * omittedSources — daftar sumber yang TIDAK disertakan beserta sebabnya, untuk kalimat
 * jujur di layar (spanduk halaman & catatan di tab gabungan seperti Timeline).
 */
export function omittedSources(panels, labels) {
  return Object.entries(labels || {})
    .filter(([key]) => panels?.[key] && !panels[key].ok)
    .map(([key, label]) => {
      const p = panels[key];
      return {
        key,
        label,
        state: p.state,
        reason: p.denied ? "tidak boleh dibuka dengan peran Anda"
          : p.offline ? "tidak ada sambungan ke server"
            : p.missing ? "tidak ada datanya di sistem"
              : "gagal dimuat",
      };
    });
}

export default loadPanels;
