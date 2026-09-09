import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Ban, BookOpen, FileUp, Landmark, Link2, Plus, ScanSearch, Undo2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import DataTable from "@/components/patterns/DataTable";
import FilterBar from "@/components/patterns/FilterBar";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import KpiCard from "@/components/patterns/KpiCard";
import BankImportDialog from "@/components/finance/BankImportDialog";
import BankMatchDialog from "@/components/finance/BankMatchDialog";
import BankAccountDialog from "@/components/finance/BankAccountDialog";
import BankReasonDialog from "@/components/finance/BankReasonDialog";
import PaymentIntakePanel from "@/components/finance/PaymentIntakePanel";
import ReconOverviewTable from "@/components/finance/ReconOverviewTable";
import ReconDifferencesPanel from "@/components/finance/ReconDifferencesPanel";
import useListQuery from "@/hooks/useListQuery";
import { useAuth } from "@/context/AuthContext";
import { useReference } from "@/context/ReferenceContext";
import { formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { BANK, DT } from "@/constants/testIds";

/**
 * BankReconciliationTab (Fase 47A) — mencocokkan uang di REKENING dengan uang di PEMBUKUAN.
 *
 * Cacat yang ditutup: sebelum fase ini penerimaan hanya bisa dicatat manual, sehingga
 * “sudah bayar” versi sistem tidak pernah dibandingkan dengan rekening bank. Layar ini
 * membuat tiga hal terlihat sekaligus:
 *   1. **Saldo buku vs saldo rekening** beserta SELISIH dan penyebabnya — termasuk bagian
 *      selisih yang BELUM bisa dijelaskan (dikatakan apa adanya, tidak disembunyikan).
 *   2. **Mutasi yang belum dicocokkan** — uang yang masuk rekening tetapi belum diakui
 *      sebagai pelunasan siapa pun. Selama di daftar ini, ia TIDAK mengurangi tagihan.
 *   3. **Jejak keputusan**: mencocokkan memakai jalur resmi subledger (kuitansi/AP/upah),
 *      membatalkan pencocokan melahirkan jurnal pembalik dan wajib beralasan.
 */
export default function BankReconciliationTab() {
  const { can } = useAuth();
  // Izin EFEKTIF (`GET /auth/me`), bukan salinan daftar peran: mendaftarkan rekening &
  // mengimpor mutasi = `bank:create`, mencocokkan/mengabaikan = `bank:update`, MEMBATALKAN
  // pencocokan (membalik pembukuan) = `bank:approve` — hanya Manajer Keuangan. Tanpa gerbang
  // ini, kasir melihat tombol "Batalkan" yang SELALU dijawab 403 (tombol mati).
  const canImport = can("bank", "create");
  const canMatch = can("bank", "update");
  const canReverse = can("bank", "approve");
  const { options } = useReference();
  const { query, setQuery, reset, apiParams, activeCount } = useListQuery({
    filters: { match_state: [], direction: "", date_from: "", date_to: "" }, limit: 25,
  });
  const [accounts, setAccounts] = useState([]);
  const [accountId, setAccountId] = useState("");
  const [txns, setTxns] = useState(null);
  const [recon, setRecon] = useState(null);
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [matchTxn, setMatchTxn] = useState(null);
  const [reasonAction, setReasonAction] = useState(null);

  const loadAccounts = useCallback(async () => {
    try {
      const res = await api.get("/bank/accounts");
      const rows = res.data.data || [];
      setAccounts(rows);
      setAccountId((cur) => cur || rows[0]?.id || "");
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat daftar rekening.");
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = { ...apiParams, ...(accountId ? { account_id: accountId } : {}) };
      const [t, r, o] = await Promise.all([
        api.get("/bank/transactions", { params }),
        api.get("/bank/reconciliation", {
          params: accountId ? { account_id: accountId } : {},
        }),
        api.get("/bank/reconciliation/overview"),
      ]);
      setTxns(t.data);
      setRecon(r.data.data);
      setOverview(o.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat mutasi rekening.");
    } finally { setLoading(false); }
  }, [apiParams, accountId]);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);
  useEffect(() => { load(); }, [load]);

  const act = async (kind, txn, reason) => {
    const url = `/bank/transactions/${txn.id}/${kind}`;
    const res = await api.post(url, { reason });
    toast.success(res.data.message
      || (kind === "unmatch" ? "Pencocokan dibatalkan & dampaknya dibalik."
        : "Mutasi ditandai bukan urusan perusahaan."));
    load();
  };

  const columns = useMemo(() => [
    {
      key: "date", header: "Tanggal",
      render: (r) => <span className="tabular-nums">{formatDateWIB(r.date)}</span>,
    },
    {
      key: "description", header: "Keterangan",
      render: (r) => (
        <div className="max-w-[22rem]">
          <p className="truncate font-medium">{r.description || "-"}</p>
          <p className="text-xs text-muted-foreground">
            {r.ref || "tanpa referensi"}{r.account_name ? ` · ${r.account_name}` : ""}
          </p>
        </div>
      ),
    },
    {
      key: "direction", header: "Arah",
      render: (r) => <StatusPill status={r.direction} group="bank_txn_direction" />,
    },
    {
      key: "amount", header: "Nominal", align: "right",
      render: (r) => <MoneyText value={r.amount}
        className={r.direction === "in" ? "font-medium text-emerald-700" : "font-medium text-rose-700"} />,
      exportValue: (r) => r.amount || 0,
    },
    {
      key: "match_state", header: "Status",
      render: (r) => (
        <div className="space-y-0.5">
          <StatusPill status={r.match_state} group="bank_match_state" />
          {r.match_kind ? (
            <p className="text-xs text-muted-foreground">{r.match_state_label}</p>
          ) : null}
          {r.ignore_reason ? (
            <p className="max-w-[16rem] truncate text-xs text-amber-700"
              title={r.ignore_reason}>{r.ignore_reason}</p>
          ) : null}
        </div>
      ),
    },
    {
      key: "aksi", header: "Aksi", align: "right", sticky: true,
      render: (r) => (
        <div className="flex justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          {r.match_state === "unmatched" && canMatch ? (
            <>
              <Button size="sm" data-testid={BANK.matchBtn} data-txn={r.id}
                aria-label={`Cocokkan mutasi ${r.ref || r.date}`}
                onClick={() => setMatchTxn(r)}>
                <Link2 className="mr-1 h-3.5 w-3.5" /> Cocokkan
              </Button>
              <Button size="sm" variant="outline" data-testid={BANK.ignoreBtn} data-txn={r.id}
                aria-label={`Abaikan mutasi ${r.ref || r.date}`}
                onClick={() => setReasonAction({ kind: "ignore", txn: r })}>
                <Ban className="mr-1 h-3.5 w-3.5" /> Abaikan
              </Button>
            </>
          ) : null}
          {r.match_state === "matched" ? (
            canReverse ? (
              <Button size="sm" variant="outline" data-testid={BANK.unmatchBtn} data-txn={r.id}
                aria-label={`Batalkan pencocokan mutasi ${r.ref || r.date}`}
                onClick={() => setReasonAction({ kind: "unmatch", txn: r })}>
                <Undo2 className="mr-1 h-3.5 w-3.5" /> Batalkan
              </Button>
            ) : (
              <span className="text-xs text-muted-foreground">
                Pembatalan oleh Manajer Keuangan
              </span>
            )
          ) : null}
        </div>
      ),
      exportValue: () => "",
    },
  ], [canMatch, canReverse]);

  const filters = (
    <FilterBar value={query} onChange={setQuery} onReset={reset} filters={[
      { key: "match_state", label: "Status pencocokan", type: "multiselect",
        options: options("bank_match_state")
          .map((o) => ({ ...o, hint: txns?.summary?.[o.value] })) },
      { key: "direction", label: "Arah mutasi", type: "select",
        options: options("bank_txn_direction") },
      { key: "tanggal", label: "Tanggal mutasi", type: "daterange",
        fromKey: "date_from", toKey: "date_to" },
    ]} />
  );

  const account = accounts.find((a) => a.id === accountId);
  const diff = recon?.difference;

  return (
    <div data-testid={BANK.panel} className="space-y-5">
      <ReconOverviewTable rows={overview} selectedId={accountId} onSelect={setAccountId} />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1.5">
          <Label>Rekening yang direkonsiliasi</Label>
          <Select value={accountId} onValueChange={setAccountId}>
            <SelectTrigger data-testid={BANK.accountSelect} className="w-[19rem]"
              aria-label="Rekening yang direkonsiliasi">
              <SelectValue placeholder={accounts.length ? "Pilih rekening"
                : "Belum ada rekening terdaftar"} />
            </SelectTrigger>
            <SelectContent>
              {accounts.map((a) => (
                <SelectItem key={a.id} value={a.id}>
                  {a.name} · {a.bank_name} {a.account_no}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-2">
          {canImport ? (
            <>
              <Button variant="outline" data-testid={BANK.accountAddBtn}
                onClick={() => setAccountOpen(true)}>
                <Plus className="mr-1.5 h-4 w-4" /> Rekening
              </Button>
              <Button data-testid={BANK.importBtn} disabled={!accountId}
                onClick={() => setImportOpen(true)}>
                <FileUp className="mr-1.5 h-4 w-4" /> Impor mutasi
              </Button>
            </>
          ) : (
            <p className="text-xs text-muted-foreground">
              Impor mutasi dilakukan kasir/keuangan — peran Anda hanya melihat hasilnya.
            </p>
          )}
        </div>
      </div>

      <div data-testid={BANK.reconSummary} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Saldo buku (GL)" icon={BookOpen} tone="primary"
          value={<MoneyText value={recon?.book_balance} />}
          hint={`Akun ${recon?.gl_account_code || "-"}`} />
        <KpiCard label="Saldo rekening" icon={Landmark} tone="emerald"
          value={recon?.statement_balance === null || recon?.statement_balance === undefined
            ? <span className="text-base font-medium text-muted-foreground">belum ada data</span>
            : <MoneyText value={recon.statement_balance} />}
          hint={recon?.statement_balance_at
            ? `Per ${formatDateWIB(recon.statement_balance_at)}`
            : "Berkas mutasi belum memuat kolom saldo"} />
        <KpiCard label="Selisih" icon={ScanSearch}
          tone={diff ? (recon?.residual ? "rose" : "amber") : "emerald"}
          value={diff === null || diff === undefined
            ? <span className="text-base font-medium text-muted-foreground">belum bisa dihitung</span>
            : <MoneyText value={diff} />}
          hint={diff ? (recon?.residual ? "Ada residu tak terjelaskan — lihat uraian" : "Terurai seluruhnya di bawah")
            : "Saldo buku sama dengan rekening"} />
        <KpiCard label="Belum dicocokkan" icon={Link2} tone="amber"
          value={recon?.unmatched_count ?? 0}
          hint={`Masuk ${recon?.unmatched_in ? "Rp " + Number(recon.unmatched_in).toLocaleString("id-ID") : "0"}`} />
      </div>

      <ReconDifferencesPanel recon={recon} canExplain={canMatch} onChanged={load} />

      <DataTable testId={BANK.table} testIds={{ row: BANK.row, pagination: DT.pagination }}
        columns={columns} rows={txns?.data || []} total={txns?.total || 0}
        query={query} onQueryChange={setQuery} loading={loading} error={error}
        filters={filters} label="mutasi" exportName="mutasi-rekening" onRefresh={load}
        searchPlaceholder="Cari keterangan / referensi mutasi…"
        emptyTitle={activeCount || query.q ? "Tidak ada mutasi yang cocok"
          : "Belum ada mutasi rekening"}
        emptyDescription={activeCount || query.q
          ? "Longgarkan filter atau kosongkan pencarian."
          : "Impor berkas mutasi dari internet banking. Pratinjau tidak menulis apa pun, dan impor ulang berkas yang sama tidak menggandakan data."}
        emptyActionLabel={activeCount || query.q ? "Reset filter"
          : (canImport ? "Impor mutasi" : "")}
        emptyAction={activeCount || query.q ? () => reset()
          : (canImport ? () => setImportOpen(true) : null)}
        footer={(txns?.data || []).length ? (
          <p className="text-xs text-muted-foreground">
            Mutasi berstatus “belum dicocokkan” TIDAK dihitung sebagai pelunasan. Tagihan
            pembeli hanya berubah setelah mutasi dicocokkan ke termin/bukti transfernya.
          </p>
        ) : null} />

      <PaymentIntakePanel onChanged={load} />

      <BankImportDialog open={importOpen} onOpenChange={setImportOpen} accountId={accountId}
        accountName={account ? `${account.name} · ${account.account_no}` : ""} onDone={load} />
      <BankAccountDialog open={accountOpen} onOpenChange={setAccountOpen}
        onDone={() => { loadAccounts(); load(); }} />
      <BankMatchDialog open={!!matchTxn} onOpenChange={(v) => !v && setMatchTxn(null)}
        txn={matchTxn} onDone={load} />
      <BankReasonDialog open={!!reasonAction}
        onOpenChange={(v) => !v && setReasonAction(null)}
        title={reasonAction?.kind === "unmatch" ? "Batalkan pencocokan" : "Abaikan mutasi ini"}
        description={reasonAction?.kind === "unmatch"
          ? "Dampaknya dibalik: kuitansi dibatalkan dan jurnal pembalik dibuat. Alasan akan tercatat di jejak audit."
          : "Mutasi tetap terlihat, tetapi dinyatakan bukan urusan perusahaan. Alasan wajib agar bisa ditinjau ulang."}
        confirmLabel={reasonAction?.kind === "unmatch" ? "Batalkan & balik jurnal"
          : "Tandai diabaikan"}
        placeholder={reasonAction?.kind === "unmatch"
          ? "Mis. ternyata transfer milik pembeli lain."
          : "Mis. mutasi milik rekening pribadi direksi."}
        testIds={reasonAction?.kind === "unmatch"
          ? { reason: BANK.unmatchReason, submit: BANK.unmatchSubmit }
          : { reason: BANK.ignoreReason, submit: BANK.ignoreSubmit }}
        onSubmit={(reason) => act(reasonAction.kind, reasonAction.txn, reason)} />
    </div>
  );
}
