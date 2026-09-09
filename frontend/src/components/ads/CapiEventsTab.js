import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import KpiCard from "@/components/patterns/KpiCard";
import MoneyText from "@/components/patterns/MoneyText";
import StatusPill from "@/components/patterns/StatusPill";
import useListQuery from "@/hooks/useListQuery";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import { formatDateTimeWIB, formatNumber } from "@/utils/formatters";
import api from "@/services/apiClient";
import { ADS, DT } from "@/constants/testIds";

/**
 * CapiEventsTab — audit **event konversi** yang dikirim balik ke platform iklan (Fase 43 §6).
 *
 * Yang membuat layar ini bisa dipercaya:
 *  — Status `Dicatat (simulasi, belum dikirim)` dipisahkan dari `Terkirim`. Sebelum fase ini
 *    semua baris berstatus “Terkirim” padahal tanpa kredensial tidak ada satu paket pun yang
 *    keluar dari server.
 *  — `event_id` (kunci dedup platform) ditampilkan: peristiwa bisnis yang sama tidak boleh
 *    menghasilkan dua konversi, dan di sini bisa dibuktikan.
 *  — Identitas pembeli hanya tampil sebagai potongan HASH SHA-256 — payloadnya sudah berbentuk
 *    siap-live, tetapi nomor/email mentah tidak pernah dikirim ke browser.
 */
export default function CapiEventsTab() {
  const { options } = useReference();
  const { can } = useAuth();
  const canManage = can("ads", "manage");
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: { event: [], status: [], transport: [] },
    sort: "", direction: "desc", limit: 25,
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/ads/capi/events", { params: apiParams });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat event konversi.");
    } finally { setLoading(false); }
  }, [apiParams]);

  useEffect(() => { load(); }, [load]);

  const resend = async (row) => {
    setBusyId(row.id);
    try {
      const res = await api.post(`/ads/capi/events/${row.id}/resend`);
      toast.success(`Status event sekarang: ${res.data.data?.status}.`);
      load();
    } catch (e) {
      // Di mode simulasi server menolak 400 dengan alasan lengkap (env mana yang kosong).
      toast.error(e?.response?.data?.detail || "Gagal mengirim ulang event.",
        { duration: 9000 });
    } finally { setBusyId(null); }
  };

  const s = data?.summary || {};
  const columns = useMemo(() => [
    {
      key: "created_at", header: "Waktu", width: "14%",
      render: (r) => (
        <span className="text-xs text-muted-foreground">{formatDateTimeWIB(r.created_at)}</span>
      ),
      exportValue: (r) => r.created_at,
    },
    {
      key: "event_name", header: "Event",
      render: (r) => (
        <div>
          <StatusPill status={r.event_name} group="capi_event_name" />
          <p className="mt-0.5 text-xs text-muted-foreground">{r.platform_label}</p>
        </div>
      ),
      exportValue: (r) => r.event_name,
    },
    {
      key: "campaign", header: "Kampanye / atribusi", width: "20%",
      render: (r) => (
        <div className="min-w-0">
          <p className="truncate text-sm">{r.campaign || "(tanpa kampanye)"}</p>
          <p className="truncate text-xs text-muted-foreground">
            {[r.campaign_id && `kampanye ${r.campaign_id}`, r.adset_id && `adset ${r.adset_id}`,
              r.ad_id && `iklan ${r.ad_id}`].filter(Boolean).join(" · ") || "tanpa ID platform"}
          </p>
        </div>
      ),
      exportValue: (r) => r.campaign || "",
    },
    {
      key: "value", header: "Nilai", align: "right",
      render: (r) => <MoneyText value={r.value} short />,
      exportValue: (r) => r.value || 0,
    },
    {
      key: "transport", header: "Transport",
      render: (r) => <StatusPill status={r.transport} group="integration_mode"
        tone={r.transport === "live" ? "active" : "simulation"} />,
      exportValue: (r) => r.transport,
    },
    {
      key: "status", header: "Status kirim",
      render: (r) => (
        <div>
          <StatusPill status={r.status} group="capi_status"
            tone={r.status === "failed" ? "rejected" : (r.status === "sent" ? "paid" : "pending")} />
          {r.attempts ? (
            <p className="mt-0.5 text-xs text-muted-foreground">{r.attempts}× dicoba</p>
          ) : null}
        </div>
      ),
      exportValue: (r) => r.status,
    },
    {
      key: "event_id", header: "ID dedup & identitas", hidden: true,
      render: (r) => (
        <div className="font-mono text-[11px] text-muted-foreground">
          <p>{String(r.event_id || "—").slice(0, 16)}…</p>
          <p>{Object.entries(r.user_data_preview || {})
            .map(([k, v]) => `${k}:${v}`).join(" ") || "tanpa identitas"}</p>
        </div>
      ),
      exportValue: (r) => r.event_id || "",
    },
    {
      key: "message", header: "Keterangan", width: "22%",
      render: (r) => (
        <span className="text-xs text-muted-foreground">{r.message || "—"}</span>
      ),
      exportValue: (r) => r.message || "",
    },
    {
      key: "actions", header: "", sticky: true,
      render: (r) => (canManage ? (
        <Button size="sm" variant="outline" data-testid={ADS.capiResend} data-event={r.id}
          aria-label={`Kirim ulang event ${r.event_name}`} disabled={busyId === r.id}
          onClick={(e) => { e.stopPropagation(); resend(r); }}>
          <Send className="h-3.5 w-3.5" />
        </Button>
      ) : null),
      exportValue: () => "",
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [canManage, busyId]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "event", label: "Event", type: "multiselect", options: options("capi_event_name") },
      { key: "status", label: "Status kirim", type: "multiselect", options: options("capi_status") },
      { key: "transport", label: "Transport", type: "multiselect",
        options: options("integration_mode") },
    ]} />
  );

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Setiap peristiwa nyata (lead masuk → SPR ditandatangani → booking → AJB) menghasilkan
        satu event konversi dengan <code>event_id</code> tetap, sehingga platform tidak pernah
        menghitungnya dua kali walau pengiriman diulang.
      </p>

      <div data-testid={ADS.capiSummary} className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard label="Total event" value={formatNumber(s.total || 0)} />
        <KpiCard label="Terkirim" value={formatNumber(s.by_status?.sent || 0)} tone="emerald" />
        <KpiCard label="Simulasi (belum dikirim)"
          value={formatNumber(s.by_status?.simulated || 0)} tone="amber"
          hint="menunggu kredensial platform" />
        <KpiCard label="Gagal" value={formatNumber(s.by_status?.failed || 0)} tone="rose" />
        <KpiCard label="Nilai konversi" value={<MoneyText value={s.value_total} short />}
          tone="sky" />
      </div>

      <DataTable testId={ADS.capiTable}
        testIds={{ row: ADS.capiRow, pagination: DT.pagination }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="event" exportName="event-capi" onRefresh={load}
        searchPlaceholder=""
        emptyTitle={activeCount ? "Tidak ada event yang cocok" : "Belum ada event konversi"}
        emptyDescription={activeCount
          ? "Longgarkan filternya."
          : "Event lahir otomatis dari peristiwa nyata: lead beratribusi iklan masuk, SPR ditandatangani, booking, atau AJB."}
        emptyActionLabel={activeCount ? "Reset filter" : ""}
        emptyAction={activeCount ? () => reset() : null} />
    </div>
  );
}
