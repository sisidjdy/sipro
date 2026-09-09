import React, { useState } from "react";
import { toast } from "sonner";
import { KeyRound, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { PROFILE } from "@/constants/testIds";

export function ProfileForm() {
  const { user, refresh } = useAuth();
  const [name, setName] = useState(user?.name || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [busy, setBusy] = useState(false);
  const dirty = name !== (user?.name || "") || phone !== (user?.phone || "");
  const save = async () => {
    setBusy(true);
    try {
      await api.put("/auth/me", { name, phone });
      await refresh();
      toast.success("Profil tersimpan.");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan profil."); }
    finally { setBusy(false); }
  };
  return (
    <div className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <h3 className="section-title">Data diri</h3>
      <div className="space-y-1.5"><Label htmlFor="pf-name">Nama lengkap</Label>
        <Input data-testid={PROFILE.nameInput} id="pf-name" value={name} onChange={(e) => setName(e.target.value)} /></div>
      <div className="space-y-1.5"><Label htmlFor="pf-phone">Telepon / WhatsApp</Label>
        <Input data-testid={PROFILE.phoneInput} id="pf-phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+628…" /></div>
      <p className="text-[11px] text-muted-foreground">Email, peran, dan status akun hanya bisa diubah oleh admin (Admin › Pengguna).</p>
      <Button data-testid={PROFILE.saveBtn} size="sm" onClick={save} disabled={!dirty || busy || name.trim().length < 2}>
        <Save className="mr-1.5 h-4 w-4" /> {busy ? "Menyimpan…" : "Simpan"}
      </Button>
    </div>
  );
}

export function PasswordForm() {
  const [f, setF] = useState({ cur: "", nw: "", cf: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault(); setErr("");
    if (f.nw.length < 6) { setErr("Kata sandi baru minimal 6 karakter."); return; }
    if (f.nw !== f.cf) { setErr("Konfirmasi kata sandi tidak sama."); return; }
    setBusy(true);
    try {
      await api.post("/auth/me/password", { current_password: f.cur, new_password: f.nw });
      toast.success("Kata sandi berhasil diubah.");
      setF({ cur: "", nw: "", cf: "" });
    } catch (er) { setErr(er?.response?.data?.detail || "Gagal mengubah kata sandi."); }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <h3 className="section-title flex items-center gap-1.5"><KeyRound className="h-4 w-4 text-primary" /> Ganti kata sandi</h3>
      {err ? <p data-testid={PROFILE.pwError} className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">{err}</p> : null}
      <div className="space-y-1.5"><Label htmlFor="pw-cur">Kata sandi saat ini</Label>
        <Input data-testid={PROFILE.pwCurrent} id="pw-cur" type="password" autoComplete="current-password" value={f.cur} onChange={set("cur")} required /></div>
      <div className="space-y-1.5"><Label htmlFor="pw-new">Kata sandi baru</Label>
        <Input data-testid={PROFILE.pwNew} id="pw-new" type="password" autoComplete="new-password" value={f.nw} onChange={set("nw")} required /></div>
      <div className="space-y-1.5"><Label htmlFor="pw-cf">Ulangi kata sandi baru</Label>
        <Input data-testid={PROFILE.pwConfirm} id="pw-cf" type="password" autoComplete="new-password" value={f.cf} onChange={set("cf")} required /></div>
      <Button data-testid={PROFILE.pwSubmit} size="sm" type="submit" disabled={busy || !f.cur || !f.nw || !f.cf}>{busy ? "Menyimpan…" : "Ubah kata sandi"}</Button>
    </form>
  );
}
