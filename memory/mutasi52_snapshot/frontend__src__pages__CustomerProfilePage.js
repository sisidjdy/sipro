import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Building2, CreditCard, FileText, Headset, History, Receipt, ScrollText, ShieldOff,
  UserCircle2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import EntityHeader from "@/components/patterns/EntityHeader";
import TabPage from "@/components/patterns/TabPage";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import DocChecklist from "@/components/patterns/DocChecklist";
import TimelineFeed from "@/components/patterns/TimelineFeed";
import CustomerSummaryTab from "@/components/customers/CustomerSummaryTab";
import CustomerFinancingTab from "@/components/customers/CustomerFinancingTab";
import CustomerContractTab from "@/components/customers/CustomerContractTab";
import CustomerPaymentPlanTab from "@/components/customers/CustomerPaymentPlanTab";
import {
  CustomerUnitsTab, CustomerComplaintsTab,
} from "@/components/customers/CustomerRelatedTabs";
import { LoadingCards, ErrorState, PanelStateView } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { honestBadge, loadPanels, omittedSources, panelRows } from "@/utils/panelLoad";
import { CUSTPROFILE, PANELSTATE } from "@/constants/testIds";

/**
 * CustomerProfilePage (`/customers/:id`) — HALAMAN kanonik pelanggan (US-40-2).
 *
 * Tab “Kontrak & Harga” dan “Rencana Bayar” SEMPAT MATI dengan label “dijadwalkan Fase 43”.
 * Nomor itu sudah lewat (urutan pengerjaan nyata berbeda dari roadmap awal — lihat tabel
 * pemetaan di docs/v2/34_ROADMAP_EKSEKUSI.md), sementara datanya sebagian besar SUDAH ada:
 * penawaran (harga unit + add-on + diskon + skema) dan jadwal tagihan AR beserta
 * penerimaannya. Sekarang kedua tab menampilkan data nyata itu dan menyebut dengan jelas
 * bagian yang memang belum dibangun (kontrak formal + rincian biaya per komponen, toleransi
 * & mesin refund) — bukan lagi janji bernomor fase yang bisa kadaluarsa.
 *
 * ------------------------------------------------------------------------------------
 * FASE 52 — kelas cacat yang sama dengan `LeadProfilePage` ditutup di sini.
 *
 * Dulu enam permintaan panel dibungkus `.catch(() => ({ data: { data: [] } }))`. Halaman
 * memang tidak mati, tetapi hasilnya justru kebohongan yang lebih halus: penolakan izin
 * (403) berubah menjadi DAFTAR KOSONG, sehingga layar menulis “Tidak ada komplain”,
 * “Belum ada unit tertaut”, dan lencana “0” untuk data yang sebenarnya ADA — hanya tidak
 * boleh dibaca peran tersebut. Aturan repo ini tegas: jangan pernah menampilkan 0 / “belum
 * ada data” untuk sesuatu yang statusnya “tidak boleh dilihat”.
 *
 * Sekarang: `loadPanels()` (Promise.allSettled) memisahkan permintaan PRIMER
 * (`/customers/{id}`, satu-satunya yang boleh mematikan halaman) dari panel; setiap panel
 * yang ditolak/gagal bercerita sendiri lewat `PanelStateView`; lencana memakai
 * `honestBadge()`; dan spanduk `customer-profile-partial` menyebut panel mana yang tidak
 * ditampilkan beserta sebabnya.
 */

// Nama panel dalam bahasa pemakai (untuk spanduk & catatan timeline).
const PANEL_LABELS = {
  financing: "Pengajuan KPR",
  units: "Unit & progres pembangunan",
  complaints: "Komplain pelanggan",
  activities: "Aktivitas & catatan",
  submissions: "Dokumen syarat",
  timeline: "Jejak lintas modul (kwitansi, BAST, klaim garansi)",
};

