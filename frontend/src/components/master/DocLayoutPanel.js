import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, Eye, RotateCcw, Save } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import BrandForm from "@/components/master/docLayout/BrandForm";
import RowsForm from "@/components/master/docLayout/RowsForm";
import ScriptForm from "@/components/master/docLayout/ScriptForm";
import SignaturesForm from "@/components/master/docLayout/SignaturesForm";
import TableForm from "@/components/master/docLayout/TableForm";
import { DocumentPreview } from "@/components/master/docLayout/DocumentPreview";
import { P60 } from "@/constants/testIds";

/**
 * DocLayoutPanel — SATU layar untuk SATU jenis dokumen (Fase 60, disatukan di Fase 66).
 *
 * Sebelum Fase 66 layar ini terbelah dua tab: "Isi template (naskah)" dengan kode bebas dan
 * "Tampilan & kop surat" per dokumen. Akibatnya tidak ada yang tahu naskah mana yang dipakai
 * dokumen mana, dan pratinjau hanya menampilkan kop — naskahnya tidak pernah terlihat.
 *
 * Sekarang: pilih jenis dokumen sekali, lalu setel **naskah**, **kop & kertas**,
 * **baris biaya**, **gaya tabel**, dan **tanda tangan** di tempat yang sama, dengan
 * PRATINJAU yang memakai mesin cetak yang sama DAN naskah yang sedang disunting.
 */
