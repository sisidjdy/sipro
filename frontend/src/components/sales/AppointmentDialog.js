import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/services/apiClient";
import { LEADS } from "@/constants/testIds";

/** Lokasi bawaan survei mengikuti PROYEK yang dipilih (nama + lokasi master proyek) — bukan teks tetap. */
export const defaultLocation = (p) => !p ? ""
  : p.marketing_office ? `Kantor pemasaran ${p.name} — ${p.marketing_office}`
    : `Kantor pemasaran ${p.name}${p.location ? ` — ${p.location}` : ""}`;

/**
 * AppointmentDialog — penjadwalan survei/janji temu.
 *
 * Fase 40: diangkat keluar dari `LeadDetail` (drawer) agar bisa dipakai halaman kanonik
 * `/leads/:id` maupun tab Survey tanpa menyalin kode.
 */
export default function AppointmentDialog({ leadId, open, onOpenChange, onDone }) {
  const [title, setTitle] = useState("Survey lokasi & unit");
  const [when, setWhen] = useState("");
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTitle("Survey lokasi & unit"); setWhen("");
    api.get("/projects", { params: { limit: 100 } }).then((r) => {
      const rows = (r.data.data || []).filter((p) => p.status !== "archived");
      setProjects(rows);
      const first = rows[0] || null;
      setProjectId(first?.id || "");
      setLocation(defaultLocation(first));
    }).catch(() => { setProjects([]); setProjectId(""); setLocation(""); });
  }, [open]);

  const pickProject = (pid) => {
    setProjectId(pid);
    setLocation(defaultLocation(projects.find((p) => p.id === pid)));
  };

  const submit = async () => {
    if (!when) { toast.error("Tentukan waktu appointment."); return; }
    if (!location.trim()) { toast.error("Isi lokasi survei."); return; }
    setBusy(true);
    try {
      await api.post("/appointments", {
        lead_id: leadId, title, scheduled_at: new Date(when).toISOString(),
        type: "survey", location: location.trim(), project_id: projectId || null,
      });
      toast.success("Appointment dijadwalkan.");
      onOpenChange(false);
      onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menjadwalkan."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-background">
        <DialogHeader><DialogTitle>Jadwalkan Survey / Janji Temu</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label htmlFor="appt-title">Judul</Label>
            <Input id="appt-title" data-testid={LEADS.apptTitle} value={title}
              onChange={(e) => setTitle(e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="appt-when">Waktu</Label>
            <Input id="appt-when" data-testid={LEADS.apptWhen} type="datetime-local" value={when}
              onChange={(e) => setWhen(e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="appt-project">Proyek yang disurvei</Label>
            <select id="appt-project" data-testid={LEADS.apptProject} value={projectId}
              onChange={(e) => pickProject(e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm">
              {!projects.length ? <option value="">Belum ada proyek</option> : null}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}{p.code ? ` (${p.code})` : ""}</option>
              ))}
            </select>
            <p className="text-[11px] text-muted-foreground">
              Lokasi di bawah mengikuti nama & alamat proyek dari Master Proyek; boleh diubah.
            </p></div>
          <div className="space-y-1.5"><Label htmlFor="appt-loc">Lokasi</Label>
            <Input id="appt-loc" data-testid={LEADS.apptLocation} value={location}
              placeholder="Kantor pemasaran / titik kumpul survei"
              onChange={(e) => setLocation(e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={LEADS.apptSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan..." : "Jadwalkan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
