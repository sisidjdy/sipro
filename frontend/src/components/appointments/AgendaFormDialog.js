import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CalendarPlus, Search, Users, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { cn } from "@/lib/utils";
import { APPTS } from "@/constants/testIds";

const KINDS = [
  ["sales", "Terkait lead/pembeli", "Survei, presentasi unit, tanda tangan"],
  ["internal", "Internal (tanpa lead)", "Rapat internal, kunjungan proyek, rapat vendor"],
];
const DEFAULT_TYPE = { sales: "survey", internal: "internal_meeting" };

const dateParts = (iso) => {
  const d = iso ? new Date(iso) : new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  };
};

/**
 * AgendaFormDialog — buat & ubah agenda (Fase 63).
 *
 * Sampai Fase 62 agenda HANYA bisa lahir dari detail lead, sehingga rapat internal,
 * kunjungan proyek, dan rapat vendor tidak punya tempat sama sekali di kalender. Di sini
 * golongan agenda dipilih lebih dulu: "terkait lead" memaksa memilih leadnya (karena
 * survei tanpa pembeli tidak bermakna), "internal" justru TIDAK menyentuh lead apa pun
 * supaya tahap pipeline tidak naik karena rapat mingguan.
 */
export default function AgendaFormDialog({ open, onOpenChange, editing = null, defaultDate,
  onDone }) {
  const { can } = useAuth();
  const maySales = can("leads", "view");
  const [kind, setKind] = useState(maySales ? "sales" : "internal");
  const [form, setForm] = useState({ title: "", type: "survey", location: "", notes: "" });
  const [when, setWhen] = useState(dateParts());
  const [lead, setLead] = useState(null);
  const [leadQ, setLeadQ] = useState("");
  const [leads, setLeads] = useState([]);
  const [staff, setStaff] = useState([]);
  const [participants, setParticipants] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  useEffect(() => {
    if (!open) return;
    api.get("/appointments/staff").then((r) => setStaff(r.data.data || []))
      .catch(() => setStaff([]));
    if (editing) {
      setKind(editing.lead_id ? "sales" : "internal");
      setForm({ title: editing.title || "", type: editing.type || "survey",
        location: editing.location || "", notes: editing.notes || "" });
      setWhen(dateParts(editing.scheduled_at));
      setParticipants(editing.participants || []);
      setLead(editing.lead_id ? { id: editing.lead_id, name: editing.lead_name } : null);
    } else {
      const k = maySales ? "sales" : "internal";
      setKind(k);
      setForm({ title: "", type: DEFAULT_TYPE[k], location: "", notes: "" });
      setWhen(dateParts(defaultDate));
      setParticipants([]); setLead(null); setLeadQ("");
    }
  }, [open, editing, defaultDate, maySales]);

  const searchLeads = useCallback(async () => {
    if (kind !== "sales" || !maySales) return;
    try {
      const res = await api.get("/leads", { params: { q: leadQ || undefined, limit: 8 } });
      setLeads(res.data.data || []);
    } catch { setLeads([]); }
  }, [kind, leadQ, maySales]);
  useEffect(() => {
    if (!open) return undefined;
    // Debounce: tanpa ini setiap ketikan menembak `GET /leads` sekali.
    const t = setTimeout(() => { searchLeads(); }, 280);
    return () => clearTimeout(t);
  }, [open, searchLeads]);

  const toggleParticipant = (email) => setParticipants((cur) =>
    cur.includes(email) ? cur.filter((e) => e !== email) : [...cur, email]);

  const staffLabel = useMemo(() => Object.fromEntries(
    staff.map((s) => [s.value, s.label])), [staff]);

  const submit = async () => {
    if (!form.title.trim()) { toast.error("Judul agenda wajib diisi."); return; }
    if (kind === "sales" && !lead) {
      toast.error("Agenda penjualan wajib menyebut leadnya — atau pilih golongan Internal.");
      return;
    }
    setBusy(true);
    try {
      const body = {
        title: form.title.trim(), type: form.type, location: form.location || null,
        notes: form.notes || null, participants,
        scheduled_at: new Date(`${when.date}T${when.time}:00`).toISOString(),
      };
      if (editing) await api.put(`/appointments/${editing.id}`, body);
      else await api.post("/appointments", { ...body, lead_id: kind === "sales" ? lead.id : null });
      toast.success(editing ? "Agenda diperbarui." : "Agenda dibuat.");
      onDone && onDone();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan agenda.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={APPTS.form}
        className="max-h-[92vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarPlus className="h-4 w-4 text-primary" />
            {editing ? "Ubah agenda" : "Buat agenda"}
          </DialogTitle>
          <DialogDescription>
            Agenda internal tidak menaikkan tahap lead dan tidak menerbitkan tugas survei —
            rapat mingguan bukan bukti kemajuan pipeline.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {!editing ? (
            <div data-testid={APPTS.formKind} className="grid gap-2 sm:grid-cols-2">
              {KINDS.map(([v, label, hint]) => (
                <button key={v} type="button" disabled={v === "sales" && !maySales}
                  data-testid={`${APPTS.formKind}-${v}`}
                  onClick={() => { setKind(v); set({ type: DEFAULT_TYPE[v] }); }}
                  className={cn("rounded-xl border p-3 text-left transition-colors",
                    kind === v ? "border-primary bg-primary/10" : "hover:bg-secondary",
                    v === "sales" && !maySales && "cursor-not-allowed opacity-50")}>
                  <p className="text-sm font-medium">{label}</p>
                  <p className="text-[11px] text-muted-foreground">{hint}</p>
                </button>
              ))}
            </div>
          ) : null}

          <div>
            <Label className="text-[11px]">Judul agenda</Label>
            <Input data-testid={APPTS.formTitle} value={form.title}
              placeholder={kind === "sales" ? "Survey lokasi & presentasi unit"
                : "Rapat mingguan divisi proyek"}
              onChange={(e) => set({ title: e.target.value })} />
          </div>

          {kind === "sales" ? (
            <div data-testid={APPTS.formLead}>
              <Label className="text-[11px]">Lead / pembeli</Label>
              {lead ? (
                <div className="flex items-center justify-between rounded-lg border p-2.5 text-sm">
                  <span className="font-medium">{lead.name}</span>
                  {!editing ? (
                    <Button size="icon" variant="ghost" aria-label="Ganti lead"
                      onClick={() => setLead(null)}><X className="h-3.5 w-3.5" /></Button>
                  ) : null}
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input data-testid={APPTS.formLeadSearch} className="pl-9" value={leadQ}
                      placeholder="Cari nama atau nomor lead…"
                      onChange={(e) => setLeadQ(e.target.value)} />
                  </div>
                  <div className="max-h-40 divide-y overflow-y-auto rounded-lg border">
                    {!leads.length ? (
                      <p className="p-2.5 text-[12px] text-muted-foreground">
                        Tidak ada lead yang cocok.
                      </p>
                    ) : leads.map((l) => (
                      <button key={l.id} type="button" onClick={() => setLead(l)}
                        data-testid={`${APPTS.formLead}-option`}
                        className="flex w-full items-center justify-between p-2.5 text-left text-[12px] hover:bg-secondary">
                        <span className="font-medium">{l.name}</span>
                        <span className="text-muted-foreground">{l.phone}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <Label className="text-[11px]">Tanggal</Label>
              <Input data-testid={APPTS.formDate} type="date" value={when.date}
                onChange={(e) => setWhen((w) => ({ ...w, date: e.target.value }))} />
            </div>
            <div>
              <Label className="text-[11px]">Jam (WIB)</Label>
              <Input data-testid={APPTS.formTime} type="time" value={when.time}
                onChange={(e) => setWhen((w) => ({ ...w, time: e.target.value }))} />
            </div>
            <div>
              <Label className="text-[11px]">Jenis</Label>
              <ReferenceSelect group="appointment_type" value={form.type}
                testId={APPTS.formType} onChange={(v) => set({ type: v })} />
            </div>
          </div>

          <div>
            <Label className="text-[11px]">Lokasi</Label>
            <Input data-testid={APPTS.formLocation} value={form.location}
              placeholder="Kantor pemasaran / lokasi proyek / daring"
              onChange={(e) => set({ location: e.target.value })} />
          </div>

          <div>
            <Label className="text-[11px]">Peserta (staf yang diundang)</Label>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" data-testid={APPTS.formParticipants}
                  className="w-full justify-start font-normal">
                  <Users className="mr-1.5 h-4 w-4" />
                  {participants.length ? `${participants.length} peserta dipilih`
                    : "Pilih peserta (opsional)"}
                </Button>
              </PopoverTrigger>
              <PopoverContent align="start" className="max-h-64 w-72 overflow-y-auto bg-popover">
                {staff.map((s) => (
                  <label key={s.value} data-testid={APPTS.formParticipant}
                    className="flex cursor-pointer items-center gap-2 rounded-md p-1.5 text-[12px] hover:bg-secondary">
                    <Checkbox checked={participants.includes(s.value)}
                      onCheckedChange={() => toggleParticipant(s.value)} />
                    <span className="min-w-0 flex-1 truncate">{s.label}</span>
                    <span className="text-[10px] uppercase text-muted-foreground">{s.hint}</span>
                  </label>
                ))}
              </PopoverContent>
            </Popover>
            {participants.length ? (
              <p className="mt-1 text-[11px] text-muted-foreground">
                {participants.map((e) => staffLabel[e] || e).join(", ")}
              </p>
            ) : null}
          </div>

          <div>
            <Label className="text-[11px]">Catatan</Label>
            <Textarea data-testid={APPTS.formNotes} rows={3} value={form.notes}
              placeholder="Agenda pembahasan, berkas yang perlu dibawa, dsb."
              onChange={(e) => set({ notes: e.target.value })} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={APPTS.formSubmit} disabled={busy} onClick={submit}>
            {busy ? "Menyimpan…" : editing ? "Simpan perubahan" : "Buat agenda"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
