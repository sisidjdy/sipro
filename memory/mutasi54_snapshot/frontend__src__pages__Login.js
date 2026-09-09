import React, { useState } from "react";
import { Building2, LogIn, AlertCircle, Clock, CornerDownLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { SESSION_END_MESSAGE, SESSION_STATE, peekReturnTo } from "@/services/sessionBus";
import { AUTH, P54 } from "@/constants/testIds";

/**
 * Daftar masuk-cepat demo. `slug` dipakai untuk data-testid agar stabil & tanpa spasi
 * (dulu testid dibentuk dari label sehingga "Super Admin" menghasilkan selector berspasi
 * dan peran admin/marketing/site sama sekali tidak punya tombol cepat).
 */
const QUICK = [
  { role: "Owner", slug: "owner", email: "owner@sipro.co.id" },
  { role: "Manajer", slug: "manajer", email: "manager@sipro.co.id" },
  { role: "Marketing", slug: "marketing", email: "marketing@sipro.co.id" },
  { role: "Sales", slug: "sales", email: "sales@sipro.co.id" },
  { role: "Finance", slug: "finance", email: "finance@sipro.co.id" },
  { role: "Proyek", slug: "proyek", email: "pm@sipro.co.id" },
  { role: "Site", slug: "site", email: "site@sipro.co.id" },
  { role: "Super Admin", slug: "superadmin", email: "superadmin@sipro.co.id" },
];

// Nama halaman yang manusiawi, supaya kalimat "kembali ke …" tidak memamerkan URL mentah.
function namaHalaman(path) {
  if (!path) return "";
  const bersih = path.split("?")[0].replace(/\/$/, "");
  const peta = {
    "/leads": "daftar lead", "/customers": "Customer & Kontrak", "/deals": "reservasi & deal",
    "/finance": "Keuangan", "/projects": "proyek", "/build": "hub Pembangunan",
    "/subcon": "Subkontraktor & SPK", "/documents": "dokumen", "/tax": "pajak",
    "/bi": "Analitik & BI", "/tasks": "tugas saya", "/automation": "otomasi & pengingat",
  };
  if (peta[bersih]) return peta[bersih];
  if (bersih.startsWith("/leads/")) return "profil lead yang sedang Anda buka";
  if (bersih.startsWith("/customers/")) return "profil pembeli yang sedang Anda buka";
  if (bersih.startsWith("/projects/")) return "proyek yang sedang Anda buka";
  if (bersih.startsWith("/units/")) return "unit yang sedang Anda buka";
  if (bersih.startsWith("/partners/")) return "profil mitra yang sedang Anda buka";
  return "halaman yang sedang Anda buka";
}

export default function Login() {
  const { login, sessionEndReason } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Hanya DILIHAT, bukan diambil: yang mengalihkan adalah `LoginRoute` (lihat App.js).
  const [returnTo] = useState(() => peekReturnTo());

  const submit = async (e, presetEmail) => {
    if (e) e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(presetEmail || email, presetEmail ? "Sipro#2026" : password);
      // TIDAK memanggil navigate() di sini. Begitu `user` terisi, `LoginRoute` mengalihkan
      // ke tujuan kembali yang tercatat — satu tempat pengalihan, tanpa lomba.
    } catch (err) {
      setError(err?.response?.data?.detail || "Gagal masuk. Periksa email & kata sandi.");
      setBusy(false);
    }
  };

  const catatanSesi = sessionEndReason && sessionEndReason !== SESSION_STATE.missing
    ? SESSION_END_MESSAGE[sessionEndReason] || SESSION_END_MESSAGE[SESSION_STATE.expired]
    : null;

  return (
    <div className="flex min-h-screen items-center justify-center app-noise bg-background px-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Building2 className="h-6 w-6" />
          </div>
          <div>
            <p className="font-heading text-xl font-bold tracking-tight">SIPRO</p>
            <p className="text-xs text-muted-foreground">Property Development OS — PT SIPRO Land</p>
          </div>
        </div>

        <div className="rounded-2xl border bg-card p-6 shadow-sm">
          {/* Fase 54 — halaman masuk menjelaskan DIRINYA SENDIRI. Dulu pengguna yang sesinya
              habis mendadak berada di sini tanpa sebab: ia mengira aplikasinya rusak atau
              sandinya salah. */}
          {catatanSesi ? (
            <div data-testid={P54.loginSessionNotice}
              className="mb-4 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 text-sm text-amber-900">
              <Clock className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{catatanSesi}</span>
            </div>
          ) : null}

          <h1 className="font-heading text-lg font-semibold">Masuk ke akun Anda</h1>
          <p className="mt-1 text-sm text-muted-foreground">Gunakan email kerja Anda untuk melanjutkan.</p>

          <form data-testid={AUTH.loginForm} onSubmit={submit} className="mt-5 space-y-4">
            {error ? (
              <div data-testid={AUTH.errorAlert} className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
                <AlertCircle className="h-4 w-4 shrink-0" /> {error}
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input data-testid={AUTH.emailInput} id="email" type="email" autoComplete="username"
                placeholder="nama@sipro.co.id" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Kata Sandi</Label>
              <Input data-testid={AUTH.passwordInput} id="password" type="password" autoComplete="current-password"
                placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
            <Button data-testid={AUTH.submitButton} type="submit" className="w-full" disabled={busy}>
              <LogIn className="h-4 w-4 mr-2" /> {busy ? "Memproses..." : "Masuk"}
            </Button>
            {returnTo ? (
              <p data-testid={P54.loginReturnTo}
                className="flex items-start gap-1.5 text-xs text-muted-foreground">
                <CornerDownLeft className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Setelah masuk, Anda dibawa kembali ke {namaHalaman(returnTo)}.
              </p>
            ) : null}
          </form>

          <div className="mt-5 border-t pt-4">
            <p className="text-xs font-medium text-muted-foreground">Masuk cepat (akun demo · kata sandi Sipro#2026)</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {QUICK.map((q) => (
                <button key={q.email} type="button" disabled={busy}
                  data-testid={`${AUTH.quickLoginPrefix}-${q.slug}`}
                  data-role-slug={q.slug}
                  aria-label={`Masuk cepat sebagai ${q.role}`}
                  title={`${q.role} — ${q.email}`}
                  onClick={() => submit(null, q.email)}
                  className="rounded-full border bg-secondary px-3 py-1 text-xs font-medium hover:bg-accent transition-colors disabled:opacity-50">
                  {q.role}
                </button>
              ))}
            </div>
          </div>
        </div>
        <p className="mt-4 text-center text-[11px] text-muted-foreground">
          Akun demo hanya untuk pengujian internal.
        </p>
      </div>
    </div>
  );
}
