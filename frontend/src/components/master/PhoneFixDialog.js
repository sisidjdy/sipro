import React, { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ExternalLink, Save, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import api from "@/services/apiClient";
import { MASTER } from "@/constants/testIds";

const ENTITY_PATH = { leads: "/leads", customers: "/customers", vendors: "/partners" };

function FixItem({ collection, item, kind, onSaved }) {
  const [phone, setPhone] = useState(item.normalized || item.phone || "");
  const [busy, setBusy] = useState(false);
  const path = ENTITY_PATH[collection];

  const save = async (value) => {
    setBusy(true);
    try {
      const r = await api.post("/master/phone-fix", { collection, id: item.id, phone: value });
      toast.success(r.data.message);
      onSaved(r.data.data.after);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperbarui nomor."); }
    finally { setBusy(false); }
  };

  return (
    <li className="rounded-lg border bg-background p-3" data-testid={`${MASTER.phoneFixItem}-${item.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{item.name || item.id}</p>
          <p className="font-mono text-xs text-muted-foreground">
            {item.phone}
            {kind === "duplicate" ? (
              <> → {item.normalized} <span className="font-sans text-amber-700">· bentrok dengan {item.clash_name || item.clash_id}</span></>
            ) : <span className="font-sans text-rose-700"> · tidak bisa dirapikan otomatis</span>}
          </p>
        </div>
        {path ? (
          <Button asChild size="sm" variant="ghost" data-testid={`${MASTER.phoneFixLink}-${item.id}`}>
            <Link to={`${path}/${item.id}`}><ExternalLink className="h-3.5 w-3.5" /> Buka</Link>
          </Button>
        ) : null}
      </div>
      <div className="mt-2 flex gap-2">
        <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+628xxxxxxxxx"
          className="h-8 font-mono text-xs" data-testid={`${MASTER.phoneFixInput}-${item.id}`} />
        <Button size="sm" className="h-8" disabled={busy || !phone.trim()} onClick={() => save(phone)}
          data-testid={`${MASTER.phoneFixSave}-${item.id}`}>
          <Save className="h-3.5 w-3.5" /> Simpan
        </Button>
        <Button size="sm" variant="outline" className="h-8" disabled={busy} onClick={() => save("")}
          title="Hapus nomor dari baris ini" data-testid={`${MASTER.phoneFixClear}-${item.id}`}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </li>
  );
}

/** Dialog tindak lanjut nomor ganda / tidak valid untuk satu koleksi. */
export default function PhoneFixDialog({ row, open, onOpenChange, onUpdated }) {
  if (!row) return null;
  const dup = row.duplicate_samples || [];
  const inv = row.invalid_samples || [];
  const handleSaved = (after) => { onUpdated(after); };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid={MASTER.phoneFixDialog}>
        <DialogHeader>
          <DialogTitle>Tindak lanjut nomor · {row.collection}.{row.field}</DialogTitle>
          <DialogDescription>
            Perbaiki nomor per baris (format 08xx atau +62xx), atau hapus nomor bila memang tidak bisa dipakai.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
          {dup.length ? (
            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-700">Akan ganda ({row.duplicate})</h4>
              <ul className="space-y-2">
                {dup.map((it) => <FixItem key={it.id} collection={row.collection} item={it} kind="duplicate" onSaved={handleSaved} />)}
              </ul>
            </section>
          ) : null}
          {inv.length ? (
            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-700">Tidak valid ({row.invalid})</h4>
              <ul className="space-y-2">
                {inv.map((it) => <FixItem key={it.id} collection={row.collection} item={it} kind="invalid" onSaved={handleSaved} />)}
              </ul>
            </section>
          ) : null}
          {!dup.length && !inv.length ? (
            <p className="text-sm text-emerald-800">Tidak ada lagi baris yang perlu ditindaklanjuti.</p>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
