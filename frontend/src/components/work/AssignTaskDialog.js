import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { WORK } from "@/constants/testIds";

/** Dialog supervisor: alihkan tugas ke staf divisinya + atur ulang tenggat/prioritas. */
export default function AssignTaskDialog({ open, onOpenChange, taskId, division, onDone }) {
  const [members, setMembers] = useState([]);
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!division) return;
    try {
      const res = await api.get(`/work/divisions/${division}/members`);
      setMembers(res.data.data || []);
    } catch (e) {
      toast.error("Gagal memuat anggota divisi.");
    }
  }, [division]);

  useEffect(() => { if (open) { load(); setEmail(""); setNote(""); setDue(""); } }, [open, load]);

  const submit = async () => {
    if (!email) { toast.error("Pilih penerima tugas."); return; }
    setBusy(true);
    try {
      await api.post(`/work/tasks/${taskId}/assign`, {
        assigned_to: email, note: note || null,
        due_date: due ? new Date(due).toISOString() : null,
      });
      toast.success("Tugas dialihkan.");
      onOpenChange(false);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengalihkan tugas.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-background">
        <DialogHeader>
          <DialogTitle>Alihkan Tugas</DialogTitle>
          <DialogDescription>
            Pilih staf di divisi ini. Penerima akan mendapat notifikasi.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Penerima</Label>
            <Select value={email} onValueChange={setEmail}>
              <SelectTrigger data-testid={WORK.taskAssignSelect}>
                <SelectValue placeholder="Pilih staf…" />
              </SelectTrigger>
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
            <Label htmlFor="assign-due">Tenggat baru (opsional)</Label>
            <Input id="assign-due" type="datetime-local" value={due}
              onChange={(e) => setDue(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="assign-note">Instruksi (opsional)</Label>
            <Textarea id="assign-note" rows={2} value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="mis. selesaikan sebelum rapat pagi" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={WORK.taskAssignSubmit} onClick={submit} disabled={busy || !email}>
            {busy ? "Menyimpan…" : "Alihkan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
