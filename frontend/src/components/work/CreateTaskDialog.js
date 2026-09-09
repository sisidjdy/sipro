import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import RelatedRecordCombobox from "@/components/work/RelatedRecordCombobox";
import api from "@/services/apiClient";
import { WORK } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";

/**
 * CreateTaskDialog — tugas ad-hoc dari supervisor.
 *
 * Endpoint `POST /api/work/tasks` sudah ada sejak fase awal tetapi TIDAK PERNAH dipakai UI,
 * sehingga supervisor tidak punya cara menugaskan pekerjaan di luar jobdesk otomatis.
 */
// Label jenis record dari Kamus Data `task_related_type`; di sini hanya cara MENCARI record-nya.
const REL_LOOKUP = {
  lead: { endpoint: "/leads?limit=300&sort=created_at&direction=desc",
    toLabel: (r) => `${r.name}${r.phone ? ` — ${r.phone}` : ""}` },
  deal: { endpoint: "/deals?limit=200",
    toLabel: (r) => `${r.lead_name || "Deal"}${r.price ? ` — Rp ${Number(r.price).toLocaleString("id-ID")}` : ""}` },
  unit: { endpoint: "/units?limit=500",
    toLabel: (r) => `${r.code || r.no || r.id}${r.block ? ` — Blok ${r.block}` : ""}` },
  customer: { endpoint: "/customers?limit=300",
    toLabel: (r) => `${r.name}${r.email ? ` — ${r.email}` : ""}` },
  project: { endpoint: "/projects?limit=100",
    toLabel: (r) => `${r.name}${r.code ? ` (${r.code})` : ""}` },
};

