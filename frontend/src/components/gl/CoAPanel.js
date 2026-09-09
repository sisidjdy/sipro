import React, { useCallback, useEffect, useState } from "react";
import { Plus, BookOpen, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import AddAccountDialog from "@/components/gl/AddAccountDialog";
import EditAccountDialog from "@/components/gl/EditAccountDialog";
import { useAuth } from "@/context/AuthContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { GL } from "@/constants/testIds";
import RefLabel from "@/components/patterns/RefLabel";


export default function CoAPanel() {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canManage = can("coa", "create");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editAcc, setEditAcc] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const r = await api.get("/gl/accounts"); setData(r.data); }
    catch (e) { setError(e?.response?.data?.detail || "Gagal memuat bagan akun."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Bagan Akun ({data?.total || 0})</p>
        {canManage ? (
          <Button data-testid={GL.accountAddBtn} size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> Tambah Akun
          </Button>
        ) : null}
      </div>
      {loading ? <LoadingCards count={4} /> : error ? <ErrorState message={error} onRetry={load} /> :
        !data?.data?.length ? (
          <EmptyState icon={BookOpen} title="Belum ada akun" description="Bagan akun standar akan otomatis dibuat." />
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Kode</TableHead><TableHead>Nama Akun</TableHead><TableHead>Tipe</TableHead>
                <TableHead className="text-right">Debit</TableHead><TableHead className="text-right">Kredit</TableHead>
                <TableHead className="text-right">Saldo</TableHead>
                {canManage ? <TableHead className="col-actions-head text-right">Aksi</TableHead> : null}
              </TableRow></TableHeader>
              <TableBody>
                {data.data.map((a) => (
                  <TableRow key={a.code} data-testid={GL.accountRow} data-account-code={a.code}>
                    <TableCell className="font-medium tabular-nums">{a.code}</TableCell>
                    <TableCell className="text-sm">{a.name}</TableCell>
                    <TableCell className="text-sm"><RefLabel group="account_type" value={a.type} /></TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{a.debit ? formatIDR(a.debit) : "-"}</TableCell>
                    <TableCell className="text-right tabular-nums text-sm">{a.credit ? formatIDR(a.credit) : "-"}</TableCell>
                    <TableCell className="text-right tabular-nums font-medium">{formatIDR(a.balance)}</TableCell>
                    {canManage ? (
                      <TableCell className="col-actions text-right">
                        <Button data-testid="gl-account-edit-btn" data-account-code={a.code}
                          aria-label={`Ubah akun ${a.code} ${a.name}`}
                          title={`Ubah akun ${a.code} — ${a.name}`}
                          size="sm" variant="ghost"
                          onClick={() => setEditAcc(a)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      <AddAccountDialog open={addOpen} onOpenChange={setAddOpen} onDone={load} />
      <EditAccountDialog account={editAcc} open={!!editAcc}
        onOpenChange={(v) => !v && setEditAcc(null)} onDone={load} />
    </div>
  );
}