export default function DocLayoutPanel() {
  const { can } = useAuth();
  const mayEdit = can("settings", "update");
  const [targets, setTargets] = useState([]);
  const [code, setCode] = useState("__default__");
  const [layout, setLayout] = useState(null);
  const [script, setScript] = useState(null);
  const [naskah, setNaskah] = useState("");
  const [savingScript, setSavingScript] = useState(false);
  const [state, setState] = useState({ loading: true, error: "" });
  const [preview, setPreview] = useState({ url: "", error: "", busy: false });
  const [dirty, setDirty] = useState(false);
  const timer = useRef(null);

  const load = useCallback(async () => {
    setState({ loading: true, error: "" });
    try {
      const [t, l, s] = await Promise.all([
        api.get("/doc-layouts"), api.get(`/doc-layouts/${code}`),
        api.get(`/doc-layouts/${code}/script`)]);
      setTargets(t.data.data || []);
      setLayout(l.data.data);
      setScript(s.data.data);
      setNaskah(s.data.data?.content || "");
      setDirty(false);
      setState({ loading: false, error: "" });
    } catch (e) {
      setState({ loading: false,
        error: e?.response?.data?.detail || "Gagal memuat konfigurasi dokumen." });
    }
  }, [code]);

  useEffect(() => { if (mayEdit) load(); }, [mayEdit, load]);

  const draft = useMemo(() => (layout ? {
    brand: layout.brand, sections: layout.sections, money_rows: layout.money_rows,
    signatures: layout.signatures, options: layout.options, table: layout.table,
  } : null), [layout]);

  const renderPreview = useCallback(async (withReal) => {
    if (!draft) return;
    setPreview((p) => ({ ...p, busy: true, error: "" }));
    try {
      const res = await api.post(`/doc-layouts/${code}/preview`,
        { ...draft, script: naskah }, {
          params: withReal ? { document_id: withReal } : {}, responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      setPreview((p) => {
        if (p.url) URL.revokeObjectURL(p.url);  // satu blob per pratinjau, bukan menumpuk
        return { url, error: "", busy: false };
      });
    } catch (e) {
      setPreview({ url: "", busy: false,
        error: "Pratinjau gagal dirender. Periksa nilai warna/margin, lalu coba lagi." });
    }
  }, [code, draft, naskah]);

  // Pratinjau ikut berubah saat pengaturan ATAU naskah diubah (ditahan 700 ms supaya tidak
  // merender ulang pada setiap ketikan).
  useEffect(() => {
    if (!draft) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => renderPreview(null), 700);
    return () => clearTimeout(timer.current);
  }, [draft, naskah, renderPreview]);

  if (!mayEdit) {
    return (
      <p data-testid={P60.denied} className="rounded-lg border bg-secondary/40 px-3 py-2 text-[12px] text-muted-foreground">
        Konfigurasi dokumen (naskah, kop surat, gaya tabel) hanya bisa diubah peran yang
        berwenang atas pengaturan organisasi.
        Ini soal HAK AKSES, bukan fitur yang belum ada.
      </p>
    );
  }
  if (state.loading) return <LoadingCards count={3} />;
  if (state.error) return <ErrorState message={state.error} onRetry={load} />;
  if (!layout) return null;

  const setPart = (part) => (key, value) => {
    setLayout((l) => ({ ...l, [part]: { ...(l[part] || {}), [key]: value } }));
    setDirty(true);
  };
  const setList = (part) => (value) => {
    setLayout((l) => ({ ...l, [part]: value }));
    setDirty(true);
  };

  const simpan = async () => {
    try {
      const res = await api.put(`/doc-layouts/${code}`, draft);
      setLayout(res.data.data);
      setDirty(false);
      toast.success("Konfigurasi dokumen disimpan — dokumen berikutnya memakai tampilan ini.");
      const t = await api.get("/doc-layouts");
      setTargets(t.data.data || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan konfigurasi.");
    }
  };

  const simpanNaskah = async () => {
    setSavingScript(true);
    try {
      const res = await api.put(`/doc-layouts/${code}/script`, { content: naskah });
      setScript(res.data.data);
      setNaskah(res.data.data?.content || "");
      toast.success("Naskah dokumen disimpan — dokumen berikutnya memakai naskah ini.");
      const t = await api.get("/doc-layouts");
      setTargets(t.data.data || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan naskah.");
    } finally { setSavingScript(false); }
  };

  const reset = async () => {
    try {
      const res = await api.delete(`/doc-layouts/${code}`);
      setLayout(res.data.data);
      setDirty(false);
      toast.success("Tampilan dikembalikan ke bawaan. Dokumen yang sudah terbit tidak berubah.");
    } catch (e) {
      toast.error("Gagal mengembalikan ke bawaan.");
    }
  };

  const unduh = () => {
    if (!preview.url) return;
    const a = document.createElement("a");
    a.href = preview.url;
    a.download = `contoh-${code}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
  };

  // Dikelompokkan per KATEGORI dokumen supaya daftarnya bisa dibaca, bukan 20 baris rata.
  const grup = targets.reduce((acc, t) => {
    const k = t.category_label || "Dokumen lain";
    (acc[k] = acc[k] || []).push(t);
    return acc;
  }, {});

  return (
    <div data-testid={P60.panel} className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-full min-w-0 sm:w-[340px]">
          <p className="mb-1 text-[11px] text-muted-foreground">Jenis dokumen yang disetel</p>
          <Select value={code} onValueChange={setCode}>
            <SelectTrigger data-testid={P60.targetSelect} className="bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(grup).map(([kategori, items]) => (
                <SelectGroup key={kategori}>
                  <SelectLabel>{kategori}</SelectLabel>
                  {items.map((t) => (
                    <SelectItem key={t.code} value={t.code}>
                      {t.label}{t.customized ? " · tampilan disetel" : ""}
                      {t.has_script ? " · naskah ada" : ""}
                    </SelectItem>
                  ))}
                </SelectGroup>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" data-testid={P60.previewRefresh}
            onClick={() => renderPreview(null)} disabled={preview.busy}>
            <Eye className="mr-1.5 h-3.5 w-3.5" />
            {preview.busy ? "Merender…" : "Segarkan pratinjau"}
          </Button>
          <Button size="sm" variant="outline" data-testid={P60.previewDownload}
            onClick={unduh} disabled={!preview.url}>
            <Download className="mr-1.5 h-3.5 w-3.5" /> Unduh contoh
          </Button>
          <Button size="sm" variant="outline" data-testid={P60.resetBtn} onClick={reset}>
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Bawaan
          </Button>
          {dirty ? (
            <Button size="sm" data-testid={P60.saveBtn} onClick={simpan}>
              <Save className="mr-1.5 h-3.5 w-3.5" /> Simpan tampilan
            </Button>
          ) : (
            <span data-testid={P60.saveBtn}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 text-xs font-semibold text-emerald-800">
              <Save className="h-3.5 w-3.5" /> Tersimpan
            </span>
          )}
        </div>
      </div>

      <p className="text-[12px] text-muted-foreground">
        {code === "__default__"
          ? "Identitas & gaya di sini dipakai SEMUA dokumen. Pilih jenis dokumen di atas untuk menyetel naskah dan menimpa tampilannya (mis. kolom tanda tangan BAST berbeda dari SPR)."
          : `Naskah dan tampilan di sini hanya berlaku untuk "${layout.label}" dan menimpa bawaan organisasi.`}
      </p>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="min-w-0 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
          <Tabs defaultValue="script">
            <TabsList className="h-auto flex-wrap justify-start">
              <TabsTrigger data-testid={P60.tabScript} value="script">Naskah</TabsTrigger>
              <TabsTrigger data-testid={P60.tabBrand} value="brand">Kop, footer &amp; kertas</TabsTrigger>
              <TabsTrigger data-testid={P60.tabRows} value="rows">Baris &amp; biaya</TabsTrigger>
              <TabsTrigger data-testid={P60.tabTable} value="table">Tabel</TabsTrigger>
              <TabsTrigger data-testid={P60.tabSign} value="sign">Tanda tangan</TabsTrigger>
            </TabsList>
            <TabsContent value="script" className="mt-3">
              <ScriptForm script={script} content={naskah} onChange={setNaskah}
                onSave={simpanNaskah} saving={savingScript}
                onUseDefault={() => setNaskah(script?.default_content
                  || script?.content || "")} />
            </TabsContent>
            <TabsContent value="brand" className="mt-3">
              <BrandForm brand={layout.brand || {}} options={layout.options || {}}
                setBrand={setPart("brand")} setOptions={setPart("options")} />
            </TabsContent>
            <TabsContent value="rows" className="mt-3">
              <RowsForm rows={layout.money_rows || []} sections={layout.sections || []}
                options={layout.options || {}} setRows={setList("money_rows")}
                setSections={setList("sections")} setOptions={setPart("options")} />
            </TabsContent>
            <TabsContent value="table" className="mt-3">
              <TableForm table={layout.table || {}} setTable={setPart("table")} />
            </TabsContent>
            <TabsContent value="sign" className="mt-3">
              <SignaturesForm signatures={layout.signatures || []}
                options={layout.options || {}} setSignatures={setList("signatures")}
                setOptions={setPart("options")} />
            </TabsContent>
          </Tabs>
        </div>

        <div className="min-w-0 space-y-2">
          <p className="text-[12px] font-medium">
            Pratinjau langsung — naskah + tampilan, dirender mesin cetak yang sama dengan
            dokumen sungguhan (data contoh)
          </p>
          {preview.error ? (
            <p data-testid={P60.previewError}
              className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-800">
              {preview.error}
            </p>
          ) : null}
          <div>
            {preview.url ? (
              <DocumentPreview url={preview.url} />
            ) : (
              <div data-testid={P60.preview} className="flex h-[720px] items-center justify-center text-[12px] text-muted-foreground">
                {preview.busy ? "Merender pratinjau…" : "Pratinjau belum tersedia."}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
