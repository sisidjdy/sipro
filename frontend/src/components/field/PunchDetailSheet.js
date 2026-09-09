import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Save } from "lucide-react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import BeforeAfterCompare from "@/components/patterns/BeforeAfterCompare";
import PhotoUploader from "@/components/patterns/PhotoUploader";
import StatusPill from "@/components/patterns/StatusPill";
import { formatDateWIB, formatDateTimeWIB } from "@/utils/formatters";
import { toPhotoList } from "@/utils/photoSrc";
import api from "@/services/apiClient";
import * as sync from "@/services/offlineSync";
import { FIELD } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";


function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value || "-"}</span>
    </div>
  );
}

export default function PunchDetailSheet({ punch, open, canManage, onOpenChange, onChanged }) {
  const { labelOf, options } = useReference();
  const [status, setStatus] = useState("");
  const [fixPhotos, setFixPhotos] = useState([]);
  const [foundPhotos, setFoundPhotos] = useState([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (punch) { setStatus(punch.status); setFixPhotos([]); setFoundPhotos([]); setNote(""); }
  }, [punch]);
  if (!punch) return null;

  const found = toPhotoList(punch, { label: punch.title || "Temuan", date: punch.created_at, scope: "unit" });
  const fixed = toPhotoList({ photos: punch.fix_photos },
    { label: `Perbaikan: ${punch.title || "temuan"}`, date: punch.updated_at, scope: "unit" });
  // Satu kartu berpasangan agar terlihat jelas mana "sebelum" dan mana "sesudah".
  const pairs = (found.length || fixed.length) ? [{
    punch_id: punch.id, title: punch.title, severity: punch.severity, status: punch.status,
    resolved: ["closed", "verified"].includes(punch.status) && fixed.length > 0,
    note: punch.fix_note, opened_at: punch.created_at,
    fixed_at: punch.closed_at || (["closed", "verified"].includes(punch.status) ? punch.updated_at : null),
    before: found, after: fixed,
  }] : [];

  // Foto temuan yang ditambahkan langsung disimpan (bukan menunggu tombol Simpan) agar
  // pasangan bukti "sebelum" lengkap walau status belum diubah.
  const addFoundPhotos = async (list) => {
    setFoundPhotos(list);
    const added = list.filter((f) => !foundPhotos.includes(f));
    if (!added.length) return;
    try {
      await api.put(`/field/punchlist/${punch.id}`, { photos: added });
      toast.success(`${added.length} foto temuan ditambahkan.`);
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menambahkan foto temuan.");
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      // Fase 50B: perubahan status + foto "sesudah" juga bisa terjadi tanpa sinyal.
      // `client_ref` menjaga agar kiriman ulang TIDAK melampirkan bukti dua kali.
      const out = await sync.submitOrQueue({
        kind: "punch_status",
        endpoint: `/field/punchlist/${punch.id}/status`,
        payload: { status, note: note || null },
        photos: fixPhotos,
        title: `${punch.title?.slice(0, 40)} → ${labelOf("punch_status", status)}`,
      });
      toast.success(out.queued
        ? "Perubahan tersimpan di perangkat — terkirim sendiri begitu sinyal kembali."
        : `Status → ${labelOf("punch_status", status)}.`
          + (fixPhotos.length ? ` ${fixPhotos.length} foto bukti perbaikan dilampirkan.` : ""));
      onOpenChange(false); onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengubah status."); }
    finally { setBusy(false); }
  };

  const unchanged = status === punch.status && !fixPhotos.length && !note.trim();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={FIELD.punchDetail} className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{punch.title}</SheetTitle>
          <SheetDescription>Detail temuan, bukti foto, & pembaruan status perbaikan.</SheetDescription>
        </SheetHeader>
        <div className="mt-5 space-y-5">
          <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
            <div className="mb-2 flex items-center justify-between">
              <StatusPill status={punch.status} group="punch_status" />
              <StatusPill status={punch.severity} group="punch_severity" />
            </div>
            <Row label="Lokasi" value={punch.location} />
            <Row label="Kategori" value={labelOf("work_category", punch.category)} />
            <Row label="Ditugaskan" value={punch.assigned_to} />
            <Row label="Tenggat" value={punch.due_date ? formatDateWIB(punch.due_date) : "-"} />
            <Row label="Dibuka oleh" value={punch.opened_by} />
            {punch.closed_at ? <Row label="Selesai" value={formatDateTimeWIB(punch.closed_at)} /> : null}
            {punch.description ? <p className="mt-2 rounded-lg bg-secondary p-3 text-sm">{punch.description}</p> : null}
          </div>

          <div className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
            <p className="text-sm font-semibold">Bukti kerja: sebelum → sesudah</p>
            <BeforeAfterCompare repairs={pairs}
              emptyText="Belum ada foto temuan maupun bukti perbaikan pada item ini." />
            {canManage ? (
              <div className="space-y-1.5 border-t pt-3">
                <Label>Tambah foto temuan (foto “sebelum”)</Label>
                <PhotoUploader value={foundPhotos} onChange={addFoundPhotos} ownerType="punch_item"
                  ownerId={punch.id} max={4} testId={FIELD.punchPhotoInput}
                  watermark={`Temuan: ${punch.title || "punch list"}`}
                  label="Unggah foto temuan" />
                <p className="text-[11px] text-muted-foreground">
                  Dipakai bila foto temuan belum diambil saat item dibuat — foto lama tidak
                  ditimpa, hanya ditambahkan.
                </p>
              </div>
            ) : null}
          </div>

          {canManage ? (
            <div className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
              <p className="text-sm font-semibold">Perbarui Status</p>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger data-testid={FIELD.punchStatusSelect} aria-label="Status temuan"><SelectValue /></SelectTrigger>
                <SelectContent>{options("punch_status").map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
              </Select>
              <div className="space-y-1.5">
                <Label>Foto bukti perbaikan (opsional)</Label>
                <PhotoUploader value={fixPhotos} onChange={setFixPhotos} ownerType="punch_item"
                  ownerId={punch.id} max={4} testId={FIELD.fixPhotoInput}
                  watermark={`Perbaikan: ${punch.title || "punch list"}`}
                  label="Unggah foto bukti perbaikan" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="punchdetailsheet-catatan-perbaikan">Catatan perbaikan</Label>
                <Textarea id="punchdetailsheet-catatan-perbaikan" rows={2} value={note} onChange={(e) => setNote(e.target.value)}
                  placeholder="mis. sudah diaci & dicat ulang" />
              </div>
              <Button data-testid={FIELD.punchStatusSubmit} className="w-full"
                disabled={busy || unchanged} onClick={save}>
                <Save className="mr-1.5 h-4 w-4" /> Simpan Perubahan
              </Button>
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
