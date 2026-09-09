#!/usr/bin/env bash
# run_all_gates.sh — jalankan SEMUA guardrail SIPRO, tampilkan ringkasan.
# Exit !=0 bila ada gate GAGAL. Usage: bash scripts/run_all_gates.sh
cd "$(dirname "$0")/.."

GATES=(
  validate_compliance.py
  health_check.py
  verify_rbac.py
  verify_api_contract.py
  check_nav_map.py
  audit_endpoint_sweep.py
  verify_data_integrity.py
  ux_audit.py
  forensic_audit.py
  audit_forms_deep.py
  verify_business_invariants.py
  verify_ui_surfaces.py
  verify_31.py
  verify_32.py
  verify_33.py
  verify_34.py
  verify_35.py
  verify_36.py
  verify_37.py
  verify_settings.py
  verify_masterplan.py
  verify_39b.py
  verify_ia_v2.py
  verify_41.py
  verify_partner.py
  verify_rbac_ui.py
  verify_ads.py
  verify_analytics.py
  verify_budget_target.py
  verify_build_hub.py
  verify_bank_recon.py
  verify_portal_proof.py
  verify_quotation_labor.py
  verify_procurement_vendor.py
  verify_field_names.py
  verify_audit_fixes.py
  verify_subcon_retention.py
  verify_stock_control.py
  verify_closing.py
  verify_tax_compliance.py
  verify_handover_warranty.py
  verify_offline_queue.py
  verify_retention_warranty.py
  verify_wa_reminders.py
  verify_portal_warranty.py
  # Fase 52 — gate ke-44: satu panel yang ditolak tidak boleh mematikan halaman, dan layar
  # tidak boleh berbohong tentang sebabnya (403 ≠ "belum ada data"), termasuk peta menu yang
  # tidak boleh mengaku menu HIDUP itu terkunci.
  verify_panel_resilience.py
  # Fase 54 — gate ke-45: sesi tidak boleh mati mendadak (ada /auth/refresh, cookie basi
  # tidak mengalahkan Bearer yang sah, sebab 401 bisa dibedakan mesin), perpanjangan bukan
  # pintu belakang bagi akun/penyewa yang dicabut dan tidak memindahkan penyewa diam-diam,
  # dan bila sesi memang berakhir ia berakhir JUJUR (React diberi tahu + tempat kerja
  # dipulihkan) tanpa membocorkan istilah internal ke layar.
  verify_session_resilience.py
  # Fase 53 — gate ke-46 (utang yang dibayar di Fase 54): rantai LEAD -> PEMBELI -> KONTRAK ->
  # AKAD -> DOKUMEN OWNER TERCETAK. Sebelum ini seluruh rantai hanya dijaga `poc/poc_53.py`
  # yang TIDAK terdaftar di sini, jadi siapa pun bisa merusaknya dan rangkaian gate tetap
  # hijau. Termasuk penjaga statis yang POC tidak bisa lakukan (label dari Kamus Data, testId
  # tidak mati, field Bank wajib dropdown).
  verify_contract_legal_docgen.py
  # Fase 56C — gate ke-47: janji pasal pembatalan SPR (potongan 35%/50%, refund menyusul
  # penjualan ulang) harus tetap BISA DIJALANKAN dan berjurnal: pengaju ≠ pemutus ≠ pembayar,
  # jurnal berimbang, unit kembali ke stok secara atomik, refund idempoten & tidak bisa
  # melebihi sisa, dan pembeli membaca angka yang SAMA dengan pembukuan di portal — tanpa
  # nomor akun bocor ke matanya. Dibuktikan bergigi oleh `scripts/mutasi_56.py`.
  verify_cancellation_refund.py
  # Fase 57A — gate ke-48: termin pembayaran WAJIB tetap bisa dikonfigurasi pemakai (DP
  # nominal/persen, jumlah cicilan, tanggal jatuh tempo, toleransi, termin berbasis
  # peristiwa, berlaku di proyek mana) dengan SATU mesin termin yang sama dengan penagihan —
  # dan skema yang tidak menagih seluruh harga jual ditolak, bukan disimpan diam-diam.
  # Dibuktikan bergigi oleh `scripts/mutasi_57.py` (28 mutan, 28 TERTANGKAP).
  verify_payment_schemes.py
  # Fase 58 — gate ke-49: TOLERANSI keterlambatan yang dijanjikan kontrak (dan tercetak pada
  # SPR) wajib dipakai penagihan — "lewat tanggal" bukan berarti "menunggak" selama masih di
  # dalam tenggang — dan denda keterlambatan wajib BERJURNAL, tidak dobel, serta hanya bisa
  # diringankan Manajer Keuangan dengan alasan tertulis yang tidak bisa dianulir bawahannya.
  # Dibuktikan bergigi oleh `scripts/mutasi_58.py` (31 mutan).
  verify_late_fee.py
  # Fase 59 — gate ke-50: jejak keringanan denda bisa dipertanggungjawabkan di rapat
  # direksi, tunggakan yang melewati batas SPR MENGUSULKAN (bukan membatalkan sendiri),
  # dan utang refund 2-1460 punya tanggal + cocok dengan buku besar.
  verify_p59.py
  # Fase 60 — gate ke-51: tampilan dokumen (kop, footer, baris biaya, tanda tangan) bisa
  # dikonfigurasi pemilik usaha, pratinjaunya dirender MESIN CETAK YANG SAMA, dan setiap
  # jalur cetak (staf, portal pembeli, kwitansi, BAST, penawaran) memakai konfigurasi itu.
  verify_p60.py
  # Fase 61 — gate ke-52: SPK subkontraktor & PO pengadaan punya bentuk CETAK berkop,
  # angkanya dari baris yang sama dengan penagihan, dan yang belum disetujui bertanda DRAFT.
  verify_p61.py
  verify_p62.py
  verify_p63.py
  verify_p64.py
  # Fase 65 — gate ke-56: notifikasi kembar diringkas jadi satu baris berjumlah (tanpa
  # menyembunyikan anggotanya), aksi kelompok mengenai seluruh anggota, dan setiap pemakai
  # memilih sendiri kategori/saluran yang boleh mengganggunya — kecuali permintaan TINDAKAN
  # yang tidak boleh bisa dibungkam (kalau bisa, persetujuan menggantung tanpa sebab).
  verify_p65.py
  # Fase 66 — gate ke-57: SATU layar per jenis dokumen. Naskah menempel pada jenis
  # dokumennya (kosakata placeholder diturunkan dari mesin penerbit), naskah benar-benar
  # TERCETAK (dibuktikan dengan membaca PDF), dan gaya tabel (garis transparan, nama kolom
  # tidak tampil) menjadi konfigurasi — bukan permintaan fitur.
  verify_p66.py
  # Fase 67 — gate ke-58: kedalaman & konsistensi tampilan. Menjaga agar layar tidak
  # kembali "flat": kanvas berlapis, primitif berbayang + fokus 2px, satu ukuran judul
  # halaman, dan afordansi (search bar berikon, status bertitik, kartu angka beraksen).
  verify_p67.py
  verify_p68.py
  # Fase 75b–78 — gate ke-60: biaya all-in per komponen dari master (sales memilih skema, bukan
  # mengetik), invoice/kuitansi biaya → titipan (kewajiban) → penyaluran, beban developer via AP,
  # pencairan KPR bertahap tervalidasi (tagihan terbit, ≤ plafon, toleransi, tanpa 2×, batal berjurnal).
  verify_p75-78.py
  # Fase 80–81 — gate ke-61: RAB tertempel pada tipe + SPK dari RAB (jejak & override beralasan),
  # versi RAB (riwayat/pulihkan), salin dari tipe lain, impor Excel, termin fasum ≤ progres fase.
  verify_p80_81.py
  # Fase 94 — permukaan autentikasi: tidak ada endpoint tanpa pagar yang membuat/meningkatkan
  # akun (lubang /auth/register), dokumentasi API mati di produksi, versi Graph API tunggal.
  verify_auth_surface.py
  # Fase 95 — satu pintu keluar WhatsApp: gagal tercatat gagal (bukan simulasi), wamid unik, outbox.
  verify_wa_gateway.py
  # Fase 96 — webhook Meta: handshake, tanda tangan palsu ditolak, idempoten, kontrak lama hidup.
  verify_wa_webhook.py
  # Fase 97 — kepatuhan: template belum approved ditolak, opt-out menghentikan marketing bukan
  # tagihan, jam kirim, broadcast tanpa status karangan.
  verify_wa_compliance.py
  # Fase 99 — template UTILITY berheader dokumen (PDF lolos di luar sesi 24 jam), Balasan Cerdas
  # berbasis playbook (tanpa LLM), dan penjaga agar pembersihan 10 gate merah tidak dibalik.
  verify_p99.py
  # Audit Tahap 7 §2 — gate ke-62: ANGKA KARTU = JUMLAH BARIS RINCIANNYA (Pola A untuk KPI).
  # Beranda per peran, Pipeline Lead (partisi), Keuangan (AR/AP/ember aging), BI (rumus tertulis,
  # nama sama = rumus sama), dan penjaga kode FIN-01/02/03, PRJ-01, CFG-01.
  verify_card_drilldown.py
  # P1 (2026-09-06 sesi lanjutan) — gate ke-70: REKONSILIASI GL SAMPAI SUMBER BARIS. Neraca saldo,
  # neraca, laba-rugi, arus kas dihitung ulang dari baris jurnal/ledger API (bukan flag
  # `balanced`), dan saldo GL dicocokkan dengan buku pembantu AP/retensi/kewajiban kontrak/
  # komisi/kas-bank; selisih sah (tagihan vendor belum disetujui) disebut sampai rupiahnya.
  verify_gl_reconciliation.py
)

fail=0
# Log gate ditaruh di dalam repo (BUKAN /tmp): /tmp bisa dibersihkan sistem di tengah run
# panjang, dan ringkasan "gate mana yang gagal" ikut hilang justru saat dibutuhkan.
LOGDIR="memory/gatelogs"
mkdir -p "$LOGDIR"
declare -a results
for g in "${GATES[@]}"; do
  if python3 "scripts/$g" > "$LOGDIR/gate_${g}.log" 2>&1; then
    results+=("  PASS  $g")
  else
    results+=("  FAIL  $g")
    fail=1
  fi
done

echo ""
echo "==================== GATE SUMMARY ===================="
for r in "${results[@]}"; do echo "$r"; done
echo "======================================================"
if [ $fail -ne 0 ]; then
  echo "OVERALL: FAIL — detail gate yang gagal:"
  for g in "${GATES[@]}"; do
    if ! grep -qE "PASSED|Total temuan perlu tindakan: 0" "$LOGDIR/gate_${g}.log" 2>/dev/null; then
      echo "----- $g -----"; tail -n 15 "$LOGDIR/gate_${g}.log";
    fi
  done
  exit 1
fi
echo "OVERALL: PASS (${#GATES[@]} gates)"
