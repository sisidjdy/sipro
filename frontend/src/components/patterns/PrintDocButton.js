import React, { useState } from "react";
import { toast } from "sonner";
import { Printer } from "lucide-react";

import { Button } from "@/components/ui/button";
import api from "@/services/apiClient";

/**
 * Tombol cetak dokumen PDF (Fase 61) — dipakai SPK & PO.
 *
 * Membuka PDF di tab baru dan sekaligus menyediakan berkasnya, karena dokumen ini
 * dipegang pihak luar: subkontraktor menandatanganinya, vendor memakainya untuk mengirim.
 */
export default function PrintDocButton({ url, filename, testId, label = "Cetak PDF",
  variant = "outline" }) {
  const [busy, setBusy] = useState(false);
  const cetak = async () => {
    setBusy(true);
    try {
      const res = await api.get(url, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = `${filename}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.open(href, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(href), 60000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mencetak dokumen.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button size="sm" variant={variant} data-testid={testId} disabled={busy} onClick={cetak}>
      <Printer className="mr-1.5 h-4 w-4" /> {busy ? "Menyiapkan…" : label}
    </Button>
  );
}
