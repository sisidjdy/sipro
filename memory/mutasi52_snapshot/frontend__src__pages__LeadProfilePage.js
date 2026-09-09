import React, { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  CalendarCheck2, ClipboardList, FileSignature, FileText, Handshake, History,
  MessageSquare, Phone, ShieldCheck, ShieldOff, UserCircle2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import EntityHeader from "@/components/patterns/EntityHeader";
import TabPage from "@/components/patterns/TabPage";
import AgingCell from "@/components/patterns/AgingCell";
import StatusPill from "@/components/patterns/StatusPill";
import DocChecklist from "@/components/patterns/DocChecklist";
import LeadWaPanel from "@/components/sales/LeadWaPanel";
import LeadSummaryTab from "@/components/leads/LeadSummaryTab";
import LeadTimelineTab from "@/components/leads/LeadTimelineTab";
import LeadSurveyTab from "@/components/leads/LeadSurveyTab";
import LeadUnitsTab from "@/components/leads/LeadUnitsTab";
import LeadPartnerFeeTab from "@/components/leads/LeadPartnerFeeTab";
import QuotationsTab from "@/components/quotations/QuotationsTab";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { honestBadge, loadPanels, omittedSources, panelRows } from "@/utils/panelLoad";
import { LEADPROFILE, TABPAGE } from "@/constants/testIds";

/**
 * LeadProfilePage (`/leads/:id`) — HALAMAN kanonik lead (US-40-2, CR-10).
 *
 * Kenapa halaman, bukan drawer: isi lead jauh lebih dari satu layar (gerbang tahap,
 * dokumen syarat, survei, percakapan WA, unit, riwayat). Di drawer semuanya bertumpuk
 * vertikal sehingga checklist dokumen Fase 39b praktis tersembunyi di dasar gulungan —
 * itulah alasan owner memutuskan `DocChecklist` PINDAH ke halaman ini (tab "Dokumen").
 *
 * Semua panel yang sudah lulus uji pada fase sebelumnya dipakai ulang apa adanya
 * (LeadLifecyclePanel, LeadWaPanel, DocChecklist), jadi pemindahan ini tidak menghapus
 * satu pun kemampuan.
 *
 * ------------------------------------------------------------------------------------
 * FASE 52 — CACAT NYATA YANG DITUTUP DI SINI (dengan bukti server)
 *
 * Dulu keenam permintaan halaman ini dijalankan dengan `Promise.all`. Satu penolakan
 * membatalkan lima yang lain, lalu satu cabang `catch` menebak sebabnya dari error mana pun
 * yang menang duluan. Bukti dari container ini (sandi demo, lead milik sales@):
 *
 *   finance@sipro.co.id  → GET /api/leads/{id}            = 200
 *                          GET /api/appointments?lead_id= = 403
 *   finlead@sipro.co.id  → sama.
 *
 * Akibatnya SELURUH halaman (10 tab) diganti satu kotak merah bertuliskan "Peran Anda tidak
 * diberi akses ke data lead — bukan hanya lead ini", padahal:
 *   (1) leadnya BARU SAJA terbaca 200, dan
 *   (2) finance memang punya `leads:view_all`; yang ditolak hanya panel jadwal survei.
 * Layar bukan sekadar mati — layar berbohong dan menuduh izin yang salah.
 *
 * Sekarang:
 *   • Hanya `GET /leads/{id}` yang FATAL. Kalimat 403 halaman-penuh disusun DARI ERROR
 *     PERMINTAAN ITU SENDIRI (`panels.lead`), bukan dari error panel mana pun.
 *   • Panel yang ditolak/gagal bercerita di TABNYA SENDIRI (`PanelStateView`), halaman hidup.
 *   • Lencana tab memakai `honestBadge`: `undefined` bila datanya tidak boleh dibaca — bukan
 *     angka 0 yang berbunyi "tidak ada survei".
 *   • Spanduk `lead-profile-partial` menyebut panel mana yang tidak ditampilkan dan mengapa.
 * Izin bacanya juga dirapikan di server: `appointments` kini memberi finance &
 * finance_manager `view_all` (BACA saja — yang menjadwalkan tetap sales/marketing).
 */

// Nama panel dalam BAHASA PEMAKAI (dipakai spanduk & catatan timeline). Sengaja bukan nama
// endpoint: pemakai tidak perlu tahu ada berapa permintaan di belakang layar.
const PANEL_LABELS = {
  lifecycle: "Gerbang tahap & langkah berikutnya",
  activities: "Riwayat aktivitas & catatan",
  appointments: "Jadwal survei & janji temu",
  deals: "Unit yang dipegang lead",
  submissions: "Dokumen syarat",
};

export default function LeadProfilePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { labelOf } = useReference();
  const [state, setState] = useState({ loading: true, error: "" });
  const [lead, setLead] = useState(null);
  const [panels, setPanels] = useState({});
  const [waKey, setWaKey] = useState(0);

  const load = useCallback(async () => {
    setState({ loading: true, error: "" });
    // TAHAN-BANTING: `loadPanels` memakai Promise.allSettled, jadi penolakan satu panel
    // TIDAK MEMBATALKAN yang lain (itulah inti cacat Fase 52).
    const res = await loadPanels({
      lead: () => api.get(`/leads/${id}`),
      lifecycle: () => api.get(`/leads/${id}/lifecycle`),
      activities: () => api.get("/activities", { params: { entity_type: "lead", entity_id: id } }),
      appointments: () => api.get("/appointments", { params: { lead_id: id } }),
      deals: () => api.get("/deals", { params: { lead_id: id } }),
      submissions: () => api.get("/doc/submissions",
        { params: { entity_type: "lead", entity_id: id } }),
    });
    setPanels(res);

    // ---- Hanya permintaan PRIMER yang boleh mematikan halaman ----
    const primer = res.lead;
    if (!primer.ok) {
      setLead(null);
      // Dua sebab 403 yang BERBEDA tidak boleh diringkas menjadi satu kalimat: server
      // membedakan "bukan lead Anda" (lingkup baris — lead ini milik rekan lain) dari
      // "tidak memiliki izin 'view' pada 'leads'" (peran ini tidak diberi akses lead sama
      // sekali). Yang dibaca di sini adalah `rawDetail` MILIK PERMINTAAN LEAD — bukan detail
      // error panel lain seperti dulu, yang membuat layar menuduh izin yang salah.
      const bukanMilikSaya = /bukan lead anda/i.test(primer.rawDetail || "");
      setState({
        loading: false,
        error: primer.status === 404 ? "Lead tidak ditemukan."
          : primer.status === 403 ? (bukanMilikSaya
            ? "Lead ini milik rekan lain. Hanya pemilik lead, manajer sales, atau marketing "
              + "admin yang boleh membukanya."
            : "Peran Anda tidak diberi akses ke data lead — bukan hanya lead ini. Hubungi "
              + "admin bila memang perlu membuka pipeline lead.")
            : primer.offline
              ? "Tidak ada sambungan ke server, jadi profil lead ini belum bisa dibuka."
              : (primer.detail || "Gagal memuat profil lead."),
      });
      return;
    }
    setLead(primer.data);
    setState({ loading: false, error: "" });
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const refresh = () => { load(); setWaKey((k) => k + 1); };

  // Aksi dari checklist syarat / kartu langkah berikutnya: pindah ke TAB yang tepat
  // (dulu men-scroll di dalam drawer; di halaman, tab adalah alamat yang bisa dibagikan).
  const goTab = (tab) => {
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    navigate(`${url.pathname}${url.search}`, { replace: false });
  };
  const handleAction = (key) => {
    if (key === "appointment") return goTab("survey");
    if (key === "reserve" || key === "deal") return goTab("unit");
    if (key === "wa") return goTab("percakapan");
    if (key === "slik" || key === "disposition" || key === "close") return goTab("ringkasan");
    if (key === "document" || key === "doc") return goTab("dokumen");
    return undefined;
  };

  if (state.loading) {
    return <div className="space-y-4"><LoadingCards count={4} /></div>;
  }
  if (state.error || !lead) {
    return (
      <div data-testid={LEADPROFILE.notFound} className="space-y-3">
        <ErrorState message={state.error} onRetry={load} />
        <Button variant="outline" size="sm" onClick={() => navigate("/leads")}>
          Kembali ke daftar lead
        </Button>
      </div>
    );
  }

  const acts = panelRows(panels.activities);
  const appts = panelRows(panels.appointments);
  const deals = panelRows(panels.deals);
  const subs = panelRows(panels.submissions);
  const life = panels.lifecycle?.ok ? panels.lifecycle.data : null;
  const omitted = omittedSources(panels, PANEL_LABELS);
  const docCount = subs.filter((s) => s.status === "verified").length;

  const header = (
    <EntityHeader testId={LEADPROFILE.header} kicker="CRM · Profil Lead" title={lead.name}
      subtitle={[lead.phone, lead.email].filter(Boolean).join(" · ")}
      onBack={() => navigate("/leads")} backLabel="Daftar lead"
      chips={[
        { label: "Tahap", value: <StatusPill status={lead.stage} group="lead_stage" /> },
        { label: "Skor", value: `${lead.score} · ${labelOf("score_band", lead.score_band)}` },
        { label: "Sumber", value: labelOf("lead_source", lead.source) },
        { label: "PIC", value: lead.assigned_to || "-" },
        {
          label: "Umur",
          value: <AgingCell ageHours={lead.age_hours} stageAgeHours={lead.stage_age_hours}
            slaHours={lead.stage_sla_hours} state={lead.sla_state} />,
        },
      ]}
      actions={(
        <>
          <Button data-testid={LEADPROFILE.callBtn} size="sm" variant="outline" asChild>
            <a href={`tel:${lead.phone}`}><Phone className="mr-1.5 h-4 w-4" /> Telepon</a>
          </Button>
          <Button data-testid={LEADPROFILE.waBtn} size="sm" onClick={() => goTab("percakapan")}>
            <MessageSquare className="mr-1.5 h-4 w-4" /> WhatsApp
          </Button>
        </>
      )} />
  );

  return (
    <div data-testid={LEADPROFILE.page} className="space-y-4">
      {omitted.length ? (
        // Spanduk jujur: pemakai berhak tahu bahwa halaman ini TIDAK LENGKAP dan mengapa —
        // tanpa itu ia mengira datanya hilang dan mulai mencari-cari.
        <div data-testid={LEADPROFILE.partial}
          className="rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-sm text-slate-700">
          <p className="flex items-center gap-2 font-medium text-slate-900">
            <ShieldOff className="h-4 w-4" /> Sebagian panel tidak ditampilkan
          </p>
          <ul className="mt-1.5 space-y-1">
            {omitted.map((o) => (
              <li key={o.key} data-testid={`lead-profile-omitted-${o.key}`}>
                • <span className="font-medium">{o.label}</span> — {o.reason}.
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-xs text-slate-600">
            Sisa profil lead ini tetap bisa dipakai seperti biasa; yang tertutup hanya bagian
            di atas. Angka pada tab yang tertutup sengaja dikosongkan — menulis 0 berarti
            mengaku “tidak ada datanya”, dan itu belum tentu benar.
          </p>
        </div>
      ) : null}

      <TabPage testId={TABPAGE.root} header={header} tabs={[
        {
          key: "ringkasan", label: "Ringkasan", icon: UserCircle2,
          content: <LeadSummaryTab lead={lead} lifecycle={life}
            lifecyclePanel={panels.lifecycle} onAction={handleAction} onChanged={refresh} />,
        },
        {
          key: "timeline", label: "Timeline", icon: History,
          content: <LeadTimelineTab lead={lead} activities={acts} appointments={appts}
            submissions={subs} omitted={omitted} />,
        },
        {
          key: "dokumen", label: "Dokumen", icon: FileText,
          badge: honestBadge(panels.submissions, docCount),
          content: <DocChecklist entityType="lead" entityId={id} onChanged={refresh} />,
        },
        {
          key: "survey", label: "Survey", icon: CalendarCheck2,
          badge: honestBadge(panels.appointments),
          content: <LeadSurveyTab leadId={id} appointments={appts}
            panel={panels.appointments} onRetry={refresh} onChanged={refresh} />,
        },
        {
          key: "unit", label: "Unit & SPR", icon: Handshake,
          badge: honestBadge(panels.deals),
          content: <LeadUnitsTab leadId={id} leadName={lead.name} deals={deals}
            panel={panels.deals} onRetry={refresh} onChanged={refresh} />,
        },
        {
          key: "penawaran", label: "Penawaran", icon: FileSignature,
          content: <QuotationsTab leadId={id} leadName={lead.name} onChanged={refresh} />,
        },
        {
          key: "percakapan", label: "Percakapan", icon: MessageSquare,
          content: <LeadWaPanel key={waKey} leadId={id} onChanged={refresh} />,
        },
        {
          key: "bi", label: "BI / SLIK", icon: ShieldCheck,
          content: (
            <div className="rounded-lg border bg-card p-4 text-sm">
              <p className="font-medium">Pra-skrining BI/SLIK ada di tab Ringkasan.</p>
              <p className="mt-1 text-muted-foreground">
                Panel SLIK menempel pada gerbang tahap (bukti iDeb wajib sebelum Booking).
                Menu BI Checking mandiri (pra-skrining sebelum booking, di luar urutan tahap)
                belum dibangun.
              </p>
              <Button className="mt-3" size="sm" variant="outline"
                onClick={() => goTab("ringkasan")}>Buka gerbang tahap</Button>
            </div>
          ),
        },
        {
          key: "mitra", label: "Fee Mitra", icon: ClipboardList,
          content: <LeadPartnerFeeTab leadId={id} lead={lead} />,
        },
      ]} />
    </div>
  );
}
