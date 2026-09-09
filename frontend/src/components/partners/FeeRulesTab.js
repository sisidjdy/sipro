import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Calculator, Plus, Power } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import FeeRuleFormDialog from "@/components/partners/FeeRuleFormDialog";
import FeePreviewDialog from "@/components/partners/FeePreviewDialog";
import useListQuery from "@/hooks/useListQuery";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { PARTNERS, DT } from "@/constants/testIds";

/** Ringkasan isi aturan dalam satu kalimat yang bisa dibaca orang keuangan. */
function ruleSummary(rule, labelOf) {
  const base = labelOf("partner_fee_basis", rule.basis) || rule.basis;
  if (rule.basis === "percent_price") {
    return `${rule.value}% × ${labelOf("partner_price_base", rule.price_base) || "harga jual"}`;
  }
  if (rule.basis === "fixed_per_deal") return `${base}: Rp ${Number(rule.value).toLocaleString("id-ID")}`;
  if (rule.basis === "fixed_per_unit_type") {
    return `${base}: ${Object.keys(rule.by_unit_type || {}).length} tipe unit`;
  }
  if (rule.basis === "tier_volume" || rule.basis === "tier_value") {
    return `${base}: ${(rule.tiers || []).length} tingkat · periode `
      + `${labelOf("partner_fee_period", rule.period) || rule.period}`;
  }
  if (rule.basis === "per_lead_qualified") {
    return `Rp ${Number(rule.value).toLocaleString("id-ID")}/lead · `
      + `${labelOf("partner_qualify_rule", rule.qualify_rule) || "survey hadir"}`;
  }
  if (rule.basis === "hybrid") return `${base}: ${(rule.components || []).length} komponen`;
  return base;
}

/**
 * FeeRulesTab — **Aturan Fee** mitra (Fase 42 §3, keputusan pemilik D5: semua skema tersedia).
 *
 * Kenapa layar ini penting: sebelum Fase 42 nominal fee diketik manual per pengajuan, jadi
 * tidak ada yang bisa membuktikan bahwa angka yang dibayar = angka yang dijanjikan di
 * kontrak mitra. Sekarang aturan disimpan, dipilih otomatis (paling spesifik menang), dan
 * setiap tagihan menyebut aturan penerbitnya. Tombol "Pratinjau" memakai mesin yang sama
 * dengan pemicu otomatis — jadi yang terlihat = yang akan dibukukan.
 */
