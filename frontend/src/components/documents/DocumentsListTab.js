import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Download, PenLine, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import StatusPill from "@/components/patterns/StatusPill";
import useListQuery from "@/hooks/useListQuery";
import { useReference } from "@/context/ReferenceContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import { slaFilter } from "@/utils/agingFilter";
import api from "@/services/apiClient";
import { CreateSprDialog, SignDialog } from "@/components/documents/DocumentDialogs";
import { DOCS } from "@/constants/testIds";

/**
 * DocumentsListTab — daftar dokumen (SPR/PPJB/AJB) sebagai tabel pro.
 * Aksi lama dipertahankan penuh: Finalisasi · Tandatangani · Unduh PDF · Buat SPR.
 */
export default function DocumentsListTab() {
  const { options } = useReference();
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: { status: [], template_code: [], created_from: "", created_to: "", sla: "" },
    sort: "created_at", direction: "desc", limit: 25,
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [signDoc, setSignDoc] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/documents", { params: apiParams });
      setData(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat dokumen.");
    } finally { setLoading(false); }
  }, [apiParams]);

  useEffect(() => { load(); }, [load]);

  const finalize = async (doc) => {
    setBusyId(doc.id);
    try {
      await api.post(`/documents/${doc.id}/finalize`);
      toast.success("Dokumen difinalisasi.");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal."); }
    finally { setBusyId(null); }
  };

  const download = async (doc) => {
    setBusyId(doc.id);
    try {
      const res = await api.get(`/documents/${doc.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (e) { toast.error("Gagal mengunduh PDF."); }
    finally { setBusyId(null); }
  };

  const columns = useMemo(() => [
    {
      key: "doc_number", header: "Nomor", sortable: true,
      render: (d) => <span className="font-mono text-xs">{d.doc_number}</span>,
    },
    {
      key: "title", header: "Judul", sortable: true,
      render: (d) => <span className="font-medium">{d.title}</span>,
    },
    { key: "template_code", header: "Template", sortable: true },
    {
      key: "status", header: "Status", sortable: true,
      render: (d) => <StatusPill status={d.status} group="document_status" />,
    },
    {
      key: "signatures", header: "Tanda tangan", align: "right",
      render: (d) => <span className="tabular-nums">{(d.signatures || []).length}</span>,
      exportValue: (d) => (d.signatures || []).length,
    },
    {
      key: "created_at", header: "Dibuat", sortable: true,
      render: (d) => <span className="text-xs text-muted-foreground">
        {formatDateTimeWIB(d.created_at)}
      </span>,
    },
    {
      key: "aksi", header: "Aksi", align: "right", sticky: true,
      render: (d) => (
        <div className="flex flex-wrap justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          {d.status === "draft" ? (
            <Button data-testid={DOCS.finalizeBtn} size="sm" disabled={busyId === d.id}
              onClick={() => finalize(d)}>
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Finalisasi
            </Button>
          ) : null}
          {["finalized", "signed"].includes(d.status) ? (
            <Button data-testid={DOCS.signBtn} size="sm" variant="outline" disabled={busyId === d.id}
              onClick={() => setSignDoc(d)}>
              <PenLine className="mr-1 h-3.5 w-3.5" /> Tandatangani
            </Button>
          ) : null}
          <Button data-testid={DOCS.downloadBtn} size="sm" variant="ghost" disabled={busyId === d.id}
            onClick={() => download(d)}>
            <Download className="mr-1 h-3.5 w-3.5" /> PDF
          </Button>
        </div>
      ),
      exportValue: () => "",
    },
  ], [busyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "status", label: "Status", type: "multiselect",
        options: options("document_status").map((o) => ({ ...o, hint: data?.counts?.[o.value] })) },
      { key: "template_code", label: "Template", type: "multiselect",
        options: options("document_template") },
      slaFilter(options("sla_state")),
      { key: "created", label: "Dibuat", type: "daterange",
        fromKey: "created_from", toKey: "created_to" },
    ]} />
  );

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button size="sm" data-testid={DOCS.createBtn} onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Buat SPR
        </Button>
      </div>
      <DataTable testId={DOCS.table} testIds={{ row: DOCS.row }}
        columns={columns} rows={data?.data || []} total={data?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="dokumen" exportName="dokumen" onRefresh={load}
        searchPlaceholder="Cari nomor / judul / template…"
        emptyTitle={activeCount || query.q ? "Tidak ada dokumen yang cocok" : "Belum ada dokumen"}
        emptyDescription={activeCount || query.q
          ? "Longgarkan filter atau kosongkan pencarian."
          : "Buat SPR dari deal yang sudah reserved/booked, lalu finalisasi, tandatangani, dan unduh PDF."}
        emptyActionLabel={activeCount || query.q ? "Reset filter" : "Buat SPR"}
        emptyAction={() => (activeCount || query.q ? reset() : setCreateOpen(true))} />
      <CreateSprDialog open={createOpen} onOpenChange={setCreateOpen} onDone={load} />
      <SignDialog doc={signDoc} onOpenChange={(v) => !v && setSignDoc(null)} onDone={load} />
    </div>
  );
}
