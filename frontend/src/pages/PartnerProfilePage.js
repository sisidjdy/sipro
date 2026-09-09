import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle, Banknote, FileText, Handshake, ListChecks, TrendingUp, UserPlus,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import EntityHeader from "@/components/patterns/EntityHeader";
import TabPage from "@/components/patterns/TabPage";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import KpiCard from "@/components/patterns/KpiCard";
import AgingCell from "@/components/patterns/AgingCell";
import EmptyState from "@/components/patterns/EmptyState";
import DocChecklist from "@/components/patterns/DocChecklist";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import FeeRulesTab from "@/components/partners/FeeRulesTab";
import PartnerFormDialog from "@/components/partners/PartnerFormDialog";
import PartnerStatusDialog from "@/components/partners/PartnerStatusDialog";
import PartnerWebhookCard from "@/components/partners/PartnerWebhookCard";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import { formatDateWIB, fromNow } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PARTNERS } from "@/constants/testIds";

function Row({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b py-1.5 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-right text-sm">{value || "—"}</span>
    </div>
  );
}

/**
 * PartnerProfilePage (`/partners/:id`) — halaman KANONIK satu mitra (Fase 42 §8.5).
 *
 * Semua yang perlu diketahui tentang satu mitra ada di satu tempat: profil & rekening,
 * kontrak (yang menentukan boleh/tidaknya menerima fee), aturan fee yang menaunginya,
 * lead yang ia setor beserta umur tahapnya, tagihan fee-nya, dan angka kinerjanya.
 */
