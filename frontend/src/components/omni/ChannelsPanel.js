import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Radio } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { OMNI } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";


export default function ChannelsPanel() {
  const { options, labelOf } = useReference();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ code: "", channel: "whatsapp", name: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/channels");
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat channel.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const toggle = async (c) => {
    try { await api.put(`/channels/${c.id}`, { is_active: !c.is_active }); load(); }
    catch { toast.error("Gagal mengubah status channel."); }
  };

  const save = async () => {
    if (!form.code.trim() || !form.name.trim()) { toast.error("Kode & nama channel wajib diisi."); return; }
    setBusy(true);
    try {
      await api.post("/channels", { code: form.code.trim(), channel: form.channel, name: form.name.trim() });
      toast.success("Channel ditambahkan (mode simulasi).");
      setOpen(false); setForm({ code: "", channel: "whatsapp", name: "" }); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menambah channel."); }
    finally { setBusy(false); }
  };

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Akun channel omnichannel. Semua <b>mode SIMULASI</b> (aktifkan nyata saat kredensial tersedia).</p>
        <Button data-testid={OMNI.channelAddBtn} size="sm" onClick={() => setOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Tambah Channel
        </Button>
      </div>

      {!rows.length ? (
        <EmptyState icon={Radio} title="Belum ada channel" description="Tambahkan akun channel pertama." />
      ) : (
        <div className="grid gap-2 md:grid-cols-2">
          {rows.map((c) => (
            <div key={c.id} data-testid={OMNI.channelRow}
              className="flex items-center justify-between rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-medium">{c.name}</p>
                  <StatusPill status="simulation" />
                </div>
                <p className="text-[11px] text-muted-foreground">{labelOf("channel_type", c.channel)} &middot; kode: {c.code}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{c.is_active ? "Aktif" : "Nonaktif"}</span>
                <Switch data-testid={OMNI.channelToggle} checked={!!c.is_active} onCheckedChange={() => toggle(c)} />
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Tambah Channel</DialogTitle>
            <DialogDescription>Akun channel baru dibuat dalam mode simulasi.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="channelspanel-kode">Kode</Label>
              <Input id="channelspanel-kode" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="mis. wa_cs" />
            </div>
            <div className="space-y-1.5">
              <Label>Tipe Channel</Label>
              <Select value={form.channel} onValueChange={(v) => setForm({ ...form, channel: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{options("channel_type").map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="channelspanel-nama">Nama</Label>
              <Input id="channelspanel-nama" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="mis. WhatsApp CS" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Batal</Button>
            <Button data-testid={OMNI.channelSave} onClick={save} disabled={busy}>{busy ? "Menyimpan..." : "Simpan"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
