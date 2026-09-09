import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Phone, Wand2, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import PhoneFixDialog from "@/components/master/PhoneFixDialog";
import api from "@/services/apiClient";
import { MASTER } from "@/constants/testIds";

/** Kartu nomor telepon: berapa yang belum +62 per koleksi + tombol rapikan sekali jalan + tindak lanjut. */
export default function PhoneHealthCard() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [fixColl, setFixColl] = useState(null);

  const load = useCallback(() => {
    api.get("/master/phone-health").then((r) => setData(r.data.data)).catch(() => setData(null));
  }, []);
  useEffect(() => { load(); }, [load]);

  const run = async () => {
    setBusy(true);
    try {
      const r = await api.post("/master/normalize-phones");
      toast.success(r.data.message);
      setData(r.data.data.after);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal merapikan nomor."); }
    finally { setBusy(false); }
  };

  if (!data) return null;
  const clean = !data.total_pending && !data.total_duplicate && !data.total_invalid;
  const fixRow = data.rows.find((r) => r.collection === fixColl) || null;
  return (
    <div data-testid={MASTER.phoneHealth} className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="flex items-center gap-2 text-sm font-semibold">
            <Phone className="h-4 w-4 text-sky-600" /> Format nomor telepon (+62)
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Nomor lead, customer, portal pembeli, percakapan WA, penerima broadcast, pengguna, dan vendor
            harus berformat +62 agar integrasi WhatsApp tidak salah alamat.
          </p>
        </div>
        <Button size="sm" onClick={run} disabled={busy || !data.total_pending}
          variant={data.total_pending ? "default" : "outline"}
          className="disabled:opacity-100 disabled:text-muted-foreground disabled:border-dashed"
          title={data.total_pending ? "Rapikan semua nomor 08xx/62xx menjadi +62xx" : "Tidak ada nomor yang perlu dirapikan"}
          data-testid={MASTER.phoneNormalize}>
          <Wand2 className="mr-1.5 h-4 w-4" /> Rapikan sekali jalan ({data.total_pending})
        </Button>
      </div>
      {clean ? (
        <p className="mt-3 text-sm text-emerald-800" data-testid={MASTER.phoneClean}>Semua nomor sudah berformat +62.</p>
      ) : (
        <div className="mt-3 overflow-hidden">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Koleksi</TableHead><TableHead className="text-right">Bisa dirapikan</TableHead>
              <TableHead className="text-right">Akan ganda (dilewati)</TableHead>
              <TableHead className="text-right">Tidak valid</TableHead><TableHead>Contoh tidak valid</TableHead>
              <TableHead className="text-right">Tindak lanjut</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.rows.filter((r) => r.pending || r.duplicate || r.invalid).map((r) => (
                <TableRow key={r.collection} data-testid={`${MASTER.phoneRow}-${r.collection}`}>
                  <TableCell className="text-sm">{r.collection}.{r.field}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.pending}</TableCell>
                  <TableCell className="text-right tabular-nums text-amber-700">{r.duplicate}</TableCell>
                  <TableCell className="text-right tabular-nums text-rose-700">{r.invalid}</TableCell>
                  <TableCell className="font-mono text-xs">{r.invalid_samples.map((s) => s.phone).join(", ")}</TableCell>
                  <TableCell className="text-right">
                    {r.duplicate || r.invalid ? (
                      <Button size="sm" variant="outline" onClick={() => setFixColl(r.collection)}
                        data-testid={`${MASTER.phoneFixBtn}-${r.collection}`}>
                        <Wrench className="h-3.5 w-3.5" /> Perbaiki ({r.duplicate + r.invalid})
                      </Button>
                    ) : <span className="text-xs text-muted-foreground">—</span>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <PhoneFixDialog row={fixRow} open={!!fixRow} onOpenChange={(o) => { if (!o) setFixColl(null); }}
        onUpdated={(after) => setData(after)} />
    </div>
  );
}
