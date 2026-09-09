import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, MessageSquareWarning } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatDateWIB } from "@/utils/formatters";
import portalApi from "@/services/portalClient";
import { PORTAL } from "@/constants/testIds";


export default function ComplaintsPanel() {
  const [data, setData] = useState(null);
  const [cats, setCats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ subject: "", message: "", category: "konstruksi", priority: "medium" });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const load = async () => {
    setLoading(true); setError("");
    try {
      // Kategori diambil dari SSOT portal (Fase 26) — dulu daftarnya hardcode & menyimpang
      // dari nilai kanonik backend.
      const [res, refRes] = await Promise.all([
        portalApi.get("/portal/complaints"),
        portalApi.get("/portal/reference").catch(() => ({ data: { data: {} } })),
      ]);
      setData(res.data.data || []);
      setCats(refRes.data?.data?.complaint_category?.options || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat komplain.");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!form.subject || !form.message) { toast.error("Judul & pesan wajib diisi."); return; }
    setBusy(true);
    try {
      await portalApi.post("/portal/complaints", form);
      toast.success("Komplain terkirim. Kami tindaklanjuti (SLA 2x24 jam).");
      setOpen(false);
      setForm({ subject: "", message: "", category: "konstruksi", priority: "medium" });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengirim komplain.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid={PORTAL.complaintsPanel} className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="section-title">Komplain & Bantuan</h2>
        <Button data-testid={PORTAL.complaintAddBtn} size="sm" onClick={() => setOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Ajukan Komplain
        </Button>
      </div>

      {loading ? <LoadingCards count={2} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !data?.length ? (
          <p className="rounded-xl border bg-white p-6 text-center text-sm text-slate-500">Belum ada komplain. Semoga semuanya lancar!</p>
        ) : (
          <div className="space-y-3">
            {data.map((c) => (
              <div key={c.id} data-testid={PORTAL.complaintRow} className="rounded-xl border bg-white p-4">
                <div className="flex items-center justify-between">
                  <p className="font-medium">{c.subject}</p>
                  <StatusPill status={c.status} label={c.status === "resolved" ? "Selesai" : c.status === "in_progress" ? "Diproses" : "Terbuka"} />
                </div>
                <p className="mt-1 text-sm text-slate-600">{c.message}</p>
                <p className="mt-1 text-xs text-slate-400">{c.category} · {formatDateWIB(c.created_at)}</p>
                {(c.responses || []).map((r, i) => (
                  <div key={i} className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">
                    <span className="text-slate-500">Balasan:</span> {r.message}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ajukan Komplain</DialogTitle>
            <DialogDescription>Tim kami akan menindaklanjuti sesuai SLA 2x24 jam.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Kategori</Label>
              <Select value={form.category} onValueChange={(v) => set("category", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{cats.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label htmlFor="subj">Judul</Label>
              <Input id="subj" value={form.subject} onChange={(e) => set("subject", e.target.value)} placeholder="mis. Rembes di plafon kamar" /></div>
            <div className="space-y-1.5"><Label htmlFor="msg">Pesan</Label>
              <Textarea id="msg" rows={3} value={form.message} onChange={(e) => set("message", e.target.value)} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Batal</Button>
            <Button data-testid={PORTAL.complaintSubmit} onClick={submit} disabled={busy}>{busy ? "Mengirim…" : "Kirim Komplain"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
