"""PUSAT KONFIGURASI — registry setting bisnis (Fase 39).

Masalah yang diperbaiki: aturan bisnis (masa keep unit, persentase DP, potongan
pembatalan, hari toleransi cicilan, tarif PPh, dst) tersebar sebagai ANGKA MATI di kode
atau tidak ada sama sekali. Akibatnya kebijakan tidak bisa diubah tanpa deploy dan tidak
ada jejak siapa mengubah apa.

Aturan modul ini:
  1. DEFAULTS ada di KODE — sistem tetap jalan walau koleksi `settings` kosong.
  2. DB hanya menyimpan yang DIUBAH (override), berlapis: org → project → cluster.
  3. Setting `sensitive` WAJIB alasan saat diubah; semua perubahan masuk `history`.
  4. Nilai divalidasi (tipe, min/max, pilihan) — setting salah tidak boleh merusak sistem.

Angka default yang berasal dari dokumen legal owner (SPR Cash/Cash Bertahap/KPR + SPKT)
ditandai `src="DOC"` supaya jelas mana yang punya dasar dokumen dan mana yang usulan sistem.
"""
import logging
import time

from core_utils import new_id, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.settings")

SCOPES = ("org", "project", "cluster")
TYPES = ("int", "pct", "money", "bool", "str", "enum", "list", "obj")
_CACHE = {"at": 0.0, "rows": {}}
_TTL = 3.0


def _d(key, value, type_, group, label, help_, *, impact="", sensitive=False, minimum=None,
       maximum=None, options=None, src="SISTEM", ref_group=None):
    # CFG-03: enum WAJIB menunjuk grup registry (/api/reference) supaya label pilihan satu sumber.
    if type_ == "enum" and not ref_group:
        raise ValueError(f"Setting enum '{key}' harus punya ref_group")
    if ref_group:
        import reference as _ref
        options = list(_ref.values(ref_group))
    return {
        "key": key, "value": value, "type": type_, "group": group, "label": label,
        "help": help_, "impact": impact, "sensitive": sensitive, "min": minimum,
        "max": maximum, "options": options or [], "source": src, "ref_group": ref_group,
    }


