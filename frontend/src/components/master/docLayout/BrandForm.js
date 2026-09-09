import React from "react";
import { Upload, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { P60 } from "@/constants/testIds";

/** Unggah gambar layout (logo/kop/footer/watermark/cap) — memakai penyimpanan berkas yang
 *  sudah ada (`/files/upload`), tanpa optimasi supaya logo vektor-rasteran tetap tajam. */
export async function uploadImage(file) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("owner_type", "doc_layout");
  fd.append("optimize", "false");
  const res = await api.post("/files/upload", fd,
    { headers: { "Content-Type": "multipart/form-data" } });
  return res.data.data.id;
}

export function ImageField({ label, testId, value, onChange, hint }) {
  const [busy, setBusy] = React.useState(false);
  const pick = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      onChange(await uploadImage(file));
      toast.success(`${label} diunggah.`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || `Gagal mengunggah ${label}.`);
    } finally { setBusy(false); }
  };
  return (
    <div className="space-y-1">
      <Label className="text-[11px]">{label}</Label>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" asChild disabled={busy}>
          <label data-testid={testId} className="cursor-pointer">
            <Upload className="mr-1.5 h-3.5 w-3.5 inline" />
            {busy ? "Mengunggah…" : value ? "Ganti" : "Unggah"}
            <input type="file" accept="image/*" className="hidden" onChange={pick} />
          </label>
        </Button>
        {value ? (
          <>
            <img alt={label} className="h-8 rounded border bg-white object-contain px-1"
              src={`${process.env.REACT_APP_BACKEND_URL}/api/files/${value}?auth=${localStorage.getItem("sipro_token")}`} />
            <Button size="icon" variant="ghost" onClick={() => onChange(null)}
              aria-label={`Hapus ${label}`}><X className="h-3.5 w-3.5" /></Button>
          </>
        ) : <span className="text-[11px] text-muted-foreground">{hint}</span>}
      </div>
    </div>
  );
}

const MODES = [["system", "Dirakit sistem (identitas + logo)"],
  ["image", "Gambar sendiri (desain)"], ["none", "Tidak ada"]];

