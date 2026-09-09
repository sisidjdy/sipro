import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Eye, Pencil, Plus, RefreshCw, Trash2, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import StatusPill from "@/components/patterns/StatusPill";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import WaTemplateEditorDialog from "@/components/config/WaTemplateEditorDialog";
import WaReminderMappingCard from "@/components/config/WaReminderMappingCard";
import { formatDateTimeWIB } from "@/utils/formatters";
import { useReference } from "@/context/ReferenceContext";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { P97 } from "@/constants/testIds";

const TONE = { APPROVED: "approved", REJECTED: "failed", PENDING: "pending", NOT_SUBMITTED: "simulation", PAUSED: "failed", DISABLED: "failed" };

/**
 * SATU layar template WA (audit WA-14 / K-1): isi, variabel + contoh, kategori, status Meta,
 * pengajuan, di mana dipakai, dan pemetaan pengingat. Layar Lead WA hanya memilih.
 */
export default function WaTemplateMetaPanel() {
  const { labelOf } = useReference();
  const { can } = useAuth();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState(null);
  const [editing, setEditing] = useState(undefined); // undefined=tutup, null=baru, obj=ubah
  const [killRow, setKillRow] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const canManage = can("wa_templates", "manage");

  const load = useCallback(() => {
    setError("");
    api.get("/wa-templates").then((r) => { setRows(r.data.data || []); setRefreshKey((k) => k + 1); })
      .catch((e) => setError(e?.response?.data?.detail || "Gagal memuat template."));
  }, []);
  useEffect(() => { load(); }, [load]);

  const sync = async () => {
    setBusy("sync");
    try { const r = await api.post("/wa-templates/sync"); toast.success(`Sinkron Meta: ${r.data.data.matched} template diperbarui, ${r.data.data.approved} APPROVED.`); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Sinkron gagal."); }
    finally { setBusy(""); }
  };
  const submit = async (t) => {
    setBusy(t.id);
    try { await api.post(`/wa-templates/${t.id}/submit`); toast.success("Template diajukan ke Meta (PENDING)."); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Pengajuan gagal.", { duration: 9000 }); }
    finally { setBusy(""); }
  };
  const openPreview = async (t) => {
    try { const r = await api.get(`/wa-templates/${t.id}/meta-preview`); setPreview({ t, payload: r.data.data }); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal memuat pratinjau."); }
  };
  const remove = async () => {
    try { await api.delete(`/wa-templates/${killRow.id}`); toast.success(`Template ${killRow.name} dihapus.`); setKillRow(null); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghapus template.", { duration: 10000 }); setKillRow(null); }
  };

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!rows) return <LoadingCards count={2} />;
  return (
    <div className="space-y-4" data-testid={P97.tmplMetaPanel}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="max-w-3xl text-sm text-muted-foreground">
          Satu tempat untuk seluruh template WhatsApp: isi & variabel, contoh nilai, kategori, pengajuan dan status resmi Meta,
          serta template mana yang dipakai pengingat/playbook. Template yang sudah <b>APPROVED</b> di Meta dibekukan; ubah isi = template baru.
        </p>
        <div className="flex gap-1.5">
          {canManage ? (
            <Button data-testid={P97.tmplSyncBtn} size="sm" variant="outline" onClick={sync} disabled={busy === "sync"}>
              <RefreshCw className="mr-1.5 h-4 w-4" /> {busy === "sync" ? "Menyinkron…" : "Tarik status dari Meta"}
            </Button>
          ) : null}
          {canManage ? (
            <Button data-testid={P97.tmplNewBtn} size="sm" onClick={() => setEditing(null)}>
              <Plus className="mr-1.5 h-4 w-4" /> Template baru
            </Button>
          ) : null}
        </div>
      </div>
      <div data-testid={P97.tmplStudio} className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
        <Table>
          <TableHeader><TableRow><TableHead>Template & isi</TableHead><TableHead>Kategori</TableHead><TableHead>Status Meta</TableHead><TableHead>Dipakai gateway</TableHead><TableHead>Dipakai oleh</TableHead><TableHead className="text-right">Aksi</TableHead></TableRow></TableHeader>
          <TableBody>
            {rows.map((t) => (
              <TableRow key={t.id} data-testid={P97.tmplMetaRow} data-code={t.code}>
                <TableCell className="max-w-[26rem] align-top">
                  <p className="font-medium">{t.name}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">{t.meta_name || t.code} · {t.language}</p>
                  <p className="mt-1 line-clamp-3 whitespace-pre-line text-xs text-secondary-foreground">{t.body}</p>
                  {(t.variables || []).length ? (
                    <p className="mt-1 flex flex-wrap gap-1">
                      {t.variables.map((v) => (
                        <span key={v} className={`rounded px-1 py-0.5 font-mono text-[10px] ${t.examples?.[v] ? "bg-secondary" : "bg-amber-50 text-amber-800"}`} title={t.examples?.[v] ? `contoh: ${t.examples[v]}` : "belum ada contoh nilai (memakai bawaan bila dikenal)"}>
                          {"{{" + v + "}}"}
                        </span>
                      ))}
                    </p>
                  ) : null}
                  {(t.hints || []).map((h) => <p key={h} data-testid={P97.tmplHint} className="mt-1 text-[11px] text-amber-700">{h}</p>)}
                </TableCell>
                <TableCell className="align-top text-xs">{labelOf("wa_template_category", t.category)}
                  {t.header_type && t.header_type !== "none" ? <span data-testid={P97.tmplHeaderBadge} className="ml-1 rounded bg-secondary px-1.5 py-0.5 text-[10px]">header: {labelOf("wa_template_header", t.header_type)}</span> : null}
                </TableCell>
                <TableCell data-testid={P97.tmplMetaStatus} className="align-top">
                  <StatusPill status={TONE[t.meta_status] || "pending"} label={labelOf("wa_meta_template_status", t.meta_status || "NOT_SUBMITTED")} />
                  {t.meta_reason ? <p className="mt-0.5 text-[11px] text-rose-600">{t.meta_reason}</p> : null}
                  {t.meta_synced_at ? <p className="mt-0.5 text-[10px] text-muted-foreground">sinkron {formatDateTimeWIB(t.meta_synced_at)}</p> : null}
                </TableCell>
                <TableCell className="align-top"><StatusPill status={t.status} group="wa_template_status" /></TableCell>
                <TableCell data-testid={P97.tmplUsedBy} className="max-w-[14rem] align-top text-[11px]">
                  {(t.used_by || []).length ? t.used_by.map((u, i) => <p key={`${u.type}-${u.id}-${i}`} className="truncate text-muted-foreground" title={u.label}>{u.label}</p>)
                    : <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell className="whitespace-nowrap text-right align-top">
                  <Button data-testid={P97.tmplPreviewBtn} size="sm" variant="ghost" onClick={() => openPreview(t)} title="Pratinjau payload Meta"><Eye className="h-4 w-4" /></Button>
                  {canManage ? <Button data-testid={P97.tmplEditBtn} size="sm" variant="ghost" onClick={() => setEditing(t)} title="Ubah"><Pencil className="h-4 w-4" /></Button> : null}
                  {canManage && !(t.used_by || []).length ? (
                    <Button data-testid={P97.tmplDeleteBtn} size="sm" variant="ghost" onClick={() => setKillRow(t)} title="Hapus"><Trash2 className="h-4 w-4 text-destructive" /></Button>
                  ) : null}
                  {canManage && t.meta_status !== "APPROVED" ? (
                    <Button data-testid={P97.tmplSubmitBtn} size="sm" variant="outline" onClick={() => submit(t)} disabled={busy === t.id}>
                      <Upload className="mr-1 h-3.5 w-3.5" /> Ajukan
                    </Button>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
            {!rows.length ? <TableRow><TableCell colSpan={6} className="py-6 text-center text-sm text-muted-foreground">Belum ada template. Klik “Template baru”.</TableCell></TableRow> : null}
          </TableBody>
        </Table>
      </div>
      <WaReminderMappingCard templates={rows} canManage={canManage} refreshKey={refreshKey} />
      <WaTemplateEditorDialog template={editing || null} open={editing !== undefined}
        onOpenChange={(v) => !v && setEditing(undefined)} onSaved={load} />
      <ConfirmDialog open={!!killRow} onOpenChange={(v) => !v && setKillRow(null)} title={`Hapus template ${killRow?.name}?`}
        description="Template yang masih dipakai playbook/otomasi/pengingat akan ditolak server." onConfirm={remove} />
      <Dialog open={!!preview} onOpenChange={(v) => !v && setPreview(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Payload Meta — {preview?.t?.name}</DialogTitle><DialogDescription>Bentuk yang dikirim ke <code>/message_templates</code>.</DialogDescription></DialogHeader>
          <pre className="max-h-[50vh] overflow-auto rounded-lg bg-secondary p-3 text-xs">{JSON.stringify(preview?.payload, null, 2)}</pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}
