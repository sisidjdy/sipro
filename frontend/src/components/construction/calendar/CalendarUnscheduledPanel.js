import React, { useState } from "react";
import { toast } from "sonner";
import { CalendarPlus, ClipboardCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import RefLabel from "@/components/patterns/RefLabel";
import api from "@/services/apiClient";
import { CAL } from "@/constants/testIds";

/**
 * INSPEKSI/QC BELUM DIJADWALKAN.
 *
 * Kalender TIDAK boleh mengarang tanggal: inspeksi yang belum punya tanggal rencana
 * ditampilkan di sini apa adanya, beserta aksi menjadwalkannya. Bila tanggal yang dipilih
 * jatuh pada hari libur, server menolak dan alasannya (beserta saran tanggal) ditampilkan
 * langsung di dialog — bukan pesan "gagal" tanpa arti.
 */
export default function CalendarUnscheduledPanel({ rows, canSchedule, onDone }) {
  const [target, setTarget] = useState(null);
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const list = rows || [];

  const save = async () => {
    if (!date) { setError("Pilih tanggal rencana inspeksi."); return; }
    setBusy(true); setError("");
    try {
      await api.put(`/inspections/${target.id}/schedule`,
        { scheduled_date: date, note: note || null });
      toast.success(`Inspeksi ${target.inspection_number} dijadwalkan ${date}.`);
      setTarget(null); setDate(""); setNote("");
      onDone && onDone();
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal menjadwalkan inspeksi.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid={CAL.unscheduled} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
      <p className="inline-flex items-center gap-1.5 text-sm font-semibold">
        <ClipboardCheck className="h-4 w-4 text-violet-600" />
        Inspeksi belum dijadwalkan
        <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] tabular-nums">
          {list.length}
        </span>
      </p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        Inspeksi ini tidak muncul di kalender karena belum punya tanggal rencana — kalender
        tidak mengarang tanggal. Beri tanggal agar ikut terlihat &amp; terhitung bentroknya.
      </p>
      <div className="mt-2 space-y-1.5">
        {!list.length ? (
          <p className="rounded-lg border border-dashed bg-background p-2.5 text-[11px] text-muted-foreground">
            Semua inspeksi yang masih berjalan sudah punya tanggal rencana — tidak ada yang
            tersembunyi dari kalender.
          </p>
        ) : null}
        {list.map((r) => (
          <div key={r.id} data-testid={CAL.unscheduledRow} data-inspection={r.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background p-2 text-xs">
            <div className="min-w-0">
              <p className="font-medium">
                <span className="font-mono text-primary">{r.inspection_number}</span>{" "}
                {r.title}
              </p>
              <p className="text-[11px] text-muted-foreground">
                <RefLabel group="inspection_category" value={r.category} />
                {r.project_name ? ` · ${r.project_name}` : ""}
              </p>
            </div>
            {canSchedule ? (
              <Button size="sm" variant="outline" data-testid={CAL.scheduleBtn}
                aria-label={`Jadwalkan ${r.inspection_number}`}
                onClick={() => { setTarget(r); setDate(""); setNote(""); setError(""); }}>
                <CalendarPlus className="mr-1 h-3.5 w-3.5" /> Jadwalkan
              </Button>
            ) : null}
          </div>
        ))}
      </div>

      <Dialog open={!!target} onOpenChange={(v) => !v && setTarget(null)}>
        <DialogContent data-testid={CAL.scheduleDialog}>
          <DialogHeader>
            <DialogTitle>Jadwalkan inspeksi {target?.inspection_number}</DialogTitle>
            <DialogDescription>
              Pilih hari kerja. Tanggal yang jatuh pada hari libur akan ditolak beserta saran
              tanggal terdekat, supaya rencana QC tidak bertabrakan dengan kalender kerja.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label htmlFor="cal-insp-date">Tanggal rencana inspeksi</Label>
              <Input id="cal-insp-date" type="date" value={date}
                data-testid={CAL.scheduleDate}
                onChange={(e) => setDate(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="cal-insp-note">Catatan (opsional)</Label>
              <Textarea id="cal-insp-note" value={note} rows={2}
                data-testid={CAL.scheduleNote}
                placeholder="mis. bersamaan dengan pengecekan struktur lantai 2"
                onChange={(e) => setNote(e.target.value)} />
            </div>
            {error ? (
              <p className="rounded-lg border border-rose-200 bg-rose-50 p-2 text-xs text-rose-800">
                {error}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setTarget(null)}>Batal</Button>
            <Button data-testid={CAL.scheduleSave} disabled={busy} onClick={save}>
              {busy ? "Menyimpan…" : "Simpan tanggal"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