# ---------------------------------------------------------------- DEFAULTS
DEFAULTS: dict = {d["key"]: d for d in [
    # ============ reservasi / keep unit ============
    _d("reservation.max_active_per_lead", 1, "int", "reservasi",
       "Maksimum unit aktif per lead",
       "Berapa unit yang boleh dipegang satu calon pembeli pada waktu yang sama.",
       impact="Menaikkan nilai ini membuat stok unit tampak habis padahal dipegang satu orang.",
       sensitive=True, minimum=1, maximum=5),
    _d("reservation.hold_days", 7, "int", "reservasi", "Masa keep unit (hari)",
       "Lama unit dipegang sebelum otomatis dilepas bila tidak ada kelanjutan.",
       impact="Terlalu panjang = unit mati; terlalu pendek = pembeli serius kehilangan unit.",
       minimum=1, maximum=90, src="DOC"),
    _d("reservation.override_roles", ["sales_manager", "super_admin"], "list", "reservasi",
       "Peran yang boleh override batas reservasi",
       "Hanya peran ini yang boleh melewati batas 1 unit per lead, dan wajib beralasan.",
       sensitive=True),
    _d("reservation.require_booking_fee_before_spr", True, "bool", "reservasi",
       "Booking fee wajib sebelum SPR",
       "SPR tidak bisa diterbitkan sebelum booking fee tercatat.", sensitive=True, src="DOC"),
    # ============ lead ============
    _d("lead.won_trigger", "spr_signed", "enum", "lead", "Pemicu lead menjadi Customer",
       "Peristiwa yang mengubah lead menjadi customer (akhir lifecycle lead).",
       impact="Menentukan kapan proses legal berpindah ke domain Customer.",
       sensitive=True, ref_group="lead_won_trigger"),
    # ============ SLA & umur tahap (Fase 41) ============
    # Ambang ini DULU angka mati di komponen frontend (72 jam di daftar Lead, 48 di Tugas &
    # Komplain, 168 di Deal, 336 di Pembeli, 720 di AR). Sekarang satu tempat, dan
    # `stage_clock.resync()` memberlakukannya ke baris yang sudah ada. Nilai 0 = tahap akhir
    # (tidak ada janji waktu) — UI menulis "tanpa SLA", bukan "dalam SLA".
    _d("lead.sla_hours", {"acquisition": 0.25, "nurturing": 48, "appointment": 72,
                          "booking": 168, "spr": 168, "won": 0, "lost": 0, "recycle": 0,
                          "default": 72}, "obj", "sla",
       "SLA tindak lanjut lead per tahap (jam)",
       "Batas waktu tindak lanjut tiap tahap lead; lewat batas memicu eskalasi ke supervisor."),
    _d("deal.sla_hours", {"reserved": 72, "booked": 720, "completed": 0, "cancelled": 0,
                          "default": 168}, "obj", "sla",
       "SLA tiap status deal (jam)",
       "Reservasi wajib berlanjut ke booking; booking wajib berlanjut ke PPJB/akad."),
    _d("task.sla_hours", {"open": 24, "in_progress": 48, "submitted": 24, "snoozed": 72,
                          "done": 0, "cancelled": 0, "default": 48}, "obj", "sla",
       "SLA tiap status tugas (jam)",
       "Batas wajar tugas menganggur pada satu status (di luar SLA jobdesk per tugas)."),
    _d("complaint.sla_hours", {"open": 24, "in_progress": 48, "resolved": 0, "closed": 0,
                               "default": 48}, "obj", "sla",
       "SLA tiap status komplain (jam)",
       "Batas wajar komplain menganggur pada satu status sebelum dianggap terlambat."),
    _d("customer.sla_hours", {"draft": 72, "submitted": 48, "verified": 0, "rejected": 0,
                              "default": 336}, "obj", "sla",
       "SLA verifikasi berkas pembeli (jam)",
       "Batas waktu berkas KYC pembeli menganggur pada satu status."),
    _d("ar.sla_hours", {"unpaid": 720, "partial": 720, "paid": 0, "default": 720}, "obj", "sla",
       "SLA tagihan (AR) per status (jam)",
       "Batas wajar tagihan belum lunas sebelum masuk penanganan penagihan."),
    _d("document.sla_hours", {"draft": 72, "finalized": 168, "signed": 0, "default": 168},
       "obj", "sla", "SLA dokumen per status (jam)",
       "Batas wajar dokumen menganggur sebelum difinalkan / ditandatangani."),
    _d("lead.required_demography", [], "list", "lead", "Data demografi wajib",
       "Field demografi yang wajib lengkap sebelum SPR diterbitkan."),
    _d("wa.auto_capture_lead", False, "bool", "lead", "Pesan WA masuk otomatis jadi lead",
       "Bila NYALA, nomor baru yang mengirim pesan WhatsApp langsung dibuatkan lead. Bila MATI, "
       "nomor masuk antrean 'Kontak WA → Lead' untuk diperiksa duplikatnya dulu oleh sales.",
       impact="Menyalakan = lebih cepat tapi berisiko lead sampah/duplikat customer lama.",
       sensitive=True),
    _d("slik.gate", "before_spr", "enum", "lead", "Kapan BI/SLIK checking diwajibkan",
       "BI Checking berjalan di menu terpisah; ini hanya menentukan titik wajibnya.",
       ref_group="slik_gate", sensitive=True),
    _d("slik.scheme_kinds", ["kpr"], "list", "lead", "SLIK wajib untuk jenis skema",
       "Jenis skema pembayaran (cash_keras / cash_bertahap / kpr) yang dikenai gerbang BI/SLIK. "
       "Pembeli tunai tidak mengajukan kredit — bawaan hanya KPR.",
       impact="Menambah 'cash_keras'/'cash_bertahap' membuat SPR tunai tertahan sampai SLIK dicatat.",
       sensitive=True),
    # ============ booking fee ============
    _d("booking_fee.default_amount", 1000000, "money", "booking_fee",
       "Booking fee default (Rp)",
       "Nominal booking fee bawaan; bisa ditimpa per proyek/cluster.", src="DOC"),
    _d("booking_fee.require_paid_before_booking", True, "bool", "booking_fee",
       "Booking fee wajib LUNAS sebelum konfirmasi booking",
       "Bila MENYALA, tombol Konfirmasi Booking ditahan sampai tagihan booking fee (INV-BF) "
       "lunas dan kwitansinya tercatat.",
       impact="Menyalakan berarti sales harus menunggu keuangan mencatat booking fee dulu.",
       src="DOC"),
    _d("booking_fee.due_days", 3, "int", "booking_fee",
       "Batas bayar booking fee (hari setelah reservasi)",
       "Jatuh tempo tagihan INV-BF; tidak melewati masa keep unit (reservation.hold_days).",
       impact="Terlalu pendek = pembeli serius terburu-buru; terlalu panjang = unit dipegang gratis.",
       minimum=1, maximum=30, src="DOC"),
    _d("booking_fee.reminder_days_before", 1, "int", "booking_fee",
       "Pengingat WhatsApp booking fee (H- sebelum jatuh tempo)",
       "Pembeli DAN sales diingatkan bila booking fee belum lunas menjelang jatuh tempo.",
       minimum=0, maximum=14),
    _d("booking_fee.reminder_template", "reminder_booking_fee_due", "string", "booking_fee",
       "Template WhatsApp pengingat booking fee",
       "Kode template `wa_templates` yang sudah disetujui; placeholder {{nama}}, {{unit}}, "
       "{{nominal}}, {{tanggal}}."),
    _d("booking_fee.refund_bi_fail_pct", 100, "pct", "booking_fee",
       "Refund bila BI Checking tidak memenuhi (%)",
       "Persentase pengembalian booking fee bila hasil BI/SLIK tidak sesuai kriteria KPR.",
       sensitive=True, minimum=0, maximum=100, src="DOC"),
    _d("booking_fee.refund_kpr_rejected_pct", 50, "pct", "booking_fee",
       "Refund bila KPR ditolak bank (%)",
       "Persentase pengembalian booking fee bila pengajuan KPR ditolak bank.",
       sensitive=True, minimum=0, maximum=100, src="DOC"),
    _d("booking_fee.forfeit_no_clarity_days", 7, "int", "booking_fee",
       "Hangus bila tidak ada kejelasan (hari)",
       "Hari kalender sejak BI Checking lolos; tanpa kejelasan berkas, booking fee hangus.",
       sensitive=True, minimum=1, maximum=60, src="DOC"),
    # ============ skema pembayaran ============
    _d("payment.cash.dp_pct", 80, "pct", "pembayaran", "DP cash keras (%)",
       "Pembayaran tahap pertama; pembangunan mulai setelah DP diterima.",
       minimum=0, maximum=100, sensitive=True, src="DOC"),
    _d("payment.cash.payoff_days_after_completion", 30, "int", "pembayaran",
       "Batas pelunasan setelah progres 100% (hari)",
       "Hari kalender sejak pemberitahuan penyelesaian pembangunan.", src="DOC"),
    _d("payment.cash.payoff_grace_days", 7, "int", "pembayaran",
       "Perpanjangan pelunasan (hari)", "Toleransi tambahan sebelum transaksi bisa dibatalkan.",
       src="DOC"),
    _d("payment.staged.dp_pct", 80, "pct", "pembayaran", "DP cash bertahap (%)",
       "Pembayaran tahap pertama pada skema cash bertahap.", minimum=0, maximum=100, src="DOC"),
    _d("payment.staged.installment_count", 6, "int", "pembayaran", "Jumlah cicilan pelunasan",
       "Sisa pembayaran dicicil sebanyak ini (bulanan).", minimum=1, maximum=60, src="DOC"),
    _d("payment.staged.due_day", 7, "int", "pembayaran", "Tanggal jatuh tempo cicilan",
       "Tanggal setiap bulan saat cicilan wajib dibayar.", minimum=1, maximum=28, src="DOC"),
    _d("payment.staged.grace_day", 20, "int", "pembayaran", "Batas akhir toleransi (tanggal)",
       "Lewat tanggal ini cicilan dinyatakan menunggak.", minimum=1, maximum=28, src="DOC"),
    _d("payment.staged.arrears_months_to_cancel", 2, "int", "pembayaran",
       "Tunggakan sebelum bisa dibatalkan (bulan)",
       "Berurutan maupun akumulatif; setelah ini developer berhak membatalkan sepihak.",
       sensitive=True, minimum=1, maximum=12, src="DOC"),
    # ============ toleransi keterlambatan & denda (Fase 58) ============
    # Tenggang & tarif denda dulu hidup sebagai angka mati di `finance_reports`
    # (DEFAULT_COLLECTION) — di luar Pusat Konfigurasi, jadi kebijakan penagihan tidak bisa
    # diubah pemilik usaha tanpa deploy. Toleransi yang tertulis pada TERMIN kontrak tetap
    # menang atas angka bawaan di bawah ini.
    _d("payment.late.grace_days", 7, "int", "pembayaran",
       "Toleransi keterlambatan bawaan (hari)",
       "Hari kalender sesudah jatuh tempo sebelum satu termin dinyatakan menunggak.",
       impact="Terlalu panjang = tunggakan tidak pernah terlihat; terlalu pendek = pembeli "
              "dituduh menunggak lebih cepat daripada perjanjiannya.",
       minimum=0, maximum=60, src="DOC"),
    _d("payment.late.rate_pct_month", 2, "pct", "pembayaran", "Tarif denda keterlambatan (%/bulan)",
       "Dihitung dari tunggakan termin, prorata hari sesudah masa toleransi.",
       impact="Denda yang ditagihkan BERJURNAL (piutang & pendapatan denda) — mengubah "
              "tarif mengubah tagihan pembeli.",
       sensitive=True, minimum=0, maximum=10),
    _d("payment.late.max_pct_of_term", 5, "pct", "pembayaran", "Batas denda per termin (%)",
       "Denda satu termin tidak boleh melebihi persentase ini dari tunggakan termin itu.",
       sensitive=True, minimum=0, maximum=100),
    _d("payment.late.min_charge", 50000, "money", "pembayaran", "Denda minimum yang ditagihkan",
       "Denda di bawah nilai ini tidak diterbitkan (biaya administrasinya lebih besar).",
       minimum=0),
    # ============ denda terjadwal (Fase 68) ============
    # Menagih otomatis adalah KEPUTUSAN BISNIS, jadi bawaannya MATI dan remnya bisa
    # disetel: berapa hari lewat toleransi baru otomatis berjalan, dan ambang nominalnya.
    _d("payment.late.auto_apply", False, "bool", "pembayaran",
       "Denda ditagihkan otomatis tiap hari",
       "Bila dinyalakan, penjadwal harian menagihkan denda termin yang lewat toleransi "
       "(berjurnal, idempoten per termin per bulan). Keringanan tetap milik Manajer "
       "Keuangan.",
       impact="Pembeli menerima tagihan denda tanpa staf menekan tombol — nyalakan hanya "
              "bila kebijakan penagihan memang otomatis.",
       sensitive=True),
    _d("payment.late.auto_min_days", 3, "int", "pembayaran",
       "Otomatis menunggu keterlambatan (hari lewat toleransi)",
       "Denda baru ditagihkan OTOMATIS bila keterlambatan melewati toleransi sebanyak "
       "ini; di bawahnya tetap bisa ditagihkan manual.",
       minimum=0, maximum=60),
    _d("payment.late.auto_min_amount", 0, "money", "pembayaran",
       "Ambang nominal denda otomatis",
       "Denda di bawah nilai ini tidak ditagihkan otomatis (0 = hanya ikut denda "
       "minimum biasa).",
       minimum=0),
    _d("payment.kpr.dp_pct", 0, "pct", "pembayaran", "DP KPR default (%)",
       "Uang muka default skema KPR (contoh dokumen: 0%).", minimum=0, maximum=100, src="DOC"),
    # ============ pembatalan & refund ============
    _d("cancellation.cut_before_build_pct", 35, "pct", "pembatalan",
       "Potongan bila batal sebelum pembangunan (%)",
       "Dipotong dari total pembayaran yang sudah diterima.",
       sensitive=True, minimum=0, maximum=100, src="DOC"),
    _d("cancellation.cut_during_build_pct", 50, "pct", "pembatalan",
       "Potongan bila batal saat pembangunan berjalan (%)",
       "Dipotong dari total pembayaran yang sudah diterima.",
       sensitive=True, minimum=0, maximum=100, src="DOC"),
    _d("cancellation.refund_requires_resale", True, "bool", "pembatalan",
       "Refund menunggu unit terjual kembali",
       "Pengembalian dana dilakukan setelah unit dibatalkan terjual ke pihak lain.",
       sensitive=True, src="DOC"),
    # Fase 59: utang refund yang sudah lahir di buku besar (2-1460) TIDAK punya tanggal
    # sampai fase ini — kewajiban tanpa tanggal tidak bisa dipakai merencanakan kas. Ambang
    # ini yang mengubahnya menjadi jatuh tempo yang bisa dilaporkan & diproyeksikan.
    _d("cancellation.refund_due_days", 30, "int", "pembatalan",
       "Batas pembayaran refund setelah keputusan (hari)",
       "Hari kalender sejak keputusan pembatalan disetujui. Refund yang tertahan ketentuan "
       "SPR (menunggu unit terjual kembali) sengaja tidak diberi tanggal.",
       sensitive=True, minimum=1, maximum=365, src="CFG"),
    # ============ legal ============
    _d("legal.shgb_months_after_ajb", 6, "int", "legal", "Sertifikat (SHGB) diserahkan (bulan)",
       "Perkiraan waktu penyerahan sertifikat sejak AJB/PPJB notaris.", src="DOC"),
    _d("retention.months", 3, "int", "legal", "Masa retensi bangunan (bulan)",
       "Masa retensi/garansi bangunan setelah akad atau AJB.", minimum=0, maximum=36),
    # ============ KPR ============
    _d("kpr.use_appraisal_step", True, "bool", "kpr", "Pakai tahap survei & appraisal bank",
       "Bila dimatikan, alur KPR langsung dari pengajuan ke SP3K."),
    _d("kpr.sla_days", {"berkas_lengkap": 7, "diajukan_ke_bank": 14, "appraisal": 7,
                        "sp3k": 14, "akad_kredit": 7}, "obj", "kpr",
       "SLA tiap tahap KPR (hari)", "Batas waktu tiap tahap sebelum dianggap tersangkut."),
    # ============ add-on / spek tambahan ============
    _d("addon.require_spkt_for_excess_land", True, "bool", "addon",
       "Kelebihan tanah wajib SPKT",
       "Add-on kelebihan tanah tidak sah tanpa Surat Pernyataan Kelebihan Tanah.",
       sensitive=True, src="DOC"),
    _d("addon.spkt_scheme_kinds", ["cash_keras", "cash_bertahap", "kpr"], "list", "addon",
       "SPKT wajib untuk jenis skema",
       "Jenis skema pembayaran yang dikenai gerbang SPKT (KPR: sebelum akad kredit; tunai: sebelum AJB).",
       sensitive=True),
    _d("addon.excess_land_must_be_paid_before_akad", True, "bool", "addon",
       "Kelebihan tanah lunas sebelum akad",
       "Akad kredit/AJB diblokir bila biaya kelebihan tanah belum lunas.",
       sensitive=True, src="DOC"),
    _d("addon.due_days", 30, "int", "addon",
       "Jatuh tempo tagihan add-on (hari)",
       "Add-on ditagih TERPISAH dari termin unit (bukan dasar KPR); jatuh tempo dihitung dari tanggal booking.",
       src="DOC"),
    _d("addon.excess_land_price_per_m2", 2000000, "money", "addon",
       "Harga list kelebihan tanah (Rp/m²)",
       "Dipakai bila master add-on kelebihan tanah belum punya harga; tercetak sebagai harga daftar di SPKT.",
       src="DOC"),
    # ============ mitra ============
    _d("partner.enabled", True, "bool", "mitra", "Aktifkan modul mitra",
       "Mematikan ini menyembunyikan menu mitra dan menolak lead bersumber mitra."),
    _d("partner.require_contract_active", True, "bool", "mitra", "Kontrak mitra wajib aktif",
       "Lead & fee ditolak bila kontrak mitra kedaluwarsa.", sensitive=True),
    _d("partner.attribution_model", "first_touch", "enum", "mitra", "Model atribusi lead mitra",
       "Menentukan mitra mana yang berhak atas lead yang dikirim lebih dari satu mitra.",
       ref_group="attribution_model", sensitive=True),
    _d("partner.lead_dedup_window_days", 30, "int", "mitra", "Jendela dedup lead mitra (hari)",
       "Lead sama dalam rentang ini dianggap milik mitra pertama.", minimum=1, maximum=365),
    _d("partner.auto_create_fee", True, "bool", "mitra", "Buat tagihan fee otomatis",
       "Fee dibuat otomatis saat pemicu tercapai (status menunggu persetujuan)."),
    _d("partner.fee_needs_approval", True, "bool", "mitra", "Fee wajib disetujui finance",
       "Tanpa persetujuan, fee tidak menjadi utang dan tidak dijurnal.", sensitive=True),
    _d("partner.max_fee_pct_of_price", 5, "pct", "mitra", "Pagar wajar fee (% harga)",
       "Fee di atas ambang ini butuh persetujuan owner.", minimum=0, maximum=100),
    _d("partner.tax_pph21_rate", 2.5, "pct", "mitra", "Tarif PPh 21 mitra perorangan (%)",
       "Default umum; WAJIB dikonfirmasi bagian pajak perusahaan.",
       sensitive=True, minimum=0, maximum=50),
    _d("partner.tax_pph23_rate", 2, "pct", "mitra", "Tarif PPh 23 mitra badan (%)",
       "Default umum; WAJIB dikonfirmasi bagian pajak perusahaan.",
       sensitive=True, minimum=0, maximum=50),
    # ============ dokumen ============
    _d("docnum.scope", "per_project", "enum", "dokumen", "Cakupan nomor dokumen",
       "Counter nomor dokumen dihitung global, per proyek, atau per proyek per bulan.",
       ref_group="docnum_scope", sensitive=True),
    _d("docnum.reset_policy", "yearly", "enum", "dokumen", "Reset nomor dokumen",
       "Kapan counter nomor dokumen dimulai dari 1 lagi.",
       ref_group="docnum_reset_policy", sensitive=True),
    _d("docnum.width", 4, "int", "dokumen", "Lebar digit nomor",
       "Contoh lebar 4 = 0001; dokumen contoh owner memakai 4 digit (5201).",
       minimum=1, maximum=8),
    _d("doc.require_verification_default", True, "bool", "dokumen",
       "Dokumen baru wajib diverifikasi",
       "Dokumen yang diunggah berstatus menunggu verifikasi sebelum dianggap sah."),
    # ============ anggaran & target ============
    # Fase 45: bawaannya MATI (sengaja, keputusan pemilik saat fase ini dikerjakan).
    # Alasannya jujur: dokumen biaya yang sudah ada dibuat SEBELUM master anggaran ada, jadi
    # menyalakan kewajiban ini sejak hari pertama akan menolak pekerjaan orang tanpa mereka
    # punya kesempatan merapikan data. Urutan yang dipakai: susun item anggaran → rapikan
    # daftar "biaya belum terpetakan" (`GET /api/budget/unmapped`) → baru nyalakan ini.
    _d("budget.enforce_cost_ref", False, "bool", "anggaran",
       "Dokumen biaya wajib memilih item anggaran",
       "Bila MATI: dokumen biaya baru boleh tanpa item anggaran, tetapi muncul di laporan "
       "'biaya belum terpetakan'. Bila MENYALA: PO/tagihan/kas bon/jurnal baru DITOLAK tanpa "
       "item anggaran, sehingga realisasi RAB & overbudget tidak perlu menebak.",
       impact="Menyalakan ini menambah satu field wajib pada semua form biaya baru. "
              "Rapikan dulu laporan 'biaya belum terpetakan'.",
       sensitive=True),
    _d("budget.alert_pct", 90, "pct", "anggaran", "Ambang peringatan anggaran (%)",
       "Saat realisasi+komitmen mencapai ambang ini, peringatan dikirim.",
       minimum=50, maximum=100),
    _d("target.default_method", "linear_remaining", "enum", "anggaran", "Metode target default",
       "Metode perhitungan target bulanan untuk proyek baru.",
       ref_group="target_method"),
    # ============ konstruksi & izin ============
    _d("survey.checklist_items",
       ["Akses jalan menuju lokasi", "Kondisi tanah & kontur", "Batas kavling & patok jelas",
        "Ketersediaan listrik", "Ketersediaan air / PDAM", "Saluran drainase",
        "Lingkungan & keamanan sekitar"],
       "list", "lead", "Checklist survey LAMA (digantikan Tahapan Survey)",
       "Tidak dibaca lagi oleh survey baru: poin pemeriksaan kini diatur per tahap di tab "
       "Tahapan Survey. Nilai ini hanya dipakai sekali untuk memindahkan checklist lama.",
       impact="Mengubah daftar hanya berlaku untuk survey berikutnya — survey berjalan "
              "tidak berubah."),
    _d("permit.block_build_without", [], "list", "konstruksi",
       "Izin yang memblokir mulai bangun",
       "Kosong = hanya peringatan. Isi kode izin (mis. PBG) untuk memblokir. Izin dicari "
       "berjenjang: unit → blok → cluster → proyek; izin yang sudah kedaluwarsa tidak "
       "dihitung sebagai ada.",
       impact="Menyalakan ini bisa menghentikan pekerjaan yang sudah berjalan di lapangan. "
              "Rapikan dulu daftar izin per objek di tab Dokumen & Izin."),
    _d("permit.types_custom", [], "list", "konstruksi",
       "Jenis izin tambahan",
       "Jenis perizinan di luar bawaan sistem (KRK/IMB/PBG/SLF/AMDAL/dst) yang boleh "
       "dipilih saat menambah izin. Menghapus jenis dari daftar ini TIDAK mengubah izin "
       "yang sudah tercatat memakai jenis tersebut."),
    _d("build.require_dp_before_start", False, "bool", "konstruksi",
       "Mulai bangun butuh DP terbayar",
       "Sesuai SPR: pembangunan dimulai setelah pembayaran tahap pertama diterima. "
       "Bawaan MATI (Fase 46) = sistem hanya MEMPERINGATKAN dan memaksa pelaksana "
       "mengakui peringatan + menulis alasan yang tercatat. Bila MENYALA, tombol "
       "'Mulai bangun' benar-benar DITOLAK sampai termin pertama terbayar.",
       impact="Menyalakan ini menghentikan mulai bangun untuk unit yang termin "
              "pertamanya belum terbayar atau belum punya rencana bayar.",
       sensitive=True, src="DOC"),
    # ============ Fase 84 — kas kecil imprest ============
    _d("petty_cash.imprest_limit", 5_000_000, "money", "kas_kecil",
       "Batas dana tetap kas kecil (imprest) bawaan",
       "Jumlah dana yang seharusnya ada di tiap kas kecil saat penuh. Pengisian selalu mengembalikan "
       "saldo ke angka ini. Bisa ditimpa per kas di Master Rekening & Kas.",
       impact="Menaikkan batas berarti lebih banyak uang tunai menganggur di brankas.",
       minimum=0, maximum=1_000_000_000),
    _d("petty_cash.replenish_threshold_pct", 30, "pct", "kas_kecil",
       "Ambang pengisian ulang (% dari batas)",
       "Bila saldo kas kecil turun di bawah persen ini, sistem mengusulkan pengisian kembali "
       "sebesar batas − saldo.", minimum=0, maximum=90),
    _d("petty_cash.max_expense", 1_000_000, "money", "kas_kecil",
       "Batas satu pengeluaran kas kecil",
       "Pengeluaran tunai di atas angka ini harus lewat kas bon atau tagihan vendor (AP), bukan "
       "kas kecil.", impact="Menaikkan batas memperbesar uang keluar tanpa persetujuan berjenjang.",
       sensitive=True, minimum=0, maximum=100_000_000),
    _d("petty_cash.require_proof", True, "bool", "kas_kecil",
       "Bukti wajib untuk setiap pengeluaran",
       "Nota/kuitansi harus dilampirkan sebelum pengeluaran kas kecil dapat dicatat.",
       impact="Mematikan ini membuat kas kecil bisa keluar tanpa bukti — audit lemah.",
       sensitive=True),
    # ============ Fase 47A — rekonsiliasi bank ============
    _d("bank.match_amount_tolerance", 0, "money", "bank",
       "Toleransi selisih nominal saat mencocokkan",
       "Selisih rupiah yang masih dianggap 'nominal sama' saat sistem MENGUSULKAN kandidat "
       "(mis. biaya transfer Rp 6.500 yang dipotong bank). Bawaan 0 = harus sama persis. "
       "Toleransi hanya memengaruhi USULAN; keputusan tetap milik manusia.",
       impact="Menaikkan nilai ini membuat usulan lebih longgar — risiko salah cocok naik.",
       minimum=0, maximum=1000000),
    _d("bank.match_date_window_days", 7, "int", "bank",
       "Jendela tanggal pencarian kandidat (hari)",
       "Seberapa jauh sistem mencari dokumen di sekitar tanggal mutasi saat mengusulkan "
       "pencocokan.", minimum=1, maximum=90),
    # ============ Fase 47C — penawaran & diskon ============
    _d("quotation.discount_max_pct_sales", 2, "pct", "penawaran",
       "Batas diskon tanpa persetujuan manajer (%)",
       "Diskon sampai persen ini boleh diberikan sales sendiri; di atasnya penawaran WAJIB "
       "disetujui manajer sales/direksi beserta alasannya.",
       impact="Menaikkan batas ini memperbesar wewenang diskon sales tanpa persetujuan.",
       minimum=0, maximum=100, src="DOC"),
    _d("quotation.validity_days", 7, "int", "penawaran", "Masa berlaku penawaran (hari)",
       "Setelah lewat, penawaran otomatis dinyatakan kedaluwarsa dan harus direvisi — harga "
       "lama tidak boleh dipakai diam-diam.", minimum=1, maximum=90),
    # ============ Fase 69 — mesin harga: promo & kupon ============
    _d("pricing.allow_stack_promo_coupon", True, "bool", "penawaran",
       "Promo dan kupon boleh digabung",
       "Bila MATI, satu transaksi hanya boleh memakai promo ATAU kupon, tidak keduanya. "
       "Skema diskon selalu boleh dipadukan dengan salah satunya.",
       impact="Menyalakan berarti potongan bisa menumpuk (promo + kupon + skema diskon)."),
    # ============ Fase 47D — upah harian ============
    _d("labor.overtime_multiplier", 1.5, "pct", "upah", "Pengali upah lembur",
       "Tarif lembur = (upah harian ÷ jam kerja normal) × pengali ini.",
       minimum=1, maximum=5, src="DOC"),
    _d("labor.normal_hours_per_day", 8, "int", "upah", "Jam kerja normal per hari",
       "Dipakai menghitung tarif per jam untuk lembur.", minimum=4, maximum=12),
    # ============ tampilan ============
    _d("ui.table_page_size", 25, "int", "tampilan", "Baris per halaman tabel",
       "Jumlah baris default pada semua tabel daftar.", minimum=10, maximum=200),
    # ============ pajak & kepatuhan (Fase 49) ============
    # Tanpa identitas ini, berkas ekspor e-Faktur/e-Bupot TIDAK BISA dibuat — dan itu
    # memang ditahan dengan pesan jelas, bukan diekspor dengan kolom kosong.
    _d("tax.company_npwp", "", "text", "pajak", "NPWP perusahaan (16 digit)",
       "Dipakai sebagai identitas penjual/pemotong pada berkas ekspor e-Faktur & e-Bupot.",
       impact="Kosong = ekspor pajak ditahan; salah = berkas ditolak Coretax.", sensitive=True),
    _d("tax.company_idtku", "", "text", "pajak", "NITKU / ID TKU perusahaan",
       "Identitas tempat kegiatan usaha pada skema Coretax (boleh sama dengan NPWP + 000000).",
       impact="Kosong = kolom ID TKU pada berkas ekspor dibiarkan kosong."),
    _d("tax.pph23_rate", 2, "pct", "pajak", "Tarif PPh 23 jasa (%)",
       "Tarif bawaan saat memotong PPh 23 atas pembayaran jasa vendor.", minimum=0, maximum=100),
    _d("tax.pph4_2_konstruksi_rate", 1.75, "pct", "pajak",
       "Tarif PPh 4(2) jasa konstruksi (%)",
       "Tarif bawaan potongan final jasa konstruksi (kualifikasi kecil 1,75%; tanpa "
       "kualifikasi 4%). Selalu bisa diubah per pembayaran.", minimum=0, maximum=100),
    _d("tax.pph4_2_sewa_rate", 10, "pct", "pajak", "Tarif PPh 4(2) sewa tanah & bangunan (%)",
       "Tarif bawaan potongan final atas sewa tanah/bangunan. Selalu bisa diubah per "
       "pemotongan bila kondisinya berbeda.", minimum=0, maximum=100),
    _d("tax.bupot_series", "01", "text", "pajak", "Kode seri bukti potong (2 digit)",
       "Dua digit kode seri pada nomor bukti potong 10 digit (PER-24/PJ/2021)."),
    # ============ Fase 50A: serah terima & garansi ============
    # Kenapa per BAGIAN, bukan satu angka: `retention.months` lama menyebut "masa retensi /
    # garansi bangunan" sebagai SATU nilai untuk semua pekerjaan, padahal struktur bertahun
    # dan finishing berbulan. Pertanyaan pembeli "ini masih garansi?" hanya bisa dijawab
    # dengan dasar kalau masanya dipisah per bagian pekerjaan.
    _d("warranty.struktur_months", 120, "int", "garansi", "Garansi struktur (bulan)",
       "Pondasi, sloof, kolom, balok, dan rangka utama.",
       impact="Memperpendek masa ini menutup hak pembeli atas cacat struktur.",
       sensitive=True, minimum=0, maximum=240, src="DOC"),
    _d("warranty.atap_plafon_months", 12, "int", "garansi", "Garansi atap & plafon (bulan)",
       "Kebocoran atap, rangka atap, dan plafon.", minimum=0, maximum=120, src="DOC"),
    _d("warranty.dinding_lantai_months", 12, "int", "garansi",
       "Garansi dinding & lantai (bulan)",
       "Retak rambut, keramik pecah/popping, dan nat lantai.", minimum=0, maximum=120,
       src="DOC"),
    _d("warranty.plumbing_months", 6, "int", "garansi", "Garansi sanitasi & plumbing (bulan)",
       "Instalasi air bersih, air kotor, dan perlengkapan sanitasi.", minimum=0, maximum=120,
       src="DOC"),
    _d("warranty.listrik_months", 6, "int", "garansi", "Garansi instalasi listrik (bulan)",
       "Titik lampu, saklar, MCB, dan pengabelan.", minimum=0, maximum=120, src="DOC"),
    _d("warranty.kusen_months", 6, "int", "garansi", "Garansi kusen, pintu & jendela (bulan)",
       "Kusen, daun pintu/jendela, kunci, dan engsel.", minimum=0, maximum=120, src="DOC"),
    _d("warranty.finishing_months", 3, "int", "garansi", "Garansi finishing (bulan)",
       "Pengecatan, nat, dan aksesori.", minimum=0, maximum=60, src="DOC"),
    _d("warranty.expiring_days", 30, "int", "garansi", "Ambang \u201champir habis\u201d (hari)",
       "Sisa hari saat masa garansi mulai ditandai hampir habis di layar & portal pembeli.",
       minimum=1, maximum=180),
    _d("warranty.claim_sla_days", 7, "int", "garansi", "SLA menjawab klaim garansi (hari)",
       "Batas waktu tim proyek memutuskan diterima atau ditolak.", minimum=1, maximum=60),
    _d("warranty.fix_days", 7, "int", "garansi", "Target selesai perbaikan garansi (hari)",
       "Tenggat bawaan pekerjaan perbaikan yang lahir dari klaim yang diterima.",
       minimum=1, maximum=90),
    # ============ Fase 51B: pengingat WhatsApp otomatis ============
    # Semua tanggalnya sudah dimiliki sistem (jatuh tempo termin, tunggakan, habis garansi)
    # tetapi tidak pernah memberi tahu pembelinya. Ambang batas ditaruh di sini supaya bisa
    # disetel per organisasi tanpa menyentuh kode \u2014 dan supaya bisa DIBUKTIKAN gate bahwa
    # angkanya benar-benar dibaca dari sini.
    _d("reminder.enabled", True, "bool", "pengingat", "Pengingat WhatsApp otomatis",
       "Bila dimatikan, kandidat tetap dihitung & ditampilkan tetapi tidak ada yang dikirim.",
       impact="Mematikan ini membuat pembeli tidak lagi diingatkan sama sekali."),
    _d("reminder.warranty_days", 30, "int", "pengingat",
       "Ingatkan garansi hampir habis (hari sebelum)",
       "Sisa hari saat pembeli mulai diingatkan bahwa garansi satu bagian akan berakhir.",
       minimum=1, maximum=180),
    _d("reminder.installment_days_before", 3, "int", "pengingat",
       "Ingatkan termin jatuh tempo (hari sebelum)",
       "Pengingat dikirim ketika sisa hari menuju jatuh tempo \u2264 angka ini.",
       minimum=0, maximum=60),
    _d("reminder.overdue_every_days", 7, "int", "pengingat",
       "Ulang pengingat tunggakan setiap (hari)",
       "Tunggakan diingatkan berulang, tetapi hanya sekali per rentang ini \u2014 bukan tiap hari.",
       minimum=1, maximum=90),
    _d("reminder.template_warranty", "reminder_warranty_expiring", "string", "pengingat",
       "Template WA \u2014 garansi hampir habis",
       "Kode template WhatsApp yang dipakai. Template harus berstatus disetujui.",
       impact="Template yang tidak ada membuat pengingat DILEWATI dengan sebab, bukan "
              "mengirim kalimat karangan."),
    _d("reminder.template_installment", "reminder_installment_due", "string", "pengingat",
       "Template WA \u2014 termin jatuh tempo",
       "Kode template WhatsApp untuk pengingat termin yang akan jatuh tempo."),
    _d("reminder.template_overdue", "reminder_installment_overdue", "string", "pengingat",
       "Template WA \u2014 tunggakan",
       "Kode template WhatsApp untuk tagihan yang sudah lewat jatuh tempo."),
    # ============ pengingat tunggakan pra-SP (Fase 68) ============
    # Sebelum ini pembeli baru tahu ada masalah saat SP1 datang. Pengingat pra-SP lahir
    # begitu tunggakan MELEWATI TOLERANSI kontrak; nominal & aturannya bisa disetel.
    _d("reminder.arrears_enabled", True, "bool", "pengingat",
       "Pengingat tunggakan lewat toleransi (pra-SP)",
       "Pesan WhatsApp disiapkan otomatis begitu tunggakan pembeli melewati toleransi "
       "kontrak \u2014 sebelum Surat Peringatan terbit.",
       impact="Dimatikan = pembeli baru tahu saat SP1 datang."),
    _d("reminder.arrears_min_amount", 0, "money", "pengingat",
       "Nominal tunggakan minimum yang diingatkan",
       "Tunggakan di bawah nilai ini tidak menghasilkan pengingat pra-SP (0 = semua "
       "tunggakan diingatkan).",
       minimum=0),
    _d("reminder.arrears_min_months", 1, "int", "pengingat",
       "Bulan tunggakan minimum (lewat toleransi)",
       "Pengingat pra-SP lahir setelah tunggakan mencapai sekian bulan menurut hitungan "
       "SPR (akumulatif maupun berurutan).",
       minimum=1, maximum=12),
    _d("reminder.arrears_every_days", 7, "int", "pengingat",
       "Ulang pengingat pra-SP setiap (hari)",
       "Satu pengingat per rentang ini per transaksi \u2014 bukan tiap hari.",
       minimum=1, maximum=90),
    _d("reminder.template_arrears", "reminder_arrears_warning", "string", "pengingat",
       "Template WA \u2014 tunggakan lewat toleransi (pra-SP)",
       "Kode template WhatsApp untuk pengingat tunggakan yang melewati toleransi "
       "kontrak."),
]}