export default function CustomerProfilePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState({ loading: true, error: "" });
  const [cust, setCust] = useState(null);
  const [panels, setPanels] = useState({});

  const load = useCallback(async () => {
    setState({ loading: true, error: "" });
    const res = await loadPanels({
      customer: () => api.get(`/customers/${id}`),
      financing: () => api.get("/financing", { params: { customer_id: id } }),
      units: () => api.get("/units", { params: { customer_id: id } }),
      complaints: () => api.get("/complaints", { params: { customer_id: id, limit: 50 } }),
      activities: () => api.get("/activities",
        { params: { entity_type: "customer", entity_id: id } }),
      submissions: () => api.get("/doc/submissions",
        { params: { entity_type: "customer", entity_id: id } }),
      // Jejak lintas-modul dirangkai SERVER (kwitansi, BAST, klaim garansi, komplain,
      // dokumen, aktivitas lead/unit). Dulu tab ini hanya membaca `activities` milik
      // pelanggan — yang tidak pernah ada isinya — sehingga selalu berbunyi "belum ada
      // jejak" walau pembelinya sudah membayar dan menerima kunci.
      timeline: () => api.get(`/customers/${id}/timeline`),
    });
    setPanels(res);
    const primer = res.customer;
    if (!primer.ok) {
      setCust(null);
      setState({
        loading: false,
        error: primer.status === 404 ? "Pelanggan tidak ditemukan."
          : primer.status === 403
            ? "Peran Anda tidak diberi akses ke data pelanggan. Hubungi admin bila memang "
              + "perlu membuka profil pembeli."
            : primer.offline
              ? "Tidak ada sambungan ke server, jadi profil pelanggan ini belum bisa dibuka."
              : (primer.detail || "Gagal memuat profil pelanggan."),
      });
      return;
    }
    setCust(primer.data);
    setState({ loading: false, error: "" });
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (state.loading) return <LoadingCards count={4} />;
  if (state.error || !cust) {
    return (
      <div data-testid={CUSTPROFILE.notFound} className="space-y-3">
        <ErrorState message={state.error} onRetry={load} />
        <Button variant="outline" size="sm" onClick={() => navigate("/customers")}>
          Kembali ke daftar pelanggan
        </Button>
      </div>
    );
  }

  const fins = panelRows(panels.financing);
  const units = panelRows(panels.units);
  const complaints = panelRows(panels.complaints);
  const acts = panelRows(panels.activities);
  const subs = panelRows(panels.submissions);
  const tl = {
    rows: panels.timeline?.ok ? (panels.timeline.res?.data?.data || []) : [],
    sources: panels.timeline?.ok ? (panels.timeline.res?.data?.sources || {}) : {},
    missing: panels.timeline?.ok ? (panels.timeline.res?.data?.missing || []) : [],
  };
  const omitted = omittedSources(panels, PANEL_LABELS);

  // Jejak dari server (lintas modul) DIGABUNG dengan yang sudah dimuat layar ini, lalu
  // baris kembar dibuang berdasarkan (waktu + judul). Menggabungkan seperti ini membuat
  // tab tetap berisi walau satu sumber gagal dimuat.
  const timelineLocal = [
    ...acts.map((a) => ({
      at: a.created_at, actor: a.actor || a.created_by, kind: "activity",
      title: a.type === "comment" ? "Catatan" : (a.title || "Aktivitas"), body: a.body,
    })),
    ...subs.map((s) => ({
      at: s.submitted_at || s.created_at, actor: s.submitted_by, kind: "upload",
      title: `Dokumen “${s.requirement_label || s.requirement_code}” diserahkan`,
      body: s.status === "verified" ? `Diverifikasi oleh ${s.verified_by || "-"}`
        : s.status === "rejected" ? `Ditolak: ${s.reject_reason || "-"}` : "Menunggu verifikasi",
    })),
    ...complaints.map((c) => ({
      at: c.created_at, actor: c.assigned_to || "portal pembeli", kind: "message",
      title: `Komplain: ${c.subject}`, body: `Status ${c.status}`,
    })),
  ];
  const seen = new Set();
  const timeline = [...tl.rows, ...timelineLocal].filter((r) => {
    const k = `${r.at}|${r.title}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  const sumberTerpakai = Object.entries(tl.sources || {})
    .filter(([, n]) => n > 0).map(([k]) => k.replace(/_/g, " "));

  // Angka pada chip kepala HANYA ditulis bila datanya benar-benar terbaca. "0" untuk panel
  // yang ditolak adalah pernyataan palsu ("pembeli ini tidak punya unit").
  const countChip = (panel, rows) => (panel?.ok
    ? String(rows.length)
    : <span className="text-xs text-muted-foreground">tidak dibuka untuk peran Anda</span>);

  const header = (
    <EntityHeader testId={CUSTPROFILE.header} kicker="CRM · Profil Pelanggan" title={cust.name}
      subtitle={[cust.phone, cust.email].filter(Boolean).join(" · ")}
      onBack={() => navigate("/customers")} backLabel="Daftar pelanggan"
      chips={[
        {
          label: "KYC",
          value: <StatusPill status={cust.kyc_status}
            label={cust.kyc_status === "submitted" ? "Terkirim" : "Pending"} />,
        },
        { label: "NIK", value: cust.nik || "-" },
        { label: "Penghasilan", value: <MoneyText value={cust.monthly_income} short /> },
        { label: "Unit", value: countChip(panels.units, units) },
        { label: "KPR", value: countChip(panels.financing, fins) },
      ]} />
  );

  return (
    <div data-testid={CUSTPROFILE.page} className="space-y-4">
      {omitted.length ? (
        <div data-testid={CUSTPROFILE.partial}
          className="rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-sm text-slate-700">
          <p className="flex items-center gap-2 font-medium text-slate-900">
            <ShieldOff className="h-4 w-4" /> Sebagian panel tidak ditampilkan
          </p>
          <ul className="mt-1.5 space-y-1">
            {omitted.map((o) => (
              <li key={o.key} data-testid={`customer-profile-omitted-${o.key}`}>
                • <span className="font-medium">{o.label}</span> — {o.reason}.
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-xs text-slate-600">
            Sisa profil pelanggan ini tetap bisa dipakai. Angka pada bagian yang tertutup
            sengaja dikosongkan — menulis 0 berarti mengaku “tidak ada datanya”.
          </p>
        </div>
      ) : null}

      <TabPage header={header} tabs={[
        {
          key: "ringkasan", label: "Ringkasan", icon: UserCircle2,
          content: <CustomerSummaryTab customer={cust} onChanged={load} />,
        },
        {
          key: "kontrak", label: "Kontrak & Harga", icon: ScrollText,
          content: <CustomerContractTab customer={cust} />,
        },
        {
          key: "bayar", label: "Rencana Bayar", icon: Receipt,
          content: <CustomerPaymentPlanTab customer={cust} />,
        },
        {
          key: "kpr", label: "KPR", icon: CreditCard, badge: honestBadge(panels.financing),
          content: panels.financing?.ok
            ? <CustomerFinancingTab customer={cust} financings={fins} onChanged={load} />
            : <PanelStateView panel={panels.financing} subject="Pengajuan KPR" onRetry={load}
              whoMay={"Data KPR dibuka untuk tim Sales, Marketing Admin, dan Keuangan."} />,
        },
        {
          key: "dokumen", label: "Dokumen & Legal", icon: FileText,
          badge: honestBadge(panels.submissions,
            subs.filter((s) => s.status === "verified").length),
          content: <DocChecklist entityType="customer" entityId={id} onChanged={load} />,
        },
        {
          key: "unit", label: "Unit & Konstruksi", icon: Building2,
          badge: honestBadge(panels.units),
          content: panels.units?.ok
            ? <CustomerUnitsTab units={units} />
            : <PanelStateView panel={panels.units} subject="Unit & progres pembangunan"
              onRetry={load} />,
        },
        {
          key: "komplain", label: "Komplain", icon: Headset,
          badge: honestBadge(panels.complaints),
          content: panels.complaints?.ok
            ? <CustomerComplaintsTab complaints={complaints} />
            : <PanelStateView panel={panels.complaints} subject="Komplain pelanggan"
              onRetry={load}
              whoMay={"Komplain ditangani tim Layanan/CS; peran proyek tidak membacanya di sini."} />,
        },
        {
          key: "timeline", label: "Timeline", icon: History,
          content: (
            <div className="space-y-2">
              <p data-testid={CUSTPROFILE.timelineSources}
                className="rounded-lg border bg-secondary/40 px-3 py-2 text-[12px] text-muted-foreground">
                Jejak dirangkai dari{" "}
                <b>{sumberTerpakai.length ? sumberTerpakai.join(", ") : "belum ada sumber"}</b>
                {(tl.missing || []).length ? (
                  <> · belum ada datanya: <b>{tl.missing.join(", ").replace(/_/g, " ")}</b></>
                ) : null}.
              </p>
              {omitted.length ? (
                // Tab gabungan paling mudah berbohong: bila satu sumber tertutup, jejaknya
                // SEBAGIAN — dan itu harus tertulis, bukan disembunyikan.
                <div data-testid={PANELSTATE.omitted}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                  <p className="font-medium text-slate-900">Jejak ini SEBAGIAN</p>
                  <ul className="mt-1 space-y-0.5 text-xs">
                    {omitted.map((o) => (
                      <li key={o.key}>• {o.label} tidak disertakan — {o.reason}.</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <TimelineFeed items={timeline}
                emptyText={omitted.length
                  ? "Tidak ada jejak yang bisa ditampilkan dari sumber yang boleh Anda baca."
                  : "Belum ada jejak untuk pelanggan ini — belum ada pembayaran, serah terima, klaim garansi, komplain, maupun dokumen yang tercatat atas namanya."} />
            </div>
          ),
        },
      ]} />
    </div>
  );
}