export default function CreateTaskDialog({ division, onDone, preset = null,
  triggerLabel = "Tugas Baru", triggerVariant = "default" }) {
  const { options } = useReference();
  const [open, setOpen] = useState(false);
  const [members, setMembers] = useState([]);
  const [jobdesks, setJobdesks] = useState([]);
  const [relRecords, setRelRecords] = useState({});
  const [form, setForm] = useState({
    title: "", description: "", type: "todo", priority: "medium", assigned_to: "", due: "",
    jobdesk_code: "", rel_type: "", rel_id: "",
  });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      if (division) {
        const res = await api.get(`/work/divisions/${division}/members`);
        setMembers(res.data.data || []);
      }
      const jd = await api.get("/work/jobdesks", { params: division ? { division } : {} });
      setJobdesks(jd.data.data || []);
    } catch { /* biarkan kosong; form tetap bisa dipakai ad-hoc */ }
  }, [division]);

  const fetchRecords = useCallback(async (type) => {
    try {
      const res = await api.get(REL_LOOKUP[type].endpoint);
      setRelRecords((c) => ({ ...c, [type]: res.data.data || [] }));
    } catch { setRelRecords((c) => ({ ...c, [type]: [] })); }
  }, []);

  useEffect(() => {
    if (!open) return;
    // Cache dibuang setiap dialog dibuka: record yang baru dibuat di tempat lain harus
    // langsung muncul tanpa memuat ulang halaman.
    setRelRecords({});
    load();
    if (preset?.type) {
      setForm((f) => ({ ...f, rel_type: preset.type, rel_id: preset.id || "" }));
      fetchRecords(preset.type);
    } else if (form.rel_type) {
      // Jenis kaitan tersisa dari sesi dialog sebelumnya (dibatalkan) — muat ulang
      // recordnya, kalau tidak combobox-nya kosong selamanya.
      fetchRecords(form.rel_type);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, load, fetchRecords]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const jdSelected = jobdesks.find((j) => j.code === form.jobdesk_code) || null;

  const pickJobdesk = (code) => {
    if (code === "adhoc") {
      setForm((f) => ({ ...f, jobdesk_code: "" }));
      return;
    }
    const jd = jobdesks.find((j) => j.code === code);
    setForm((f) => ({
      ...f, jobdesk_code: code,
      title: jd?.title || f.title,
      type: jd?.type || f.type,
      priority: jd?.priority || f.priority,
    }));
  };

  const pickRelType = (v) => {
    const type = v === "none" ? "" : v;
    setForm((f) => ({ ...f, rel_type: type, rel_id: "" }));
    if (type && !relRecords[type]) fetchRecords(type);
  };

  const submit = async () => {
    if (form.title.trim().length < 3) { toast.error("Judul tugas minimal 3 karakter."); return; }
    if (form.rel_type && !form.rel_id) {
      toast.error("Pilih record terkaitnya dari daftar.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/work/tasks", {
        title: form.title.trim(), description: form.description || null,
        type: form.type, priority: form.priority,
        assigned_to: form.assigned_to || null,
        due_date: form.due ? new Date(form.due).toISOString() : null,
        jobdesk_code: form.jobdesk_code || null,
        related_entity_type: form.rel_type || null,
        related_entity_id: form.rel_id || null,
      });
      toast.success("Tugas dibuat.");
      setOpen(false);
      setForm({ title: "", description: "", type: "todo", priority: "medium", assigned_to: "", due: "", jobdesk_code: "", rel_type: "", rel_id: "" });
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuat tugas.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant={triggerVariant} data-testid={WORK.createTaskBtn}>
          <Plus className="mr-1.5 h-4 w-4" /> {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent className="bg-background">
        <DialogHeader>
          <DialogTitle>Tugas Baru</DialogTitle>
          <DialogDescription>
            Untuk pekerjaan di luar jobdesk otomatis. Penerima akan mendapat notifikasi.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Jobdesk (dari katalog)</Label>
            <Select value={form.jobdesk_code || "adhoc"} onValueChange={pickJobdesk}>
              <SelectTrigger data-testid={WORK.createTaskJobdesk}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="adhoc">Ad-hoc — di luar jobdesk</SelectItem>
                {jobdesks.map((j) => (
                  <SelectItem key={j.code} value={j.code}>{j.code} — {j.title}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {jdSelected ? (
              <p className="rounded-md bg-secondary/60 px-2.5 py-1.5 text-[11px] text-muted-foreground">
                Mengikuti aturan jobdesk: bukti <b>{jdSelected.proof_kind || "note"}</b> ·
                verifikasi <b>{jdSelected.verify_mode || "none"}</b>
                {jdSelected.sla_hours ? <> · SLA <b>{jdSelected.sla_hours} jam</b></> : null}
              </p>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                Pilih jobdesk agar tugas mengikuti proses bisnis (bukti & verifikasi),
                atau biarkan ad-hoc.
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nt-title">Judul</Label>
            <Input id="nt-title" value={form.title} onChange={(e) => set("title", e.target.value)}
              placeholder="mis. Siapkan materi open house Sabtu" />
          </div>
          <div className="space-y-1.5">
            <Label>Kaitkan ke data (opsional)</Label>
            <div className="grid grid-cols-2 gap-2">
              <Select value={form.rel_type || "none"} onValueChange={pickRelType}>
                <SelectTrigger data-testid={WORK.createTaskRelatedType}>
                  <SelectValue placeholder="Tanpa kaitan" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Tanpa kaitan</SelectItem>
                  {options("task_related_type").filter((r) => REL_LOOKUP[r.value]).map((r) => (
                    <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <RelatedRecordCombobox
                records={relRecords[form.rel_type] || []}
                value={form.rel_id}
                onChange={(v) => set("rel_id", v)}
                toLabel={(REL_LOOKUP[form.rel_type] || {}).toLabel}
                disabled={!form.rel_type}
                placeholder={form.rel_type ? "Pilih record" : "Pilih jenis dulu"}
                fallbackLabel={preset && preset.id === form.rel_id ? preset.label : null}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Jenis</Label>
              <Select value={form.type} onValueChange={(v) => set("type", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {options("task_type").map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Prioritas</Label>
              <Select value={form.priority} onValueChange={(v) => set("priority", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {options("priority").map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Penerima</Label>
            <Select value={form.assigned_to} onValueChange={(v) => set("assigned_to", v)}>
              <SelectTrigger><SelectValue placeholder="Saya sendiri" /></SelectTrigger>
              <SelectContent>
                {members.map((m) => (
                  <SelectItem key={m.email} value={m.email}>
                    {m.name} — {m.level === "supervisor" ? "Supervisor" : "Staf"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nt-due">Tenggat</Label>
            <Input id="nt-due" type="datetime-local" value={form.due}
              onChange={(e) => set("due", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nt-desc">Keterangan</Label>
            <Textarea id="nt-desc" rows={2} value={form.description}
              onChange={(e) => set("description", e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Batal</Button>
          <Button data-testid={WORK.createTaskSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Buat Tugas"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
