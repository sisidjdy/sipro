import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Boxes, Plus, ArrowLeftRight, ClipboardList , Pencil} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, AccessDenied } from "@/components/patterns/StateViews";
import ProjectSelect from "@/components/construction/ProjectSelect";
import RequisitionsPanel from "@/components/materials/RequisitionsPanel";
import BudgetPanel from "@/components/materials/BudgetPanel";
import StockControlPanel from "@/components/materials/StockControlPanel";
import { useAuth } from "@/context/AuthContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import EditMaterialDialog from "@/components/materials/EditMaterialDialog";
import api from "@/services/apiClient";
import { MATERIALS, STOCK } from "@/constants/testIds";
import ReferenceItems from "@/components/patterns/ReferenceItems";

export default function MaterialsPage() {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  // Pemisahan tugas Fase 18: site MENGAJUKAN & mengeluarkan, PM MENYETUJUI.
  const canView = can("materials", "view");
  const canUpdate = can("materials", "update");
  const canApprove = can("materials", "approve");
  const [projectId, setProjectId] = useState(null);
  const [mats, setMats] = useState([]);
  const [txns, setTxns] = useState([]);
  const [phases, setPhases] = useState([]);
  const [loading, setLoading] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [txnMat, setTxnMat] = useState(null);
  const [opnameMat, setOpnameMat] = useState(null);
  const [editMat, setEditMat] = useState(null);
  const [budgetKey, setBudgetKey] = useState(0);
  const [tab, setTab] = useState("stok");

  const load = useCallback(async () => {
    if (!projectId || !canView) return;
    setLoading(true);
    try {
      const [m, t, p] = await Promise.all([
        api.get(`/materials/project/${projectId}`),
        api.get(`/materials/project/${projectId}/txns`),
        api.get(`/construction/project/${projectId}/phases`),
      ]);
      setMats(m.data.data || []);
      setTxns(t.data.data || []);
      setPhases(p.data.data || []);
      setBudgetKey((k) => k + 1);
    } catch (e) { toast.error("Gagal memuat material."); }
    finally { setLoading(false); }
  }, [projectId, canView]);

  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid={MATERIALS.page} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Boxes className="h-5 w-5 text-primary" />
          <h1 className="page-title">Material, Permintaan & Anggaran</h1>
        </div>
        {canView ? (
          <ProjectSelect value={projectId} onChange={setProjectId} testId={MATERIALS.projectSelect} />
        ) : null}
      </div>

      {!canView ? (
        <AccessDenied testId={MATERIALS.denied}
          title="Gudang & permintaan material bukan untuk peran Anda"
          description={"Halaman ini memuat stok gudang, permintaan material, anggaran RAB, dan "
            + "perpindahan barang antar proyek — dibuka untuk tim Proyek (Manajer Proyek, "
            + "pelaksana lapangan), Keuangan, dan Direksi."}
          askWho="Bila Anda memang perlu melihat ketersediaan material untuk pembeli, mintakan hak akses ke admin sistem." />
      ) : !projectId ? (
        <EmptyState icon={Boxes} title="Pilih proyek" description="Pilih proyek untuk melihat stok material, permintaan, & anggaran RAB." />
      ) : (
        <Tabs value={tab} onValueChange={setTab} className="space-y-4">
          <TabsList>
            <TabsTrigger data-testid={MATERIALS.tabStock} value="stok">Stok & Buku Besar</TabsTrigger>
            <TabsTrigger data-testid={MATERIALS.tabReq} value="permintaan">Permintaan Material</TabsTrigger>
            <TabsTrigger data-testid={MATERIALS.tabBudget} value="anggaran">Anggaran (RAB)</TabsTrigger>
            <TabsTrigger data-testid={STOCK.tab} value="kendali">Kendali Stok</TabsTrigger>
          </TabsList>

          <TabsContent value="stok" className="space-y-4">
            {loading ? <LoadingCards count={3} /> : (
            <>
            {canUpdate ? (
              <div className="flex justify-end">
                <Button data-testid={MATERIALS.addBtn} size="sm" onClick={() => setAddOpen(true)}>
                  <Plus className="mr-1.5 h-4 w-4" /> Material
                </Button>
              </div>
            ) : null}
            <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Kode</TableHead><TableHead>Material</TableHead>
                    <TableHead className="text-right">Stok (buku)</TableHead>
                    <TableHead>Satuan</TableHead><TableHead>Opname terakhir</TableHead>
                    {canUpdate ? <TableHead className="col-actions-head text-right">Aksi</TableHead> : null}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {mats.map((m) => (
                    <TableRow key={m.id} data-testid={MATERIALS.row} data-material-code={m.code}>
                      <TableCell className="font-mono text-xs">{m.code}</TableCell>
                      <TableCell className="font-medium">{m.name}</TableCell>
                      <TableCell className="text-right font-semibold tabular-nums">{m.stock}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{m.uom}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{m.last_opname ? formatDateTimeWIB(m.last_opname) : "-"}</TableCell>
                      {canUpdate ? (
                        <TableCell className="col-actions text-right">
                          <div className="flex justify-end gap-1.5">
                            <Button data-testid={MATERIALS.txnBtn} data-material-code={m.code}
                              aria-label={`Transaksi stok ${m.name}`} size="sm" variant="outline" onClick={() => setTxnMat(m)}>
                              <ArrowLeftRight className="mr-1 h-3.5 w-3.5" /> Transaksi
                            </Button>
                            <Button data-testid={MATERIALS.opnameBtn} data-material-code={m.code}
                              aria-label={`Opname stok ${m.name}`} size="sm" variant="ghost" onClick={() => setOpnameMat(m)}>
                              <ClipboardList className="mr-1 h-3.5 w-3.5" /> Opname
                            </Button>
                            <Button data-testid="material-edit-btn" data-material-code={m.code}
                              aria-label={`Ubah material ${m.name}`} size="sm" variant="ghost" onClick={() => setEditMat(m)}>
                              <Pencil className="mr-1 h-3.5 w-3.5" /> Ubah
                            </Button>
                          </div>
                        </TableCell>
                      ) : null}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold">Buku Besar Material (terbaru)</h3>
              {!txns.length ? <p className="text-sm text-muted-foreground">Belum ada transaksi.</p> : (
                <div className="space-y-2">
                  {txns.slice(0, 30).map((t) => (
                    <div key={t.id} className="flex items-center justify-between rounded-lg border bg-card p-2.5 text-sm shadow-[var(--shadow-card)]">
                      <div>
                        <span className={`mr-2 rounded-full border px-2 py-0.5 text-xs ${
                          t.type === "in" ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                          : t.type === "out" ? "border-rose-200 bg-rose-50 text-rose-700"
                          : "border-amber-200 bg-amber-50 text-amber-800"}`}>
                          {t.type === "in" ? "MASUK" : t.type === "out" ? "KELUAR" : "OPNAME"}
                        </span>
                        <span className="font-medium">{t.material_name}</span>
                        <span className="ml-2 tabular-nums text-muted-foreground">{t.qty > 0 ? "+" : ""}{t.qty} {t.uom}</span>
                        {t.ref ? <span className="ml-2 text-[11px] text-muted-foreground">({t.ref})</span> : null}
                      </div>
                      <span className="text-[11px] text-muted-foreground">{formatDateTimeWIB(t.created_at)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            </>
            )}
          </TabsContent>

          <TabsContent value="permintaan">
            <RequisitionsPanel projectId={projectId} materials={mats} phases={phases}
              canCreate={canUpdate} canApprove={canApprove} onChanged={load} />
          </TabsContent>

          <TabsContent value="anggaran">
            <BudgetPanel projectId={projectId} refreshKey={budgetKey} />
          </TabsContent>

          {/* Fase 48E — peringatan stok minimum, transfer antar proyek, dan NILAI persediaan
              (harga rata-rata bergerak; material tanpa harga masuk dilaporkan apa adanya). */}
          <TabsContent value="kendali">
            <StockControlPanel projectId={projectId} onChanged={load} />
          </TabsContent>

          <AddMaterialDialog projectId={projectId} open={addOpen} onOpenChange={setAddOpen} onDone={load} />
          <TxnDialog projectId={projectId} material={txnMat} onOpenChange={(v) => !v && setTxnMat(null)} onDone={load} />
          <OpnameDialog projectId={projectId} material={opnameMat} onOpenChange={(v) => !v && setOpnameMat(null)} onDone={load} />
          <EditMaterialDialog material={editMat} open={!!editMat}
            onOpenChange={(v) => !v && setEditMat(null)} onDone={load} />
        </Tabs>
      )}
    </div>
  );
}

function AddMaterialDialog({ projectId, open, onOpenChange, onDone }) {
  const [form, setForm] = useState({ code: "", name: "", uom: "unit" });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const submit = async () => {
    if (!form.code || !form.name) { toast.error("Kode & nama wajib."); return; }
    setBusy(true);
    try {
      await api.post("/materials", { project_id: projectId, ...form });
      toast.success("Material ditambahkan.");
      onOpenChange(false); setForm({ code: "", name: "", uom: "unit" }); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal."); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Tambah Material</DialogTitle></DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5"><Label htmlFor="materialspage-kode">Kode</Label><Input id="materialspage-kode" value={form.code} onChange={(e) => set("code", e.target.value.toUpperCase())} /></div>
          <div className="space-y-1.5"><Label>Satuan</Label>
            <ReferenceSelect group="uom" value={form.uom} onChange={(v) => set("uom", v)}
              testId="material-form-uom" /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="materialspage-nama">Nama</Label><Input id="materialspage-nama" value={form.name} onChange={(e) => set("name", e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={MATERIALS.addSubmit} onClick={submit} disabled={busy}>{busy ? "Menyimpan..." : "Simpan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TxnDialog({ projectId, material, onOpenChange, onDone }) {
  const open = !!material;
  const [type, setType] = useState("in");
  const [qty, setQty] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setType("in"); setQty(""); setNote(""); } }, [open]);
  const submit = async () => {
    if (!qty || Number(qty) <= 0) { toast.error("Qty harus > 0."); return; }
    setBusy(true);
    try {
      const res = await api.post("/materials/txn", {
        project_id: projectId, material_id: material.id, type, qty: Number(qty), note });
      toast.success(`Stok baru: ${res.data.stock} ${material.uom}.`);
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal."); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Transaksi Material</DialogTitle>
          <DialogDescription>{material?.name} · stok {material?.stock} {material?.uom}</DialogDescription></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label>Tipe</Label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger data-testid="txn-type-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <ReferenceItems group="stock_movement" />
              </SelectContent>
            </Select></div>
          <div className="space-y-1.5"><Label>Jumlah ({material?.uom})</Label>
            <Input type="number" value={qty} onChange={(e) => setQty(e.target.value)} /></div>
          <div className="space-y-1.5"><Label htmlFor="materialspage-catatan">Catatan</Label>
            <Textarea id="materialspage-catatan" rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={MATERIALS.txnSubmit} onClick={submit} disabled={busy}>{busy ? "Memproses..." : "Simpan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OpnameDialog({ projectId, material, onOpenChange, onDone }) {
  const open = !!material;
  const [physical, setPhysical] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setPhysical(String(material?.stock ?? "")); setNote(""); } }, [open, material]);
  const variance = physical === "" ? null : Number(physical) - (material?.stock ?? 0);
  const submit = async () => {
    if (physical === "") { toast.error("Isi jumlah fisik."); return; }
    setBusy(true);
    try {
      const res = await api.post("/materials/opname", {
        project_id: projectId, material_id: material.id, physical_qty: Number(physical), note });
      const v = res.data.data.variance;
      toast.success(`Opname tersimpan. Selisih ${v > 0 ? "+" : ""}${v} ${material.uom}.`);
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal."); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Stock Opname</DialogTitle>
          <DialogDescription>{material?.name} · stok buku {material?.stock} {material?.uom}</DialogDescription></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label>Jumlah Fisik ({material?.uom})</Label>
            <Input type="number" value={physical} onChange={(e) => setPhysical(e.target.value)} /></div>
          {variance !== null ? (
            <div className={`rounded-lg border p-2.5 text-sm ${
              variance === 0 ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-amber-200 bg-amber-50 text-amber-800"}`}>
              Selisih (fisik − buku): <b className="tabular-nums">{variance > 0 ? "+" : ""}{variance} {material?.uom}</b>
              {variance !== 0 ? " — penyesuaian akan dicatat di buku besar." : " — sesuai."}
            </div>
          ) : null}
          <div className="space-y-1.5"><Label htmlFor="materialspage-catatan-2">Catatan</Label>
            <Textarea id="materialspage-catatan-2" rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={MATERIALS.opnameSubmit} onClick={submit} disabled={busy}>{busy ? "Memproses..." : "Simpan Opname"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
