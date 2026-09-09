import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Eye, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import SimpleMarkdown from "@/components/legal/SimpleMarkdown";
import api from "@/services/apiClient";
import { LEGAL } from "@/constants/testIds";

const IDENTITY = [
  ["company_name", "Nama perusahaan (badan hukum)"], ["brand", "Nama merek / proyek"],
  ["address", "Alamat"], ["email", "Email kontak"], ["phone", "Telepon / WhatsApp"],
  ["dpo_name", "Penanggung jawab pelindungan data"], ["effective_date", "Tanggal berlaku (YYYY-MM-DD)"],
];
const PAGES = [["privacy", "Kebijakan Privasi"], ["terms", "Syarat & Ketentuan"], ["deletion", "Penghapusan Data"]];
const PLACEHOLDERS = "{company} {brand} {address} {email} {phone} {dpo} {domain} {effective_date}";

export default function LegalSettingsForm({ editable }) {
  const [identity, setIdentity] = useState(null);
  const [texts, setTexts] = useState({});
  const [lang, setLang] = useState("id");
  const [page, setPage] = useState("privacy");
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/legal/settings").then((r) => { setIdentity(r.data.data.identity); setTexts(r.data.data.texts || {}); })
      .catch((e) => toast.error(e?.response?.data?.detail || "Gagal memuat pengaturan legal."));
  }, []);

  const custom = texts?.[lang]?.[page] || "";
  const setCustom = (v) => setTexts((t) => ({ ...t, [lang]: { ...(t[lang] || {}), [page]: v } }));

  const save = async () => {
    setSaving(true);
    try {
      const r = await api.put("/legal/settings", { identity, texts });
      setIdentity(r.data.data.identity); setTexts(r.data.data.texts || {});
      toast.success("Pengaturan legal tersimpan — halaman publik langsung berubah.");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan."); }
    finally { setSaving(false); }
  };

  const doPreview = async () => {
    try {
      const r = await api.get("/legal/preview", { params: { lang, public_base: window.location.origin } });
      setPreview(r.data.data.pages[page].content);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memuat pratinjau."); }
  };

  if (!identity) return <p className="text-sm text-muted-foreground">Memuat…</p>;
  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <div className="space-y-4 lg:col-span-2">
        <div className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
          <h3 className="section-title">Identitas perusahaan</h3>
          <p className="text-[11px] text-muted-foreground">Mengisi placeholder di template bawaan. Kosong = tanda "-".</p>
          {IDENTITY.map(([k, label]) => (
            <div key={k} className="space-y-1">
              <Label htmlFor={`legal-${k}`} className="text-xs">{label}</Label>
              <Input data-testid={LEGAL.identityField} data-field={k} id={`legal-${k}`} value={identity[k] || ""}
                disabled={!editable} onChange={(e) => setIdentity((s) => ({ ...s, [k]: e.target.value }))} />
            </div>
          ))}
        </div>
      </div>
      <div className="space-y-3 lg:col-span-3">
        <div className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="section-title">Teks halaman</h3>
            <Tabs value={lang} onValueChange={setLang}><TabsList>
              <TabsTrigger data-testid={LEGAL.textLang} data-lang="id" value="id">Indonesia</TabsTrigger>
              <TabsTrigger data-testid={LEGAL.textLang} data-lang="en" value="en">English</TabsTrigger>
            </TabsList></Tabs>
          </div>
          <Tabs value={page} onValueChange={(v) => { setPage(v); setPreview(null); }}><TabsList className="flex-wrap">
            {PAGES.map(([k, l]) => <TabsTrigger key={k} data-testid={LEGAL.textPage} data-page={k} value={k}>{l}</TabsTrigger>)}
          </TabsList></Tabs>
          <p className="text-[11px] text-muted-foreground">
            Kosongkan untuk memakai <b>template bawaan</b> (UU PDP + kebijakan WhatsApp/Meta). Markdown ringan
            didukung; placeholder tersedia: <code className="break-all">{PLACEHOLDERS}</code>.
            {custom ? <span data-testid={LEGAL.textCustomBadge} className="ml-1 rounded border border-amber-300 bg-amber-50 px-1 text-amber-800">teks kustom aktif</span> : null}
          </p>
          <Textarea data-testid={LEGAL.textArea} rows={14} value={custom} disabled={!editable} onChange={(e) => setCustom(e.target.value)}
            placeholder="(memakai template bawaan — tulis di sini untuk menggantinya)" className="font-mono text-xs" />
          <div className="flex flex-wrap items-center gap-2">
            {editable ? <Button data-testid={LEGAL.saveBtn} size="sm" onClick={save} disabled={saving}><Save className="mr-1.5 h-4 w-4" /> {saving ? "Menyimpan…" : "Simpan"}</Button> : null}
            <Button data-testid={LEGAL.previewBtn} size="sm" variant="outline" onClick={doPreview}><Eye className="mr-1.5 h-4 w-4" /> Pratinjau (versi tersimpan)</Button>
          </div>
        </div>
        {preview !== null ? (
          <div data-testid={LEGAL.previewBox} className="max-h-[520px] overflow-y-auto rounded-xl border bg-card p-5 shadow-[var(--shadow-card)]">
            <SimpleMarkdown text={preview} className="text-sm" />
          </div>
        ) : null}
      </div>
    </div>
  );
}
