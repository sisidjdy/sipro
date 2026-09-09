import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Settings2, Play, Zap, Repeat, Hand, ShieldCheck, Bot } from "lucide-react";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { WORK } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";

const SOURCE_ICON = { event: Zap, recurring: Repeat, manual: Hand };
const VERIFY_ICON = { system: Bot, supervisor: ShieldCheck };

/**
 * JobdeskPanel — KATALOG PEKERJAAN per divisi + pengaturan oleh supervisor.
 *
 * Inti Fase 29: pekerjaan tidak lagi "muncul entah dari mana". Setiap jenis pekerjaan
 * punya kode, sumber (event sistem / berulang / manual), aturan penerima, SLA, bukti
 * wajib, dan cara verifikasi — semuanya bisa diubah supervisor TANPA ubah kode.
 */
export default function JobdeskPanel({ division, canManage, onChanged }) {
  const { options } = useReference();
  const [rows, setRows] = useState([]);
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [edit, setEdit] = useState(null);
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/work/jobdesks", { params: division ? { division } : {} });
      setRows(res.data.data || []);
      if (division) {
        try {
          const m = await api.get(`/work/divisions/${division}/members`);
          setMembers(m.data.data || []);
        } catch { setMembers([]); }
      }
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat katalog jobdesk.");
    } finally { setLoading(false); }
  }, [division]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      await api.put(`/work/jobdesks/${edit.code}`, {
        is_active: edit.is_active, sla_hours: Number(edit.sla_hours),
        priority: edit.priority, assignee_rule: edit.assignee_rule,
        assignee_email: edit.assignee_rule === "specific" ? edit.assignee_email : null,
        verify_mode: edit.verify_mode, proof_kind: edit.proof_kind,
        recurrence: edit.source === "recurring" ? edit.recurrence : null,
      });
      toast.success(`Jobdesk ${edit.code} diperbarui.`);
      setEdit(null); load(); onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan jobdesk.");
    } finally { setBusy(false); }
  };

  const doRun = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/work/jobdesks/${run.code}/run`, {
        assigned_to: run.assigned_to || null, note: run.note || null,
      });
      toast.success(`${res.data.created} tugas dibuat dari ${run.code}.`);
      setRun(null); load(); onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menjalankan jobdesk.");
    } finally { setBusy(false); }
  };

  if (loading) return <LoadingCards count={5} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={WORK.jobdeskPanel} className="space-y-3">
      <p className="rounded-xl border bg-card p-3 text-xs text-muted-foreground shadow-[var(--shadow-card)]">
        {rows.length} jobdesk. <span className="font-medium text-foreground">Otomatis</span> lahir
        dari event sistem, <span className="font-medium text-foreground">Berulang</span> dibuat
        sesuai jadwal, <span className="font-medium text-foreground">Manual</span> ditugaskan
        supervisor. Verifikasi <span className="font-medium text-foreground">sistem</span> memeriksa
        data secara otomatis; verifikasi <span className="font-medium text-foreground">supervisor</span>
        {" "}dipakai untuk pekerjaan yang butuh penilaian manusia (mis. pendampingan survey/akad).
      </p>
      <div className="overflow-x-auto rounded-xl border bg-card shadow-sm">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-secondary/60 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Kode</th>
              <th className="px-3 py-2 text-left font-medium">Pekerjaan</th>
              <th className="px-3 py-2 text-left font-medium">Sumber</th>
              <th className="px-3 py-2 text-left font-medium">Penerima</th>
              <th className="px-3 py-2 text-left font-medium">SLA</th>
              <th className="px-3 py-2 text-left font-medium">Bukti / Verifikasi</th>
              <th className="px-3 py-2 text-right font-medium">Aktif</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((j) => {
              const SIcon = SOURCE_ICON[j.source] || Hand;
              const VIcon = VERIFY_ICON[j.verify_mode];
              return (
                <tr key={j.code} data-testid={WORK.jobdeskRow} data-jobdesk-code={j.code}
                  className="border-t align-top">
                  <td className="px-3 py-2 font-mono text-xs font-semibold text-primary">{j.code}</td>
                  <td className="px-3 py-2">
                    <p className="font-medium leading-snug">{j.title}</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">{j.description}</p>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {j.open_tasks} aktif · {j.done_tasks} selesai
                    </p>
                  </td>
                  <td className="px-3 py-2 text-xs">
                    <span className="inline-flex items-center gap-1">
                      <SIcon className="h-3.5 w-3.5 text-muted-foreground" />
                      <RefLabel group="jobdesk_source" value={j.source} />
                    </span>
                    {j.source === "recurring" ? (
                      <p className="text-[11px] text-muted-foreground">
                        <RefLabel group="recurrence" value={j.recurrence} />
                      </p>
                    ) : null}
                    {j.event ? (
                      <p className="font-mono text-[10px] text-muted-foreground">{j.event}</p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    <RefLabel group="assignee_rule" value={j.assignee_rule} />
                    {j.assignee_email ? (
                      <p className="text-[11px] text-muted-foreground">{j.assignee_email}</p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-xs tabular-nums">
                    {j.sla_hours < 1 ? `${Math.round(j.sla_hours * 60)} mnt` : `${j.sla_hours} jam`}
                    <div className="mt-1"><StatusPill status={j.priority} group="priority" /></div>
                  </td>
                  <td className="px-3 py-2 text-xs">
                    <RefLabel group="proof_kind" value={j.proof_kind} />
                    <p className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                      {VIcon ? <VIcon className="h-3 w-3" /> : null}
                      <RefLabel group="verify_mode" value={j.verify_mode} />
                    </p>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <StatusPill status={j.is_active ? "active" : "cancelled"}
                      label={j.is_active ? "Aktif" : "Nonaktif"} />
                  </td>
                  <td className="px-3 py-2">
                    {canManage ? (
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="outline" data-testid={WORK.jobdeskConfigBtn}
                          aria-label={`Atur jobdesk ${j.code}`} onClick={() => setEdit({ ...j })}>
                          <Settings2 className="h-3.5 w-3.5" />
                        </Button>
                        <Button size="sm" variant="outline" data-testid={WORK.jobdeskRunBtn}
                          aria-label={`Jalankan jobdesk ${j.code}`}
                          onClick={() => setRun({ code: j.code, title: j.title, note: "", assigned_to: "" })}>
                          <Play className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Dialog open={!!edit} onOpenChange={(v) => !v && setEdit(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto bg-background">
          <DialogHeader>
            <DialogTitle>Atur jobdesk {edit?.code}</DialogTitle>
            <DialogDescription>{edit?.title}</DialogDescription>
          </DialogHeader>
          {edit ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-lg border bg-card px-3 py-2 shadow-[var(--shadow-card)]">
                <Label htmlFor="jd-active">Jobdesk aktif</Label>
                <Switch id="jd-active" data-testid={WORK.jobdeskActive} checked={!!edit.is_active}
                  onCheckedChange={(v) => setEdit({ ...edit, is_active: v })} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="jd-sla">SLA (jam)</Label>
                  <Input id="jd-sla" data-testid={WORK.jobdeskSla} type="number" step="0.25"
                    value={edit.sla_hours}
                    onChange={(e) => setEdit({ ...edit, sla_hours: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>Prioritas</Label>
                  <Select value={edit.priority}
                    onValueChange={(v) => setEdit({ ...edit, priority: v })}>
                    <SelectTrigger data-testid={WORK.jobdeskPriority}><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {options("priority").map((o) => (
                        <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Aturan penerima</Label>
                <Select value={edit.assignee_rule}
                  onValueChange={(v) => setEdit({ ...edit, assignee_rule: v })}>
                  <SelectTrigger data-testid={WORK.jobdeskAssigneeRule}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {options("assignee_rule").map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {edit.assignee_rule === "specific" ? (
                <div className="space-y-1.5">
                  <Label>Orang tertentu</Label>
                  <Select value={edit.assignee_email || ""}
                    onValueChange={(v) => setEdit({ ...edit, assignee_email: v })}>
                    <SelectTrigger data-testid={WORK.jobdeskAssignee}>
                      <SelectValue placeholder="Pilih anggota…" />
                    </SelectTrigger>
                    <SelectContent>
                      {members.map((m) => (
                        <SelectItem key={m.email} value={m.email}>{m.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}
              {edit.source === "recurring" ? (
                <div className="space-y-1.5">
                  <Label>Perulangan</Label>
                  <Select value={edit.recurrence || "daily"}
                    onValueChange={(v) => setEdit({ ...edit, recurrence: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {options("recurrence").map((o) => (
                        <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Bukti wajib</Label>
                  <Select value={edit.proof_kind}
                    onValueChange={(v) => setEdit({ ...edit, proof_kind: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {options("proof_kind").map((o) => (
                        <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Cara verifikasi</Label>
                  <Select value={edit.verify_mode}
                    onValueChange={(v) => setEdit({ ...edit, verify_mode: v })}>
                    <SelectTrigger data-testid={WORK.jobdeskVerify}><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {options("verify_mode").map((o) => (
                        <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEdit(null)} disabled={busy}>Batal</Button>
            <Button data-testid={WORK.jobdeskSaveBtn} onClick={save} disabled={busy}>
              {busy ? "Menyimpan…" : "Simpan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!run} onOpenChange={(v) => !v && setRun(null)}>
        <DialogContent className="bg-background">
          <DialogHeader>
            <DialogTitle>Jalankan sekarang: {run?.code}</DialogTitle>
            <DialogDescription>{run?.title}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Penerima (opsional — kosong = ikuti aturan jobdesk)</Label>
              <Select value={run?.assigned_to || ""}
                onValueChange={(v) => setRun({ ...run, assigned_to: v })}>
                <SelectTrigger><SelectValue placeholder="Ikuti aturan penerima" /></SelectTrigger>
                <SelectContent>
                  {members.map((m) => (
                    <SelectItem key={m.email} value={m.email}>{m.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="jobdeskpanel-instruksi-tambahan">Instruksi tambahan</Label>
              <Textarea id="jobdeskpanel-instruksi-tambahan" rows={2} value={run?.note || ""}
                onChange={(e) => setRun({ ...run, note: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRun(null)} disabled={busy}>Batal</Button>
            <Button onClick={doRun} disabled={busy}>{busy ? "Menjalankan…" : "Buat Tugas"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
