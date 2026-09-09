import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { MessageSquarePlus, Upload, Users, Zap } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import WaContactsTable from "@/components/wa/WaContactsTable";
import WaImportPanel from "@/components/wa/WaImportPanel";
import WaCaptureDialog from "@/components/wa/WaCaptureDialog";
import WaSimulateInboundDialog from "@/components/wa/WaSimulateInboundDialog";
import WaQuickReplyDialog from "@/components/wa/WaQuickReplyDialog";
import api from "@/services/apiClient";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import { P94 } from "@/constants/testIds";

const KPIS = [
  { key: "new", label: "Menunggu diproses", tone: "text-sky-700" },
  { key: "dup_new", label: "Duplikat lead (perlu keputusan)", tone: "text-amber-700" },
  { key: "captured", label: "Jadi lead baru", tone: "text-emerald-700" },
  { key: "linked", label: "Ditautkan ke lead lama", tone: "text-teal-700" },
  { key: "skipped", label: "Dilewati", tone: "text-zinc-600" },
  { key: "invalid", label: "Nomor tidak valid", tone: "text-rose-700" },
];

/**
 * WaCapturePage — antrean kontak WhatsApp → lead (Fase 95).
 * Kontak datang dari webhook Meta (pesan masuk), impor manual (tempel/CSV/VCF), atau Inbox.
 * Setiap kontak dicocokkan ke lead & customer per nomor E.164; keputusan duplikat di tangan
 * pemakai (lewati / tautkan / buat ulang untuk customer lama).
 */
export default function WaCapturePage() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "import" ? "import" : "queue";
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ status: "new", q: "", dup: "" });
  const [captureFor, setCaptureFor] = useState(null);
  const [simOpen, setSimOpen] = useState(false);
  const [replyFor, setReplyFor] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/wa/contacts", { params: { ...filters, limit: 200 } });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat kontak WhatsApp.");
    } finally { setLoading(false); }
  }, [filters]);
  useEffect(() => { load(); }, [load, refreshKey]);

  const counts = useMemo(() => ({ ...(data?.counts || {}), dup_new: data?.dup_new || 0 }), [data]);
  const setTab = (v) => { const n = new URLSearchParams(); n.set("tab", v); setParams(n); };
  const canCreate = can("leads", "create");
  const canReply = can("inbox", "create");

  return (
    <div data-testid={P94.page} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">Kontak WA → Lead</h1>
          <p className="page-desc">
            Nomor yang masuk lewat WhatsApp (webhook Meta) atau diimpor dari kontak HP — periksa
            duplikat dengan lead/customer lama, lalu jadikan lead satu per satu, sebagian, atau semua.
          </p>
        </div>
        <div className="flex gap-2">
          <Button data-testid={P94.simulateBtn} variant="outline" size="sm" onClick={() => setSimOpen(true)}>
            <Zap className="mr-1.5 h-4 w-4" /> Simulasi pesan masuk
          </Button>
          <Button variant="outline" size="sm" onClick={() => setTab("import")}>
            <Upload className="mr-1.5 h-4 w-4" /> Impor kontak
          </Button>
          {canCreate ? (
            <Button data-testid={P94.captureAllBtn} size="sm" disabled={!counts.new}
              onClick={() => setCaptureFor({ all_new: true, count: counts.new })}>
              <MessageSquarePlus className="mr-1.5 h-4 w-4" /> Jadikan lead semua ({counts.new || 0})
            </Button>
          ) : null}
        </div>
      </div>

      <div data-testid={P94.kpi} className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {KPIS.map((k) => (
          <button key={k.key} type="button"
            onClick={() => { setTab("queue"); setFilters((f) => ({ ...f, status: k.key === "dup_new" ? "new" : k.key, dup: k.key === "dup_new" ? "lead" : "" })); }}
            className={cn("rounded-xl border bg-card p-3 text-left shadow-[var(--shadow-card)] transition-colors hover:bg-secondary",
              (filters.status === k.key && !filters.dup) || (k.key === "dup_new" && filters.dup === "lead") ? "border-primary" : "")}>
            <p className="text-xs text-muted-foreground">{k.label}</p>
            <p className={cn("mt-1 text-2xl font-semibold tabular-nums", k.tone)}>{counts[k.key] ?? 0}</p>
          </button>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab} className="space-y-4">
        <TabsList>
          <TabsTrigger data-testid={P94.tabQueue} value="queue"><Users className="mr-1.5 h-4 w-4" /> Antrean kontak</TabsTrigger>
          <TabsTrigger data-testid={P94.tabImport} value="import"><Upload className="mr-1.5 h-4 w-4" /> Impor kontak</TabsTrigger>
        </TabsList>
        <TabsContent value="queue">
          <WaContactsTable rows={data?.data || []} total={data?.total || 0} loading={loading} error={error}
            filters={filters} onFilters={setFilters} onRefresh={load} canCreate={canCreate} canReply={canReply}
            onReply={setReplyFor}
            onCapture={(rows) => setCaptureFor({ ids: rows.map((r) => r.id), rows, count: rows.length })}
            onOpenLead={(id) => navigate(`/leads/${id}`)} />
        </TabsContent>
        <TabsContent value="import">
          <WaImportPanel onImported={() => { setRefreshKey((k) => k + 1); setTab("queue"); setFilters({ status: "new", q: "", dup: "" }); toast.success("Kontak masuk antrean. Periksa duplikat lalu jadikan lead."); }} />
        </TabsContent>
      </Tabs>

      <WaCaptureDialog open={!!captureFor} onOpenChange={(v) => !v && setCaptureFor(null)}
        target={captureFor} onDone={() => { setCaptureFor(null); load(); }} />
      <WaSimulateInboundDialog open={simOpen} onOpenChange={setSimOpen} onDone={load} />
      <WaQuickReplyDialog contact={replyFor} onOpenChange={(v) => !v && setReplyFor(null)} onDone={load} />
    </div>
  );
}