from settings_p88 import DEFAULTS_P88  # noqa: E402
DEFAULTS.update(DEFAULTS_P88)

GROUP_LABELS = {
    "reservasi": "Reservasi & Keep Unit", "lead": "Lead & Lifecycle",
    "sla": "SLA & Umur Tahap (Aging)",
    "booking_fee": "Booking Fee", "pembayaran": "Skema Pembayaran",
    "pembatalan": "Pembatalan & Refund", "legal": "Legal & Retensi", "kpr": "KPR",
    "addon": "Spek Tambahan (Add-on)", "mitra": "Mitra / Pihak Ketiga",
    "dokumen": "Dokumen & Penomoran", "anggaran": "Anggaran & Target",
    "konstruksi": "Konstruksi & Izin", "bank": "Rekonsiliasi Bank",
    "kas_kecil": "Kas Kecil (Imprest)",
    "penawaran": "Penawaran & Diskon", "upah": "Upah Harian Tenaga Kerja",
    "pajak": "Pajak & Kepatuhan",
    "garansi": "Serah Terima & Garansi",
    "pengingat": "Pengingat Otomatis (WhatsApp)",
    "whatsapp": "WhatsApp — Jam Kirim, Batas Laju & Biaya",
    "tampilan": "Tampilan",
}


# ---------------------------------------------------------------- validasi nilai
def coerce(spec: dict, value):
    """Ubah & validasi nilai sesuai tipe setting. Melempar ValueError bila tidak sah."""
    t = spec["type"]
    if t in ("int", "money"):
        try:
            value = int(float(value))
        except (TypeError, ValueError):
            raise ValueError(f"{spec['label']}: harus berupa angka bulat.")
    elif t == "pct":
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{spec['label']}: harus berupa angka persen.")
    elif t == "bool":
        if isinstance(value, str):
            value = value.strip().lower() in ("1", "true", "ya", "on")
        value = bool(value)
    elif t == "enum":
        value = str(value)
        if spec.get("options") and value not in spec["options"]:
            raise ValueError(f"{spec['label']}: pilihan tidak valid "
                             f"({', '.join(spec['options'])}).")
    elif t == "list":
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        if not isinstance(value, list):
            raise ValueError(f"{spec['label']}: harus berupa daftar.")
    elif t == "obj":
        if not isinstance(value, dict):
            raise ValueError(f"{spec['label']}: harus berupa objek.")
    else:
        value = str(value)
    if spec.get("min") is not None and isinstance(value, (int, float)) and value < spec["min"]:
        raise ValueError(f"{spec['label']}: minimum {spec['min']}.")
    if spec.get("max") is not None and isinstance(value, (int, float)) and value > spec["max"]:
        raise ValueError(f"{spec['label']}: maksimum {spec['max']}.")
    return value


