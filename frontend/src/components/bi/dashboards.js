import React, { useState } from "react";

import DashboardShell from "@/components/bi/DashboardShell";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { BI } from "@/constants/testIds";

/**
 * Lima dashboard persona (Dok 31 §2). Tiap dashboard hanya menentukan: endpoint, grafik apa
 * yang menjawab pertanyaan personanya, dan filter khususnya. Sisanya (pemuatan, kejujuran
 * angka, rincian, ekspor) milik `DashboardShell` supaya perilakunya tidak bercabang.
 */
export function ExecutiveDashboard({ params }) {
  return (
    <DashboardShell endpoint="/analytics/executive" params={params} testId="bi-dash-eksekutif"
      description="Pertanyaan direksi: sudah berapa terjual, uangnya sudah masuk berapa, dan di mana risikonya."
      charts={[
        { code: "SLS-01", kind: "series", title: "Unit terjual (kumulatif)",
          description: "Deret dari tanggal booking yang benar-benar tercatat." },
        { code: "SLS-05", kind: "series", title: "Kas masuk per bulan",
          description: "Σ kuitansi penerimaan — uang yang sudah benar-benar diterima." },
        { code: "SLS-06", title: "Piutang jatuh tempo per ember umur" },
        { code: "BGT-04", title: "Pencapaian target unit per proyek",
          description: "Dibandingkan dengan target AKTIF; realisasi dibaca dari deal yang benar-benar tercatat." },
        { code: "PRC-01", title: "Potongan diberikan per proyek",
          description: "Σ skema diskon + promo + kupon dari rincian harga yang TERSIMPAN pada deal." },
        { code: "RAB-02", title: "Margin HPP proyeksi per proyek (RAB terstruktur)",
          description: "Harga jual + add-on terjual − RAB (tipe × unit + add-on + fasum + umum). Angka yang sama dengan RAB/BoQ › Ringkasan & HPP." },
        { code: "RAB-03", title: "Margin HPP per tipe unit (%)",
          description: "Tipe bermargin tipis (<10%) tampil di rincian — HPP = RAB tipe + alokasi biaya bersama." },
        { code: "PRJ-04", title: "Realisasi terhadap RAB per kategori" },
      ]} />
  );
}

export function SalesLeadDashboard({ params }) {
  const [groupBy, setGroupBy] = useState("source");
  return (
    <DashboardShell endpoint="/analytics/sales/funnel" params={{ ...params, group_by: groupBy }}
      testId="bi-dash-penjualan"
      description="Pertanyaan manajer sales: di mana lead bocor, berapa lama tiap tahap, dan sumber mana yang benar-benar menghasilkan."
      extraFilters={(
        <div className="w-44">
          <ReferenceSelect group="analytics_dimension" value={groupBy} onChange={setGroupBy}
            testId={BI.dictPersona} placeholder="Kelompokkan per…" />
        </div>
      )}
      charts={[
        { code: "LED-02", title: "Conversion per tahap",
          description: "Dihitung dari riwayat tahap (bukan status akhir), sehingga lead yang sempat naik lalu turun tetap terlihat." },
        { code: "LED-05", title: "Distribusi umur tahap lead aktif" },
        { code: "LED-13", title: "Kualitas per sumber lead" },
        { code: "LED-10", kind: "pie", title: "Alasan lead hilang" },
        { code: "PRC-02", title: "Potongan diberikan per sales",
          description: "Siapa yang paling banyak memberi potongan — dari skema diskon, promo, dan kupon yang tersimpan pada deal." },
        { code: "PRC-03", kind: "pie", title: "Komposisi potongan: skema · promo · kupon" },
        { code: "PRC-01", kind: "series", title: "Potongan per bulan (deret)" },
        { code: "PRC-04", title: "Pemakaian kupon per kode" },
      ]} />
  );
}

export function MarketingDashboard({ params }) {
  const [components, setComponents] = useState("ads,partner");
  return (
    <DashboardShell endpoint="/analytics/marketing/performance" params={params}
      testId="bi-dash-marketing"
      description="Pertanyaan supervisor DM: kampanye mana yang efisien, dan berapa biaya sebenarnya per pembeli."
      extraFilters={(
        <select data-testid={BI.cacComponents} value={components} aria-label="Komponen CAC"
          onChange={(e) => setComponents(e.target.value)}
          className="h-9 rounded-md border bg-background px-2 text-sm">
          <option value="ads,partner">CAC: iklan + fee mitra</option>
          <option value="ads">CAC: iklan saja</option>
          <option value="ads,partner,opex">CAC: iklan + fee + opex</option>
        </select>
      )}
      charts={[
        { code: "MKT-02", title: "CPL per kampanye",
          description: "Kampanye tanpa biaya tetap ditampilkan dengan nilai kosong — tidak dihapus dari grafik." },
        { code: "MKT-04", kind: "pie", title: "Campuran kanal lead" },
        { code: "MKT-03", title: "ROAS per kampanye" },
        { code: "MKT-05", title: "Event konversi per jenis" },
      ]} />
  );
}

export function ProjectCostDashboard({ params }) {
  return (
    <DashboardShell endpoint="/analytics/project/schedule-health" params={params}
      testId="bi-dash-proyek"
      description="Pertanyaan manajer proyek & direksi: progresnya sesuai rencana? biayanya masih di dalam RAB?"
      charts={[
        { code: "PRJ-01", title: "Progres per unit (berbobot)" },
        { code: "PRJ-02", title: "Keterlambatan per unit" },
        { code: "PRJ-03", title: "Realisasi RAB per kategori" },
        { code: "BGT-02", title: "Exposure anggaran per proyek",
          description: "Exposure = realisasi + komitmen. Dipakai untuk peringatan dini sebelum tagihannya masuk." },
        { code: "BGT-03", title: "Item anggaran overbudget" },
        { code: "PRJ-09", title: "Komitmen belum tertagih per vendor" },
        { code: "RAB-01", kind: "pie", title: "Komposisi RAB terstruktur",
          description: "RAB unit (tipe × unit) · add-on terjual · fasum/fasos · umum · item lama." },
        { code: "RAB-04", title: "SPK fasum: termin disetujui vs progres fase",
          description: "Nilai = termin kumulatif %; rincian memuat batas dari progres fase konstruksi tertaut. Baris merah = melampaui." },
        { code: "RAB-05", title: "Selisih SPK terhadap dasar RAB",
          description: "Override beralasan saat SPK dibuat dari RAB — positif = kontrak di atas RAB." },
        { code: "RAB-06", kind: "series", title: "Revisi RAB tipe/add-on per hari",
          description: "Setiap Simpan yang mengubah baris RAB tercatat sebagai versi; rincian per tipe memuat arah perubahan total." },
      ]} />
  );
}

export function TeamDashboard({ params }) {
  return (
    <DashboardShell endpoint="/analytics/users/daily" params={params} testId="bi-dash-tim"
      description="Pertanyaan supervisor: siapa mengerjakan apa, tepat waktu atau tidak, dan siapa yang kelebihan beban."
      charts={[
        { code: "USR-01", kind: "series", title: "Jejak aktivitas harian" },
        { code: "USR-02", title: "Ketepatan waktu per user" },
        { code: "USR-05", title: "Beban kerja aktif per user" },
        { code: "USR-07", title: "Perpindahan tahap per pelaku" },
      ]} />
  );
}