export default function FeeRulesTab({ partnerId = null }) {
  const { labelOf, options } = useReference();
  const { can } = useAuth();
  // Izin diambil dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis
  // ulang di layar. Matriks RBAC bisa diubah admin lewat Pusat Konfigurasi; daftar peran
  // hardcode membuat tombol berbeda dengan jawaban server — tombol mati (403) atau
  // tombol yang seharusnya ada tapi hilang.
  const canManage = can("partners", "update");
  const { query, setQuery, reset, activeCount } = useListQuery({
    filters: { status: [], basis: [] }, sort: "created_at", direction: "desc", limit: 25,
  });
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [formFor, setFormFor] = useState(null);
  const [previewFor, setPreviewFor] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/partners/rules", {
        params: partnerId ? { partner_id: partnerId } : {},
      });
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat aturan fee.");
    } finally { setLoading(false); }
  }, [partnerId]);

  useEffect(() => { load(); }, [load]);

  const toggleStatus = async (rule) => {
    setBusyId(rule.id);
    try {
      const next = rule.status === "active" ? "inactive" : "active";
      await api.put(`/partners/rules/${rule.id}`, { status: next });
      toast.success(next === "active" ? "Aturan diaktifkan." : "Aturan dinonaktifkan.");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengubah status aturan.");
    } finally { setBusyId(null); }
  };

  const filtered = useMemo(() => {
    let out = rows;
    if ((query.status || []).length) out = out.filter((r) => query.status.includes(r.status));
    if ((query.basis || []).length) out = out.filter((r) => query.basis.includes(r.basis));
    if (query.q) {
      const q = query.q.toLowerCase();
      out = out.filter((r) => `${r.name} ${r.code} ${r.partner_name}`.toLowerCase().includes(q));
    }
    return out;
  }, [rows, query]);

  const columns = useMemo(() => [
    {
      key: "name", header: "Aturan", sortable: true, width: "28%",
      render: (r) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-primary">{r.name}</p>
          <p className="text-xs text-muted-foreground">{r.code} · {ruleSummary(r, labelOf)}</p>
        </div>
      ),
      exportValue: (r) => `${r.code} ${r.name}`,
    },
    {
      key: "partner_name", header: "Berlaku untuk", sortable: true,
      render: (r) => (
        <div>
          <p className="text-sm">{r.partner_name}</p>
          <p className="text-xs text-muted-foreground">
            {r.scope?.project_id ? "proyek tertentu" : "semua proyek"}
            {r.scope?.unit_type ? ` · tipe ${r.scope.unit_type}` : ""}
            {" · prioritas "}{r.specificity}
          </p>
        </div>
      ),
      exportValue: (r) => r.partner_name,
    },
    {
      key: "trigger", header: "Pemicu & porsi",
      render: (r) => ((r.splits || []).length ? (
        <div className="space-y-0.5">
          {r.splits.map((s) => (
            <p key={s.trigger} className="text-xs" data-split={s.trigger}>
              {labelOf("partner_fee_trigger", s.trigger) || s.trigger}: <strong>{s.pct}%</strong>
            </p>
          ))}
        </div>
      ) : (
        <span className="text-sm">
          {labelOf("partner_fee_trigger", r.trigger) || r.trigger} · 100%
        </span>
      )),
      exportValue: (r) => (r.splits || []).map((s) => `${s.trigger} ${s.pct}%`).join(" | ")
        || r.trigger,
    },
    {
      key: "tax", header: "PPh",
      render: (r) => (
        <span className="text-xs text-muted-foreground">
          {r.tax?.pph_type ? `${r.tax.pph_type}${r.tax?.rate ? ` ${r.tax.rate}%` : " (tarif config)"}`
            : "ikut bentuk badan mitra"}
          {r.tax?.gross_up ? " · gross-up" : ""}
        </span>
      ),
      exportValue: (r) => r.tax?.pph_type || "auto",
    },
    {
      key: "valid", header: "Masa berlaku",
      render: (r) => (
        <span className="text-xs text-muted-foreground">
          {(r.valid_from || "—").slice(0, 10)} → {(r.valid_to || "tanpa batas").slice(0, 10)}
        </span>
      ),
      exportValue: (r) => `${r.valid_from || ""} - ${r.valid_to || ""}`,
    },
    {
      key: "fee_count", header: "Tagihan terbit", align: "right",
      render: (r) => <span className="text-sm tabular-nums">{r.fee_count || 0}</span>,
      exportValue: (r) => r.fee_count || 0,
    },
    {
      key: "status", header: "Status", sortable: true,
      render: (r) => <StatusPill status={r.status} group="partner_rule_status" />,
    },
    {
      key: "actions", header: "", sticky: true,
      render: (r) => (canManage ? (
        <div className="flex justify-end gap-1.5">
          <Button size="sm" variant="outline" data-testid={PARTNERS.ruleToggle} data-rule={r.id}
            aria-label={`${r.status === "active" ? "Nonaktifkan" : "Aktifkan"} aturan ${r.code}`}
            disabled={busyId === r.id}
            onClick={(e) => { e.stopPropagation(); toggleStatus(r); }}>
            <Power className="h-3.5 w-3.5" />
          </Button>
        </div>
      ) : null),
      exportValue: () => "",
    },
  ], [labelOf, canManage, busyId]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "status", label: "Status", type: "multiselect",
        options: options("partner_rule_status") },
      { key: "basis", label: "Dasar fee", type: "multiselect",
        options: options("partner_fee_basis") },
    ]} />
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Fee mitra lahir dari ATURAN, bukan angka yang diketik saat menagih. Bila dua aturan
          sama-sama berlaku dan sama spesifik, sistem MENOLAK dan meminta cakupannya
          dipersempit — supaya mitra tidak pernah ditagihkan angka yang bukan haknya.
        </p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" data-testid={PARTNERS.previewBtn}
            onClick={() => setPreviewFor({ partnerId })}>
            <Calculator className="mr-1.5 h-4 w-4" /> Pratinjau perhitungan
          </Button>
          {canManage ? (
            <Button size="sm" data-testid={PARTNERS.ruleAddBtn}
              onClick={() => setFormFor({ partner_id: partnerId || null })}>
              <Plus className="mr-1.5 h-4 w-4" /> Aturan Fee
            </Button>
          ) : null}
        </div>
      </div>

      <DataTable testId={PARTNERS.rulesTable}
        testIds={{ row: PARTNERS.ruleRow, pagination: DT.pagination }}
        columns={columns} rows={filtered} total={filtered.length}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="aturan fee" exportName="aturan-fee-mitra" onRefresh={load}
        searchPlaceholder="Cari nama / kode aturan / mitra…"
        onRowClick={(r) => canManage && setFormFor(r)}
        emptyTitle={activeCount || query.q ? "Tidak ada aturan yang cocok"
          : "Belum ada aturan fee"}
        emptyDescription={activeCount || query.q
          ? "Longgarkan filter atau kosongkan pencarian."
          : "Tanpa aturan fee, tidak ada tagihan fee yang bisa diterbitkan (INV-09)."}
        emptyActionLabel={canManage && !activeCount ? "Buat aturan fee" : ""}
        emptyAction={canManage && !activeCount
          ? () => setFormFor({ partner_id: partnerId || null }) : null} />

      <FeeRuleFormDialog rule={formFor} open={!!formFor}
        onOpenChange={(v) => !v && setFormFor(null)} onDone={load} />
      <FeePreviewDialog context={previewFor} open={!!previewFor}
        onOpenChange={(v) => !v && setPreviewFor(null)} onDone={load} />
    </div>
  );
}
