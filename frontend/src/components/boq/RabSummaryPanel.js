import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import MetricCard from "@/components/patterns/MetricCard";
import { LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { P80 } from "@/constants/testIds";
import RabFasumControl from "./RabFasumControl";

const SCOPE_LABEL = { unit: "Unit + add-on", fasum: "Fasum / fasos", umum: "Umum" };

/** Ringkasan RAB proyek: total RAB (unit+add-on+fasum+umum) vs nilai jual → margin; HPP per unit; kendali SPK dari RAB. */
export default function RabSummaryPanel({ projectId, reloadKey }) {
  const { can } = useAuth();
  const [s, setS] = useState(null);
  const load = useCallback(() => {
    api.get(`/rab/projects/${projectId}/summary`).then((r) => setS(r.data.data)).catch((e) => toast.error(e?.response?.data?.detail || "Gagal memuat ringkasan RAB."));
  }, [projectId]);
  useEffect(() => { load(); }, [load, reloadKey]);
  const setAlloc = async (method) => {
    try { await api.put(`/rab/projects/${projectId}/allocation`, { method }); toast.success("Metode alokasi disimpan."); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan alokasi."); }
  };
  if (!s) return <LoadingCards count={4} />;
  const neg = s.margin < 0;
  return (
    <div className="space-y-5">
      <div data-testid={P80.summaryCard} className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Total RAB (unit + add-on + fasum + umum)" value={s.total_rab} tone="primary" format="idr" />
        <MetricCard label="Total nilai jual (unit + add-on)" value={s.total_price + s.addon_sell} tone="indigo" format="idr" />
        <MetricCard label={`Margin RAB${s.margin_pct != null ? ` (${s.margin_pct}%)` : ""}`} value={s.margin} tone={neg ? "rose" : "emerald"} format="idr" />
        <MetricCard label="Biaya bersama (fasum + umum)" value={s.shared} tone="amber" format="idr" />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border bg-card p-3 text-sm shadow-[var(--shadow-card)]">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Komposisi RAB</p>
          <ul className="space-y-1 tabular-nums">
            <li className="flex justify-between"><span>RAB unit (Σ tipe × jumlah unit)</span><b>{formatIDR(s.unit_rab)}</b></li>
            <li className="flex justify-between"><span>RAB add-on terjual (deal aktif)</span><b>{formatIDR(s.addon_rab)}</b></li>
            <li className="flex justify-between"><span>Fasum / fasos</span><b>{formatIDR(s.fasum)}</b></li>
            <li className="flex justify-between"><span>Umum</span><b>{formatIDR(s.umum)}</b></li>
            {s.legacy ? <li className="flex justify-between text-amber-800"><span>Item RAB lama tanpa lingkup (dialokasikan sebagai biaya bersama)</span><b>{formatIDR(s.legacy)}</b></li> : null}
          </ul>
          {s.units_without_template ? <p className="mt-2 text-xs text-amber-700">{s.units_without_template} unit bertipe tanpa RAB tipe — HPP unit tersebut belum lengkap.</p> : null}
          <div className="mt-3 space-y-1">
            {s.per_type.map((t) => <p key={t.unit_type_code} className="flex justify-between text-xs"><span>{t.unit_type_code} · {t.name} × {t.units} unit{!t.has_template ? <span className="ml-1 rounded bg-amber-50 px-1 text-[10px] text-amber-800">belum ada RAB</span> : null}</span><span className="tabular-nums">{t.has_template ? `${formatIDR(t.rab_per_unit)} / unit → ${formatIDR(t.rab_total)}` : "—"}</span></p>)}
          </div>
        </div>
        <div className="rounded-xl border bg-card p-3 text-sm shadow-[var(--shadow-card)]">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Alokasi biaya bersama ke HPP unit</p>
          <Select value={s.allocation} onValueChange={setAlloc} disabled={!can("boq", "update")}>
            <SelectTrigger data-testid={P80.allocationSelect} className="bg-background"><SelectValue /></SelectTrigger>
            <SelectContent>{s.allocation_options.map((o) => <SelectItem key={o.code} value={o.code}>{o.label}</SelectItem>)}</SelectContent>
          </Select>
          <p className="mt-3 mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Kendali: RAB vs SPK dari RAB vs termin</p>
          <Table>
            <TableHeader><TableRow><TableHead>Lingkup</TableHead><TableHead className="text-right">RAB</TableHead><TableHead className="text-right">Dikontrakkan</TableHead><TableHead className="text-right">Ditagih</TableHead></TableRow></TableHeader>
            <TableBody>{s.control.map((c) => (
              <TableRow key={c.scope} data-testid={P80.controlRow} data-scope={c.scope} className={c.over ? "text-rose-700" : ""}>
                <TableCell className="text-xs">{SCOPE_LABEL[c.scope]} <span className="text-muted-foreground">({c.spk} SPK)</span></TableCell>
                <TableCell className="text-right tabular-nums text-xs">{formatIDR(c.budget)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{formatIDR(c.contracted)}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{formatIDR(c.billed)}</TableCell>
              </TableRow>))}</TableBody>
          </Table>
        </div>
      </div>
      <RabFasumControl rows={s.fasum_control} />
      <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
        <p className="border-b bg-secondary px-3 py-1.5 text-xs font-semibold">HPP per unit vs harga jual ({s.units} unit)</p>
        <Table>
          <TableHeader><TableRow><TableHead>Unit</TableHead><TableHead>Tipe</TableHead><TableHead className="text-right">RAB tipe</TableHead><TableHead className="text-right">Alokasi bersama</TableHead><TableHead className="text-right">HPP</TableHead><TableHead className="text-right">Harga jual</TableHead><TableHead className="text-right">Margin</TableHead></TableRow></TableHeader>
          <TableBody>{s.per_unit.map((u) => (
            <TableRow key={u.unit_id} data-testid={P80.hppRow} data-unit={u.unit_code}>
              <TableCell className="font-medium">{u.unit_code}</TableCell>
              <TableCell className="text-xs">{u.unit_type_code || u.type}</TableCell>
              <TableCell className="text-right tabular-nums text-xs">{formatIDR(u.rab_type)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs">{formatIDR(u.shared)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs font-medium">{formatIDR(u.hpp)}</TableCell>
              <TableCell className="text-right tabular-nums text-xs">{formatIDR(u.price)}</TableCell>
              <TableCell className={`text-right tabular-nums text-xs ${u.margin < 0 ? "text-rose-600" : "text-emerald-700"}`}>{formatIDR(u.margin)}{u.margin_pct != null ? ` (${u.margin_pct}%)` : ""}</TableCell>
            </TableRow>))}</TableBody>
        </Table>
      </div>
    </div>
  );
}
