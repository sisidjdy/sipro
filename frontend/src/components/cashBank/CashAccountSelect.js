import { useEffect, useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { CASHBANK } from "@/constants/testIds";

/**
 * Pemilih rekening bank / kas (Fase 82). Dipasang di setiap dialog uang masuk/keluar.
 * - Memuat rekening aktif dari `/cash-bank/accounts?active=1`.
 * - Bila `value` kosong, otomatis memilih rekening default sesuai `kind` ("bank" | "cash" | null=semua).
 * - Menampilkan saldo buku tiap rekening agar kasir sadar saldo saat memilih.
 */
export default function CashAccountSelect({ value, onChange, kind = null, label = "Rekening / Kas",
  testId = CASHBANK.select, disabled = false, hint, exclude = null }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/cash-bank/accounts", { params: { active: true } })
      .then((r) => setRows(r.data.data || []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);

  const options = (kind ? rows.filter((r) => r.kind === kind) : rows).filter((r) => r.id !== exclude);

  useEffect(() => {
    if (!options.length) return;
    if (value && options.some((r) => r.id === value)) return;
    const def = options.find((r) => r.is_default) || options[0];
    if (def) onChange(def.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.length, kind, value, exclude]);

  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Select value={value || ""} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger data-testid={testId} className="h-9">
          <SelectValue placeholder={loading ? "Memuat rekening…" : options.length ? "Pilih rekening / kas" : "Belum ada rekening aktif"} />
        </SelectTrigger>
        <SelectContent>
          {options.map((r) => (
            <SelectItem key={r.id} value={r.id} data-testid={`${testId}-opt-${r.id}`}>
              <span className="font-medium">{r.kind === "cash" ? "Kas" : r.bank_name}</span>
              {" · "}{r.name}
              <span className="ml-2 text-xs text-muted-foreground tabular-nums">{formatIDR(r.balance)}</span>
              {r.is_default ? <span className="ml-1 text-[10px] uppercase text-primary">default</span> : null}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