# ---------------------------------------------------------------- pembacaan
async def _rows(org_id: str) -> dict:
    """Semua override tersimpan, dikelompokkan per key (dengan cache pendek)."""
    now = time.time()
    if now - _CACHE["at"] < _TTL and org_id in _CACHE["rows"]:
        return _CACHE["rows"][org_id]
    out: dict = {}
    async for row in db.settings.find({"org_id": org_id}, {"_id": 0}):
        out.setdefault(row["key"], []).append(row)
    _CACHE["rows"][org_id] = out
    _CACHE["at"] = now
    return out


def invalidate():
    _CACHE["at"] = 0.0
    _CACHE["rows"] = {}


async def get(key: str, *, org_id: str = ORG_ID, project_id: str = None,
              cluster_id: str = None):
    """Nilai efektif: cluster → project → org → default kode."""
    spec = DEFAULTS.get(key)
    if not spec:
        raise KeyError(f"Setting tidak dikenal: {key}")
    rows = (await _rows(org_id)).get(key) or []
    by = {(r.get("scope"), r.get("scope_id")): r.get("value") for r in rows}
    for scope, sid in (("cluster", cluster_id), ("project", project_id), ("org", org_id)):
        if sid and (scope, sid) in by:
            return by[(scope, sid)]
    return spec["value"]