/** BrandForm — identitas perusahaan, kop, footer, watermark, kertas & margin. */
export default function BrandForm({ brand, options, setBrand, setOptions }) {
  const f = (k) => (e) => setBrand(k, e.target.value);
  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <div>
          <Label htmlFor="dl-company" className="text-[11px]">Nama perusahaan</Label>
          <Input id="dl-company" data-testid={P60.companyName} className="bg-background"
            value={brand.company_name || ""} onChange={f("company_name")} />
        </div>
        <div>
          <Label className="text-[11px]">Tagline / bidang usaha</Label>
          <ReferenceSelect group="business_field" testId="doc-layout-tagline"
            className="bg-background" value={brand.tagline || ""}
            onChange={(v) => setBrand("tagline", v)} />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="dl-address" className="text-[11px]">Alamat kantor</Label>
          <Input id="dl-address" data-testid={P60.address} className="bg-background"
            value={brand.address || ""} onChange={f("address")} />
        </div>
        <div>
          <Label htmlFor="dl-phone" className="text-[11px]">Telepon</Label>
          <Input id="dl-phone" data-testid={P60.phone} className="bg-background"
            value={brand.phone || ""} onChange={f("phone")} />
        </div>
        <div>
          <Label htmlFor="dl-email" className="text-[11px]">Email</Label>
          <Input id="dl-email" data-testid={P60.email} className="bg-background"
            value={brand.email || ""} onChange={f("email")} />
        </div>
        <div>
          <Label htmlFor="dl-web" className="text-[11px]">Situs web</Label>
          <Input id="dl-web" data-testid={P60.website} className="bg-background"
            value={brand.website || ""} onChange={f("website")} />
        </div>
        <div>
          <Label htmlFor="dl-npwp" className="text-[11px]">NPWP</Label>
          <Input id="dl-npwp" data-testid={P60.npwp} className="bg-background"
            value={brand.npwp || ""} onChange={f("npwp")} />
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <div>
          <Label className="text-[11px]">Mode kop surat</Label>
          <Select value={brand.header_mode || "system"}
            onValueChange={(v) => setBrand("header_mode", v)}>
            <SelectTrigger data-testid={P60.headerMode} className="bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-[11px]">Mode footer</Label>
          <Select value={brand.footer_mode || "system"}
            onValueChange={(v) => setBrand("footer_mode", v)}>
            <SelectTrigger data-testid={P60.footerMode} className="bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <ImageField label="Logo perusahaan" testId={P60.logoUpload}
          value={brand.logo_file_id} hint="PNG latar transparan"
          onChange={(v) => setBrand("logo_file_id", v)} />
        <ImageField label="Gambar kop (mode desain)" testId={P60.headerUpload}
          value={brand.header_image_file_id} hint="dipakai bila mode = gambar"
          onChange={(v) => setBrand("header_image_file_id", v)} />
        <ImageField label="Gambar footer" testId={P60.footerUpload}
          value={brand.footer_image_file_id} hint="dipakai bila mode = gambar"
          onChange={(v) => setBrand("footer_image_file_id", v)} />
        <ImageField label="Watermark (gambar)" value={brand.watermark_file_id}
          testId="doc-layout-watermark-upload" hint="mis. cap air logo"
          onChange={(v) => setBrand("watermark_file_id", v)} />
      </div>

      <div>
        <Label htmlFor="dl-footer-text" className="text-[11px]">
          Teks footer (kosongkan = dirakit dari identitas di atas)
        </Label>
        <Textarea id="dl-footer-text" data-testid={P60.footerText} rows={2}
          className="bg-background" value={brand.footer_text || ""}
          onChange={f("footer_text")} />
      </div>

      <div className="grid gap-2 sm:grid-cols-4">
        <div>
          <Label htmlFor="dl-accent" className="text-[11px]">Warna aksen</Label>
          <Input id="dl-accent" data-testid={P60.accent} type="color" className="h-9 bg-background"
            value={brand.accent_color || "#0f766e"} onChange={f("accent_color")} />
        </div>
        <div>
          <Label htmlFor="dl-wm" className="text-[11px]">Watermark teks</Label>
          <Input id="dl-wm" data-testid={P60.watermarkText} className="bg-background"
            placeholder="mis. SALINAN" value={brand.watermark_text || ""}
            onChange={f("watermark_text")} />
        </div>
        <div>
          <Label className="text-[11px]">Ukuran kertas</Label>
          <Select value={brand.paper || "A4"} onValueChange={(v) => setBrand("paper", v)}>
            <SelectTrigger data-testid={P60.paper} className="bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {["A4", "LETTER", "LEGAL"].map((v) => (
                <SelectItem key={v} value={v}>{v}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="dl-mt" className="text-[11px]">Margin atas (mm)</Label>
          <Input id="dl-mt" data-testid={P60.marginTop} type="number" min={8} max={60}
            className="bg-background" value={brand.margin_top_mm ?? 32}
            onChange={(e) => setBrand("margin_top_mm", Number(e.target.value))} />
        </div>
      </div>

      <label className="flex items-center gap-2 text-[12px]">
        <input type="checkbox" checked={brand.show_page_numbers !== false}
          onChange={(e) => setBrand("show_page_numbers", e.target.checked)} />
        Cetak nomor halaman di footer
      </label>
      <div>
        <Label htmlFor="dl-closing" className="text-[11px]">
          Kalimat penutup dokumen (opsional)
        </Label>
        <Textarea id="dl-closing" rows={2} className="bg-background"
          value={options.closing_note || ""}
          onChange={(e) => setOptions("closing_note", e.target.value)} />
      </div>
    </div>
  );
}