export default function PartnerProfilePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { labelOf } = useReference();
  const { can } = useAuth();
  // Izin diambil dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis
  // ulang di layar. Matriks RBAC bisa diubah admin lewat Pusat Konfigurasi; daftar peran
  // hardcode membuat tombol berbeda dengan jawaban server — tombol mati (403) atau
  // tombol yang seharusnya ada tapi hilang.
  const canManage = can("partners", "update");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get(`/partners/${id}`);
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat profil mitra.");
    } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  const p = data.partner || {};
  const m = data.metrics || {};
  const stats = p.stats || {};

  const profileTab = (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
        <h3 className="mb-2 text-sm font-semibold">Identitas &amp; pembayaran</h3>
        <Row label="Kode mitra" value={p.code} />
        <Row label="Jenis" value={labelOf("partner_kind", p.partner_kind)} />
        <Row label="Bentuk badan" value={labelOf("partner_entity_type", p.entity_type)} />
        <Row label="Perusahaan" value={p.company} />
        <Row label="Telepon" value={p.phone} />
        <Row label="Email" value={p.email} />
        <Row label="NIK" value={p.nik} />
        <Row label="NPWP" value={p.npwp} />
        <Row label="Alamat" value={p.address} />
        <Row label="PIC" value={p.pic_name ? `${p.pic_name} (${p.pic_phone || "-"})` : null} />
        <Row label="Rekening" value={p.bank_account
          ? `${p.bank_name || ""} ${p.bank_account} — ${p.bank_account_name || ""}` : null} />
        <Row label="Catatan" value={p.note} />
      </div>
      <div className="space-y-4">
        <div data-testid={PARTNERS.statsCard} className="grid gap-3 sm:grid-cols-2">
          <KpiCard label="Lead disetor" value={stats.leads ?? m.leads ?? 0}
            hint={`${stats.contacted ?? 0} sudah dihubungi`}
            to={`/leads?partner_id=${p.id}`} />
          <KpiCard label="Booking · closing"
            value={`${stats.booked ?? m.booked ?? 0} · ${stats.won ?? m.won ?? 0}`}
            hint={m.win_rate_pct !== null && m.win_rate_pct !== undefined
              ? `win rate ${m.win_rate_pct}%` : "belum ada closing"} />
          <KpiCard label="Fee disetujui" value={<MoneyText value={stats.fee_total} short />}
            hint={`dibayar ${new Intl.NumberFormat("id-ID").format(stats.fee_paid || 0)}`} />
          <KpiCard label="Sisa utang fee"
            value={<MoneyText value={stats.fee_outstanding} short />}
            tone={stats.fee_outstanding ? "amber" : "primary"}
            hint="saldo 2-1500 milik mitra ini" />
        </div>
        <div data-testid={PARTNERS.contractCard} className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            Kontrak kerja sama
            {data.contract_ok ? (
              <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700">
                berlaku
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5
                text-xs text-amber-800">
                <AlertTriangle className="h-3 w-3" /> bermasalah
              </span>
            )}
          </h3>
          <Row label="Nomor" value={p.contract?.number} />
          <Row label="Mulai" value={p.contract?.start_date
            ? formatDateWIB(p.contract.start_date) : null} />
          <Row label="Berakhir" value={p.contract?.end_date
            ? formatDateWIB(p.contract.end_date) : null} />
          <Row label="Ditandatangani" value={p.contract?.signed_by} />
          {!data.contract_ok ? (
            <p className="mt-2 text-xs text-amber-800">
              {data.contract_note} — selama aturan
              <code className="mx-1">partner.require_contract_active</code> menyala, lead &amp;
              tagihan fee BARU dari mitra ini ditolak.
            </p>
          ) : null}
        </div>
        <PartnerWebhookCard partner={p} webhook={data.webhook} canManage={canManage}
          onDone={load} />
        {(p.status_history || []).length ? (          <div className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
            <h3 className="mb-2 text-sm font-semibold">Riwayat status</h3>
            {(p.status_history || []).slice().reverse().map((h, i) => (
              <div key={`${h.at}-${i}`} className="border-b py-1.5 text-xs last:border-0">
                <p>
                  <strong>{h.from} → {h.to}</strong> · {fromNow(h.at)} oleh {h.by}
                </p>
                <p className="text-muted-foreground">{h.reason}</p>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );

  const leadsTab = (data.leads || []).length ? (
    <div className="overflow-x-auto rounded-lg border bg-card shadow-[var(--shadow-card)]">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left">Lead</th>
            <th className="px-3 py-2 text-left">Tahap</th>
            <th className="px-3 py-2 text-left">PIC</th>
            <th className="px-3 py-2 text-left">Umur (total · tahap)</th>
            <th className="px-3 py-2 text-left">Masuk</th>
          </tr>
        </thead>
        <tbody>
          {(data.leads || []).map((l) => (
            <tr key={l.id} data-lead={l.id} className="cursor-pointer border-t hover:bg-muted/40"
              onClick={() => navigate(`/leads/${l.id}`)}>
              <td className="px-3 py-2">
                <p className="font-medium text-primary">{l.name}</p>
                <p className="text-xs text-muted-foreground">{l.phone}</p>
              </td>
              <td className="px-3 py-2">
                <StatusPill status={l.stage} group="lead_stage" />
              </td>
              <td className="px-3 py-2 text-xs">{l.assigned_to || "—"}</td>
              <td className="px-3 py-2">
                <AgingCell ageHours={l.age_hours} stageAgeHours={l.stage_age_hours}
                  slaHours={l.stage_sla_hours} state={l.sla_state} />
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">{fromNow(l.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <EmptyState icon={UserPlus} title="Mitra ini belum menyetor lead"
      description="Lead yang dibuat dengan sumber 'Mitra / pihak ketiga' dan mitra ini akan muncul di sini." />
  );

  const feesTab = (data.fees || []).length ? (
    <div className="overflow-x-auto rounded-lg border bg-card shadow-[var(--shadow-card)]">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left">No</th>
            <th className="px-3 py-2 text-left">Unit</th>
            <th className="px-3 py-2 text-left">Pemicu · aturan</th>
            <th className="px-3 py-2 text-right">Beban</th>
            <th className="px-3 py-2 text-right">PPh</th>
            <th className="px-3 py-2 text-right">Netto</th>
            <th className="px-3 py-2 text-right">Dibayar</th>
            <th className="px-3 py-2 text-left">Status</th>
          </tr>
        </thead>
        <tbody>
          {(data.fees || []).map((f) => (
            <tr key={f.id} data-fee={f.id} className="border-t">
              <td className="px-3 py-2 font-medium">{f.no}</td>
              <td className="px-3 py-2">{f.unit_code || "—"}</td>
              <td className="px-3 py-2 text-xs">
                {labelOf("marketing_fee_trigger", f.trigger) || f.trigger}
                {f.rule_code ? (
                  <span className="text-muted-foreground"> · {f.rule_code}</span>
                ) : (
                  <span className="text-muted-foreground"> · pengajuan manual</span>
                )}
                {f.share_pct && f.share_pct !== 100 ? (
                  <span className="text-muted-foreground"> · porsi {f.share_pct}%</span>
                ) : null}
                {f.needs_owner_approval ? (
                  <span className="ml-1 text-amber-700">· butuh persetujuan owner</span>
                ) : null}
              </td>
              <td className="px-3 py-2 text-right"><MoneyText value={f.amount_gross} short /></td>
              <td className="px-3 py-2 text-right"><MoneyText value={f.pph_amount} short /></td>
              <td className="px-3 py-2 text-right"><MoneyText value={f.amount_net} short /></td>
              <td className="px-3 py-2 text-right"><MoneyText value={f.paid_amount} short /></td>
              <td className="px-3 py-2">
                <StatusPill status={f.status} group="marketing_fee_status" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t px-3 py-2 text-xs text-muted-foreground">
        Persetujuan &amp; pembayaran tagihan dikerjakan finance di tab
        <strong> Tagihan Fee</strong> pada halaman Mitra &amp; Fee.
      </p>
    </div>
  ) : (
    <EmptyState icon={Banknote} title="Belum ada tagihan fee"
      description="Tagihan terbit otomatis saat pemicu pada aturan fee tercapai (mis. PPJB ditandatangani)." />
  );

  return (
    <div data-testid={PARTNERS.profile} className="space-y-4">
      <EntityHeader kicker="Mitra & Fee" title={p.name}
        subtitle={`${p.code} · ${labelOf("partner_kind", p.partner_kind)} · `
          + `${labelOf("partner_entity_type", p.entity_type)}`}
        onBack={() => navigate("/partners")} backLabel="Daftar mitra"
        chips={[
          { label: "Status", value: <StatusPill status={p.status} group="agent_status" /> },
          { label: "Kontrak", value: data.contract_ok ? "berlaku" : (data.contract_note || "—") },
          { label: "Lead", value: `${stats.leads ?? 0}` },
          { label: "Sisa utang fee", value: <MoneyText value={stats.fee_outstanding} short /> },
        ]}
        actions={canManage ? (
          <>
            <Button data-testid={PARTNERS.editBtn} size="sm" variant="outline"
              onClick={() => setEditOpen(true)}>Ubah data</Button>
            <Button data-testid={PARTNERS.statusBtn} size="sm" variant="outline"
              onClick={() => setStatusOpen(true)}>Ubah status</Button>
          </>
        ) : null} />

      <TabPage testId={PARTNERS.profileTabs} tabs={[
        { key: "profil", label: "Profil & Kontrak", icon: Handshake, content: profileTab },
        { key: "aturan", label: "Aturan Fee", icon: ListChecks,
          content: <FeeRulesTab partnerId={p.id} /> },
        { key: "lead", label: `Lead (${(data.leads || []).length})`, icon: UserPlus,
          content: leadsTab },
        { key: "fee", label: `Tagihan Fee (${(data.fees || []).length})`, icon: Banknote,
          content: feesTab },
        { key: "analitik", label: "Kinerja", icon: TrendingUp,
          content: (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <KpiCard label="Survey hadir" value={m.survey_attended ?? 0}
                hint={m.qualified_pct !== null && m.qualified_pct !== undefined
                  ? `${m.qualified_pct}% dari lead` : "belum ada"} />
              <KpiCard label="Kontribusi pendapatan" value={<MoneyText value={m.revenue} short />}
                hint="nilai deal booking/selesai" />
              <KpiCard label="Biaya per closing" value={<MoneyText value={m.cost_per_won} short />}
                hint="Σ beban fee ÷ closing" />
              <KpiCard label="ROI" value={m.roi_pct === null || m.roi_pct === undefined
                ? "—" : `${m.roi_pct}%`} hint="(pendapatan − fee) ÷ fee" />
              <KpiCard label="Median hari ke closing" value={m.median_days_to_won ?? "—"}
                hint="dari lead masuk sampai won" />
              <KpiCard label="Fee menunggu persetujuan"
                value={<MoneyText value={m.fee_waiting} short />}
                hint="belum menjadi utang" />
            </div>
          ) },
        { key: "dokumen", label: "Dokumen Onboarding", icon: FileText,
          content: (
            <div className="space-y-3">
              <p className="rounded-xl border bg-card p-3 text-[13px] text-muted-foreground shadow-[var(--shadow-card)]">
                Checklist dokumen onboarding mitra (KTP/NPWP/PKS bertanda tangan) memakai
                mesin dokumen syarat yang sama dengan lead & pelanggan. Master syaratnya
                diatur admin di <b>Dokumen &amp; Perizinan → Master Dokumen Syarat</b> dengan
                objek <b>mitra</b>; bila belum ada syarat yang berlaku, daftar di bawah
                mengatakannya apa adanya.
              </p>
              <DocChecklist entityType="partner" entityId={id} onChanged={load} />
            </div>
          ) },
      ]} />

      <PartnerFormDialog partner={editOpen ? p : null} open={editOpen}
        onOpenChange={setEditOpen} onDone={load} />
      <PartnerStatusDialog partner={statusOpen ? p : null} open={statusOpen}
        onOpenChange={setStatusOpen} onDone={load} />
    </div>
  );
}