async def get_many(keys, *, org_id: str = ORG_ID, project_id: str = None,
                   cluster_id: str = None) -> dict:
    return {k: await get(k, org_id=org_id, project_id=project_id, cluster_id=cluster_id)
            for k in keys}


async def get_group(group: str, *, org_id: str = ORG_ID, project_id: str = None) -> dict:
    keys = [k for k, s in DEFAULTS.items() if s["group"] == group]
    return await get_many(keys, org_id=org_id, project_id=project_id)


async def listing(*, org_id: str = ORG_ID, group: str = None, project_id: str = None,
                  q: str = None) -> list:
    """Daftar setting untuk UI: spec + nilai efektif + asal nilai + jejak terakhir."""
    rows = await _rows(org_id)
    out = []
    for key, spec in DEFAULTS.items():
        if group and spec["group"] != group:
            continue
        if q and q.lower() not in (key + " " + spec["label"] + " " + spec["help"]).lower():
            continue
        stored = rows.get(key) or []
        by = {(r.get("scope"), r.get("scope_id")): r for r in stored}
        row = None
        origin = "default"
        if project_id and ("project", project_id) in by:
            row, origin = by[("project", project_id)], "project"
        elif ("org", org_id) in by:
            row, origin = by[("org", org_id)], "org"
        item = dict(spec)
        if spec.get("ref_group"):
            import reference as _ref
            item["option_labels"] = _ref.labels(spec["ref_group"])
        item["group_label"] = GROUP_LABELS.get(spec["group"], spec["group"])
        item["default_value"] = spec["value"]
        item["value"] = row["value"] if row else spec["value"]
        item["origin"] = origin
        item["updated_by"] = (row or {}).get("updated_by")
        item["updated_at"] = (row or {}).get("updated_at")
        item["history_count"] = len((row or {}).get("history") or [])
        item["overrides"] = [{"scope": r.get("scope"), "scope_id": r.get("scope_id"),
                             "value": r.get("value")} for r in stored]
        out.append(item)
    out.sort(key=lambda x: (x["group"], x["key"]))
    return out


