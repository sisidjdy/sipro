import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Megaphone, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import CampaignFormDialog from "@/components/ads/CampaignFormDialog";
import { SourceLabels } from "@/components/ads/CostStatus";
import useListQuery from "@/hooks/useListQuery";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { ADS, DT } from "@/constants/testIds";

/**
 * CampaignsTab — master **kampanye** per platform (Fase 43 §4).
 *
 * Kenapa master ini wajib ada lebih dulu: baris biaya iklan hanya boleh masuk bila
 * kampanyenya sudah terdaftar. Tanpa aturan itu, satu kesalahan ketik nama kampanye pada
 * berkas CSV akan melahirkan “kampanye” baru yang tidak dimiliki siapa pun — biayanya masuk,
 * tetapi tidak pernah bertemu leadnya.
 */
export default function CampaignsTab() {
  const { options, labelOf } = useReference();
  const { can } = useAuth();
  // Izin EFEKTIF dari `GET /auth/me` — bukan daftar peran yang ditulis ulang di layar
  // (matriks RBAC bisa diubah admin lewat Pusat Konfigurasi).
  const canCreate = can("ads", "create");
  const canUpdate = can("ads", "update");
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: { platform: [], status: [], objective: [] },
    sort: "created_at", direction: "desc", limit: 25,
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [formFor, setFormFor] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/ads/campaigns", { params: apiParams });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar kampanye.");
    } finally { setLoading(false); }
  }, [apiParams]);

  useEffect(() => { load(); }, [load]);

  const columns = useMemo(() => [
    {
      key: "name", header: "Kampanye", sortable: true, width: "26%",
      render: (c) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-primary">{c.name}</p>
          <p className="text-xs text-muted-foreground">
            {c.code} · {c.external_id ? `ID platform ${c.external_id}` : "tanpa ID platform"}
          </p>
        </div>
      ),
      exportValue: (c) => `${c.code} ${c.name}`,
    },
    {
      key: "platform", header: "Platform", sortable: true,
      render: (c) => (
        <div>
          <p className="text-sm">{labelOf("ad_platform", c.platform)}</p>
          <p className="text-xs text-muted-foreground">
            {labelOf("campaign_objective", c.objective)}
          </p>
        </div>
      ),
      exportValue: (c) => labelOf("ad_platform", c.platform),
    },
    {
      key: "status", header: "Status", sortable: true,
      render: (c) => <StatusPill status={c.status} group="campaign_status" />,
    },
    {
      key: "start_date", header: "Periode", sortable: true,
      render: (c) => (
        <span className="text-xs text-muted-foreground">
          {(c.start_date || "—").slice(0, 10)} → {(c.end_date || "tanpa batas").slice(0, 10)}
        </span>
      ),
      exportValue: (c) => `${c.start_date || ""} - ${c.end_date || ""}`,
    },
    {
      key: "budget_total", header: "Anggaran", sortable: true, align: "right",
      render: (c) => (
        <div className="text-right">
          <MoneyText value={c.budget_total} short />
          <p className="text-xs text-muted-foreground">
            {c.budget_daily
              ? <>harian <MoneyText value={c.budget_daily} short /></>
              : "tanpa batas harian"}
          </p>
        </div>
      ),
      exportValue: (c) => c.budget_total || 0,
    },
    {
      key: "spend_range", header: "Biaya (rentang)", align: "right",
      render: (c) => (
        <div className="space-y-0.5 text-right">
          <MoneyText value={c.spend_range} short />
          <p className="text-xs text-muted-foreground">
            {c.spend_days ? `${c.spend_days} hari terisi` : "belum ada biaya"}
            {c.budget_used_pct !== null && c.budget_used_pct !== undefined
              ? ` · ${c.budget_used_pct}% anggaran` : ""}
          </p>
        </div>
      ),
      exportValue: (c) => c.spend_range || 0,
    },
    {
      key: "spend_sources", header: "Asal angka",
      render: (c) => <SourceLabels sources={c.spend_sources} />,
      exportValue: (c) => (c.spend_sources || []).join("|"),
    },
  ], [labelOf]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "platform", label: "Platform", type: "multiselect", options: options("ad_platform") },
      { key: "status", label: "Status", type: "multiselect",
        options: options("campaign_status")
          .map((o) => ({ ...o, hint: data?.counts?.[o.value] })) },
      { key: "objective", label: "Tujuan", type: "multiselect",
        options: options("campaign_objective") },
    ]} />
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Biaya iklan hanya bisa dicatat untuk kampanye yang terdaftar di sini. Isi
          <strong> ID platform</strong> bila tahu — nama kampanye bisa diganti kapan saja di
          Ads Manager, ID-nya tidak, jadi ID itulah yang membuat biaya &amp; lead tetap
          bertemu setelah nama berubah. Kolom “Biaya (rentang)” mengikuti rentang tanggal di
          tab Biaya Iklan (bawaan 30 hari terakhir).
        </p>
        {canCreate ? (
          <Button size="sm" data-testid={ADS.campaignAdd} onClick={() => setFormFor({})}>
            <Plus className="mr-1.5 h-4 w-4" /> Kampanye Baru
          </Button>
        ) : null}
      </div>

      <DataTable testId={ADS.campaignsTable}
        testIds={{ row: ADS.campaignRow, pagination: DT.pagination }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="kampanye" exportName="kampanye-iklan" onRefresh={load}
        searchPlaceholder="Cari nama / kode / ID platform…"
        onRowClick={(c) => canUpdate && setFormFor(c)}
        emptyTitle={activeCount || query.q ? "Tidak ada kampanye yang cocok"
          : "Belum ada kampanye terdaftar"}
        emptyDescription={activeCount || query.q
          ? "Longgarkan filter atau kosongkan pencarian."
          : "Daftarkan kampanye yang sedang berjalan di Meta/Google/TikTok supaya biayanya bisa dicatat dan CPL-nya bisa dihitung."}
        emptyActionLabel={activeCount || query.q ? "Reset filter"
          : (canCreate ? "Kampanye Baru" : "")}
        emptyAction={activeCount || query.q ? () => reset()
          : (canCreate ? () => setFormFor({}) : null)}
        emptyIcon={Megaphone} />

      <CampaignFormDialog campaign={formFor} open={!!formFor}
        onOpenChange={(v) => !v && setFormFor(null)} onDone={load} />
    </div>
  );
}
