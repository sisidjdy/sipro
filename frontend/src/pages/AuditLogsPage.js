import React, { useCallback, useEffect, useState } from "react";
import { History, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import MigrationRunsPanel from "@/components/master/MigrationRunsPanel";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { AUDIT } from "@/constants/testIds";

const ALL = "__all__";

/**
 * Jejak Audit — sebelumnya audit_log() menulis ke koleksi `audit_logs` tetapi TIDAK ADA
 * endpoint maupun halaman untuk melihatnya, jadi jejak persetujuan/perubahan tidak bisa diaudit.
 */
export default function AuditLogsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [resource, setResource] = useState(ALL);
  const [action, setAction] = useState(ALL);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = { limit: 100 };
      if (resource !== ALL) params.resource = resource;
      if (action !== ALL) params.action = action;
      const r = await api.get("/admin/audit-logs", { params });
      setData(r.data);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat jejak audit."); }
    finally { setLoading(false); }
  }, [resource, action]);
  useEffect(() => { load(); }, [load]);

  const rows = data?.data || [];
  const resources = data?.filters?.resources || [];
  const actions = data?.filters?.actions || [];

  return (
    <div data-testid={AUDIT.page} className="space-y-5">
      <div className="flex items-center gap-2">
        <History className="h-5 w-5 text-primary" />
        <h1 className="page-title">Jejak Audit</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        Riwayat aksi sensitif: pembuatan/perubahan pengguna & hak akses, persetujuan PO,
        perubahan master data, penanganan komplain.
      </p>

      {/* Fase 39b — riwayat migrasi/backfill data V2 (dulu hanya ada di koleksi
          `migration_runs` tanpa layar mana pun): bukti US-39-5 bisa diperiksa admin. */}
      <MigrationRunsPanel />

      <div className="flex flex-wrap items-end gap-3">
        <div className="w-48 space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Objek</p>
          <Select value={resource} onValueChange={setResource}>
            <SelectTrigger data-testid={AUDIT.filterResource}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Semua objek</SelectItem>
              {resources.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="w-48 space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Aksi</p>
          <Select value={action} onValueChange={setAction}>
            <SelectTrigger data-testid={AUDIT.filterAction}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Semua aksi</SelectItem>
              {actions.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <Button data-testid={AUDIT.refresh} size="sm" variant="outline" onClick={load}>
          <RefreshCw className="mr-1.5 h-4 w-4" /> Muat ulang
        </Button>
      </div>

      {loading ? <LoadingCards count={4} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !rows.length ? (
          <EmptyState icon={History} title="Belum ada jejak audit"
            description="Jejak akan muncul setelah ada aksi sensitif (mis. menyetujui PO, mengubah hak akses, mengubah master data)." />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Waktu</TableHead><TableHead>Pelaku</TableHead><TableHead>Peran</TableHead>
                <TableHead>Aksi</TableHead><TableHead>Objek</TableHead><TableHead>Detail</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.id} data-testid={AUDIT.row}>
                    <TableCell className="whitespace-nowrap text-xs">{formatDateTimeWIB(r.created_at)}</TableCell>
                    <TableCell className="text-sm">{r.actor}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{r.actor_role}</TableCell>
                    <TableCell className="text-sm font-medium">{r.action}</TableCell>
                    <TableCell className="text-sm">
                      {r.resource}
                      {r.entity_id ? (
                        <span className="ml-1 font-mono text-[11px] text-muted-foreground">
                          {String(r.entity_id).slice(0, 8)}
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell className="max-w-[280px] truncate text-xs text-muted-foreground"
                      title={r.meta && Object.keys(r.meta).length
                        ? JSON.stringify(r.meta, null, 1) : undefined}>
                      {r.meta && Object.keys(r.meta).length ? JSON.stringify(r.meta) : "-"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      <p className="text-xs text-muted-foreground">Menampilkan {rows.length} dari {data?.total || 0} entri.</p>
    </div>
  );
}