# ---------------------------------------------------------------- penulisan
async def set_value(key: str, value, *, actor: str, reason: str = None,
                    org_id: str = ORG_ID, scope: str = "org", scope_id: str = None) -> dict:
    spec = DEFAULTS.get(key)
    if not spec:
        raise ValueError(f"Setting tidak dikenal: {key}")
    if scope not in SCOPES:
        raise ValueError(f"Scope tidak valid: {scope}")
    scope_id = scope_id or (org_id if scope == "org" else None)
    if not scope_id:
        raise ValueError("scope_id wajib untuk scope project/cluster.")
    if spec.get("sensitive") and not (reason or "").strip():
        raise ValueError(f"'{spec['label']}' adalah setting sensitif — alasan wajib diisi.")
    value = coerce(spec, value)
    ts = now_iso()
    existing = await db.settings.find_one(
        {"org_id": org_id, "key": key, "scope": scope, "scope_id": scope_id}, {"_id": 0})
    entry = {"at": ts, "by": actor, "from": (existing or {}).get("value", spec["value"]),
             "to": value, "reason": (reason or "").strip() or None}
    if existing:
        await db.settings.update_one(
            {"org_id": org_id, "key": key, "scope": scope, "scope_id": scope_id},
            {"$set": {"value": value, "updated_by": actor, "updated_at": ts},
             "$push": {"history": {"$each": [entry], "$slice": -50}}})
    else:
        await db.settings.insert_one({
            "id": new_id(), "org_id": org_id, "key": key, "scope": scope, "scope_id": scope_id,
            "value": value, "type": spec["type"], "group": spec["group"],
            "updated_by": actor, "updated_at": ts, "created_at": ts, "history": [entry]})
    invalidate()
    logger.info("Setting %s (%s:%s) = %s oleh %s", key, scope, scope_id, value, actor)
    return {"key": key, "value": value, "scope": scope, "scope_id": scope_id, "entry": entry}


