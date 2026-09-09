import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { OMNI } from "@/constants/testIds";


function emptyForm() {
  return {
    name: "", trigger_event: "message.received", keywords: "", no_response_days: 3,
    act_create_task: true, act_send_template: false, template_code: "",
    act_suggest_stage: false, stage: "appointment", act_notify: false,
  };
}

export default function RulesPanel() {
  const { options, labelOf } = useReference();
  const [rules, setRules] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [r, t] = await Promise.all([
        api.get("/automation-rules"), api.get("/wa-templates"),
      ]);
      setRules(r.data.data || []);
      setTemplates(t.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat rules.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => { setEditId(null); setForm(emptyForm()); setOpen(true); };
  const openEdit = (r) => {
    const acts = r.actions || [];
    const get = (type) => acts.find((a) => a.type === type) || null;
    setEditId(r.id);
    setForm({
      name: r.name, trigger_event: r.trigger?.event || "message.received",
      keywords: (r.trigger?.keywords || []).join(", "),
      no_response_days: r.trigger?.no_response_days || 3,
      act_create_task: !!get("create_task"),
      act_send_template: !!get("send_template"), template_code: get("send_template")?.template_code || "",
      act_suggest_stage: !!get("suggest_stage"), stage: get("suggest_stage")?.stage || "appointment",
      act_notify: !!get("notify"),
    });
    setOpen(true);
  };

  const buildActions = () => {
    const a = [];
    if (form.act_create_task) a.push({ type: "create_task" });
    if (form.act_send_template) a.push({ type: "send_template", template_code: form.template_code });
    if (form.act_suggest_stage) a.push({ type: "suggest_stage", stage: form.stage });
    if (form.act_notify) a.push({ type: "notify" });
    return a;
  };

  const save = async () => {
    if (!form.name.trim()) { toast.error("Nama rule wajib diisi."); return; }
    const actions = buildActions();
    if (!actions.length) { toast.error("Pilih minimal satu aksi."); return; }
    if (form.act_send_template && !form.template_code) { toast.error("Pilih template untuk aksi kirim template."); return; }
    setBusy(true);
    const payload = {
      name: form.name.trim(), trigger_event: form.trigger_event,
      keywords: form.trigger_event === "message.received"
        ? form.keywords.split(",").map((k) => k.trim()).filter(Boolean) : [],
      no_response_days: form.trigger_event === "no_response" ? Number(form.no_response_days) || 3 : null,
      actions,
    };
    try {
      if (editId) await api.put(`/automation-rules/${editId}`, payload);
      else await api.post("/automation-rules", payload);
      toast.success(editId ? "Rule diperbarui." : "Rule dibuat.");
      setOpen(false); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan rule."); }
    finally { setBusy(false); }
  };

  const toggle = async (r) => {
    try { await api.post(`/automation-rules/${r.id}/toggle`); load(); }
    catch { toast.error("Gagal mengubah status rule."); }
  };
  const remove = async (r) => {
    try { await api.delete(`/automation-rules/${r.id}`); toast.success("Rule dihapus."); load(); }
    catch { toast.error("Gagal menghapus rule."); }
  };

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Aturan otomasi percakapan (trigger &rarr; aksi). Semua kiriman template berjalan <b>SIMULASI</b>.
        </p>
        <Button data-testid={OMNI.ruleAddBtn} size="sm" onClick={openCreate}>
          <Plus className="mr-1.5 h-4 w-4" /> Tambah Rule
        </Button>
      </div>

      {!rules.length ? (
        <EmptyState icon={Zap} title="Belum ada rule" description="Buat aturan otomasi pertama Anda."
          actionLabel="Tambah Rule" onAction={openCreate} />
      ) : (
        <div className="space-y-2">
          {rules.map((r) => (
            <div key={r.id} data-testid={OMNI.ruleRow}
              className="flex items-start justify-between gap-3 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">{r.name}</p>
                  <StatusPill status={r.is_active ? "active" : "snoozed"} label={r.is_active ? "Aktif" : "Nonaktif"} />
                  <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[11px]">{labelOf("automation_trigger", r.trigger?.event)}</span>
                </div>
                {r.trigger?.keywords?.length ? (
                  <p className="mt-1 text-xs text-muted-foreground">Keyword: {r.trigger.keywords.join(", ")}</p>
                ) : null}
                <p className="mt-1 text-xs text-muted-foreground">
                  Aksi: {(r.actions || []).map((a) => a.type).join(", ") || "-"} &middot; Eksekusi: {r.executions || 0}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Switch data-testid={OMNI.ruleToggle} checked={!!r.is_active} onCheckedChange={() => toggle(r)} />
                <Button data-testid={OMNI.ruleEditBtn} variant="ghost" size="icon" onClick={() => openEdit(r)}>
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button data-testid={OMNI.ruleDeleteBtn} variant="ghost" size="icon" onClick={() => remove(r)}>
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editId ? "Ubah Rule" : "Tambah Rule"}</DialogTitle>
            <DialogDescription>Tentukan trigger dan aksi otomatis.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="rulespanel-nama-rule">Nama Rule</Label>
              <Input id="rulespanel-nama-rule" data-testid={OMNI.ruleName} value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="mis. Intent Harga/KPR" />
            </div>
            <div className="space-y-1.5">
              <Label>Trigger</Label>
              <Select value={form.trigger_event} onValueChange={(v) => setForm({ ...form, trigger_event: v })}>
                <SelectTrigger data-testid={OMNI.ruleEvent}><SelectValue /></SelectTrigger>
                <SelectContent>
                  {options("automation_trigger").map((e) => <SelectItem key={e.value} value={e.value}>{e.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {form.trigger_event === "message.received" && (
              <div className="space-y-1.5">
                <Label htmlFor="rulespanel-keyword-pisahkan-koma">Keyword (pisahkan koma)</Label>
                <Input id="rulespanel-keyword-pisahkan-koma" data-testid={OMNI.ruleKeywords} value={form.keywords}
                  onChange={(e) => setForm({ ...form, keywords: e.target.value })} placeholder="harga, kpr, survey" />
              </div>
            )}
            {form.trigger_event === "no_response" && (
              <div className="space-y-1.5">
                <Label htmlFor="rulespanel-diam-berapa-hari">Diam berapa hari</Label>
                <Input id="rulespanel-diam-berapa-hari" data-testid={OMNI.ruleDays} type="number" min={1} value={form.no_response_days}
                  onChange={(e) => setForm({ ...form, no_response_days: e.target.value })} />
              </div>
            )}
            <div className="space-y-2">
              <Label>Aksi</Label>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={form.act_create_task} onCheckedChange={(v) => setForm({ ...form, act_create_task: !!v })} />
                Buat tugas follow-up
              </label>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={form.act_send_template} onCheckedChange={(v) => setForm({ ...form, act_send_template: !!v })} />
                Kirim template WA
              </label>
              {form.act_send_template && (
                <Select value={form.template_code} onValueChange={(v) => setForm({ ...form, template_code: v })}>
                  <SelectTrigger className="ml-6 w-[calc(100%-1.5rem)]"><SelectValue placeholder="Pilih template" /></SelectTrigger>
                  <SelectContent>
                    {templates.map((t) => <SelectItem key={t.id} value={t.code}>{t.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={form.act_suggest_stage} onCheckedChange={(v) => setForm({ ...form, act_suggest_stage: !!v })} />
                Usulkan majukan stage (NBA)
              </label>
              {form.act_suggest_stage && (
                <Select value={form.stage} onValueChange={(v) => setForm({ ...form, stage: v })}>
                  <SelectTrigger className="ml-6 w-[calc(100%-1.5rem)]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {options("lead_stage").map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={form.act_notify} onCheckedChange={(v) => setForm({ ...form, act_notify: !!v })} />
                Notifikasi ke sales
              </label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Batal</Button>
            <Button data-testid={OMNI.ruleSave} onClick={save} disabled={busy}>{busy ? "Menyimpan..." : "Simpan"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
