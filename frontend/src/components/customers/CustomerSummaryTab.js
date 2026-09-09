import React, { useRef, useState } from "react";
import { toast } from "sonner";
import { FileText, ShieldCheck, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import api, { API, TOKEN_KEY } from "@/services/apiClient";
import { CUSTOMERS, CUSTPROFILE } from "@/constants/testIds";

const DOC_TYPES = [
  { v: "ktp", l: "KTP" }, { v: "npwp", l: "NPWP" }, { v: "kk", l: "Kartu Keluarga" },
  { v: "slip_gaji", l: "Slip Gaji" }, { v: "rekening", l: "Rekening Koran" },
  { v: "lainnya", l: "Lainnya" },
];

function Field({ label, value }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-sm">{value ?? "-"}</p>
    </div>
  );
}

/**
 * CustomerSummaryTab — identitas + KYC + berkas KYC bebas (lampiran).
 *
 * Catatan jujur yang dipertahankan dari fase sebelumnya: berkas di sini BERBEDA dari
 * checklist “Dokumen & Legal” — lampiran KYC tidak punya status verifikasi/penolakan.
 * Konsolidasi dua sistem dokumen pelanggan (docs/v2/26) BELUM dikerjakan; keduanya sengaja
 * dibedakan di layar supaya tidak ada yang menyangka lampiran KYC sudah terverifikasi.
 */
export default function CustomerSummaryTab({ customer, onChanged }) {
  const [docType, setDocType] = useState("ktp");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const onPickFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("doc_type", docType);
      await api.post(`/customers/${customer.id}/kyc`, fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Dokumen KYC diunggah.");
      onChanged?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Gagal mengunggah dokumen.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const fileUrl = (fid) => `${API}/files/${fid}?auth=${localStorage.getItem(TOKEN_KEY)}`;

  return (
    <div data-testid={CUSTPROFILE.summary} className="space-y-4">
      <section className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 font-heading text-base font-semibold">
            <ShieldCheck className="h-4 w-4 text-primary" /> Identitas & KYC
          </h2>
          <StatusPill status={customer.kyc_status}
            label={customer.kyc_status === "submitted" ? "KYC Terkirim" : "KYC Pending"} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Telepon" value={customer.phone} />
          <Field label="Email" value={customer.email} />
          <Field label="NIK" value={customer.nik} />
          <Field label="NPWP" value={customer.npwp} />
          <Field label="Pekerjaan" value={customer.occupation} />
          <Field label="Penghasilan/bln"
            value={<MoneyText value={customer.monthly_income} />} />
          <Field label="Pasangan" value={customer.spouse_name} />
          <Field label="Ahli waris"
            value={customer.heir_name
              ? `${customer.heir_name} (${customer.heir_relation || "-"})` : "-"} />
          <Field label="Alamat" value={customer.address} />
        </div>
      </section>

      <section className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
        <h2 className="mb-3 flex items-center gap-2 font-heading text-base font-semibold">
          <FileText className="h-4 w-4 text-primary" /> Lampiran KYC
        </h2>
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1.5">
            <Label htmlFor="kyc-doctype" className="text-xs">Jenis dokumen</Label>
            <Select value={docType} onValueChange={setDocType}>
              <SelectTrigger id="kyc-doctype" data-testid={CUSTOMERS.kycDocType}
                className="h-9 w-40" aria-label="Jenis dokumen KYC">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DOC_TYPES.map((d) => <SelectItem key={d.v} value={d.v}>{d.l}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <input ref={fileRef} data-testid={CUSTOMERS.kycFileInput} type="file"
            className="hidden" onChange={onPickFile} aria-label="Pilih berkas KYC" />
          <Button data-testid={CUSTOMERS.kycUploadBtn} size="sm" disabled={uploading}
            onClick={() => fileRef.current?.click()}>
            <Upload className="mr-1.5 h-4 w-4" /> {uploading ? "Mengunggah…" : "Unggah Lampiran"}
          </Button>
        </div>
        <div className="mt-3 space-y-2">
          {(customer.kyc_files || []).length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Belum ada lampiran KYC. Dokumen yang WAJIB terverifikasi ada di tab
              “Dokumen & Legal”.
            </p>
          ) : customer.kyc_files.map((f) => (
            <div key={f.file_id} data-testid={CUSTOMERS.kycFileRow}
              className="flex items-center justify-between rounded-lg border bg-background px-3 py-2 text-sm">
              <span>
                <StatusPill status="info" label={(f.doc_type || "dok").toUpperCase()} />
                <span className="ml-2">{f.original_filename}</span>
              </span>
              <a className="text-primary hover:underline" href={fileUrl(f.file_id)}
                target="_blank" rel="noreferrer">Lihat</a>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