async def reset(key: str, *, actor: str, org_id: str = ORG_ID, scope: str = "org",
                scope_id: str = None) -> dict:
    spec = DEFAULTS.get(key)
    if not spec:
        raise ValueError(f"Setting tidak dikenal: {key}")
    scope_id = scope_id or (org_id if scope == "org" else None)
    res = await db.settings.delete_one(
        {"org_id": org_id, "key": key, "scope": scope, "scope_id": scope_id})
    invalidate()
    return {"key": key, "removed": res.deleted_count, "value": spec["value"]}


async def history(key: str, *, org_id: str = ORG_ID) -> list:
    rows = await db.settings.find({"org_id": org_id, "key": key}, {"_id": 0}).to_list(20)
    out = []
    for r in rows:
        for h in (r.get("history") or []):
            out.append({**h, "scope": r.get("scope"), "scope_id": r.get("scope_id")})
    out.sort(key=lambda x: x.get("at") or "", reverse=True)
    return out


async def groups_summary(*, org_id: str = ORG_ID) -> list:
    rows = await _rows(org_id)
    counts = {}
    for key, spec in DEFAULTS.items():
        g = counts.setdefault(spec["group"], {"group": spec["group"],
                                              "label": GROUP_LABELS.get(spec["group"], spec["group"]),
                                              "total": 0, "overridden": 0})
        g["total"] += 1
        if rows.get(key):
            g["overridden"] += 1
    return sorted(counts.values(), key=lambda x: x["label"])
