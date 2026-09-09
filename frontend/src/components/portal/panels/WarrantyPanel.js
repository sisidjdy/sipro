import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, Plus, CheckCircle2 } from "lucide-react";

import ClaimAckDialog from "@/components/portal/panels/ClaimAckDialog";
import portalApi from "@/services/portalClient";
import { P50, P51 } from "@/constants/testIds";

const PILL = {
  aktif: "bg-emerald-50 text-emerald-700 border-emerald-200",
  hampir_habis: "bg-amber-50 text-amber-800 border-amber-200",
  habis: "bg-slate-100 text-slate-600 border-slate-200",
};

/**
 * Panel garansi di PORTAL PEMBELI (Fase 50A).
 *
 * Pembeli adalah orang yang paling butuh tahu “bagian ini masih garansi sampai kapan”.
 * Sebelum Fase 50 jawabannya hanya ada di kepala staf, jadi setiap keluhan berubah menjadi
 * perdebatan tanpa dasar. Di sini pembeli melihat masa garansi tiap bagian, mengajukan
 * klaim sendiri, dan melihat jawaban tertulis bila klaimnya ditolak.
 */
export default function WarrantyPanel() {
  const [rows, setRows] = useState([]);
  const [claims, setClaims] = useState([]);
  const [ref, setRef] = useState({});
  const [detail, setDetail] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [form, setForm] = useState(null);
  const [ackClaim, setAckClaim] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [w, c, r] = await Promise.all([
        portalApi.get("/portal/warranty"),
        portalApi.get("/portal/warranty/claims"),
        portalApi.get("/portal/reference"),
      ]);
      setRows(w.data.data || []);
      setDetail(w.data.detail || "");
      setClaims(c.data.data || []);
      setRef(r.data.data || {});
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat data garansi.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const catOptions = (ref.warranty_category?.options) || [];
  const labelOf = (group, value) => (ref[group]?.options || [])
    .find((o) => o.value === value)?.label || value || "—";

  const submit = async () => {
    if (!form?.category || (form.title || "").trim().length < 4) {
      toast.error("Pilih bagian yang dikeluhkan dan tulis judul keluhan.");
      return;
    }
    setBusy(true);
    try {
      const res = await portalApi.post("/portal/warranty/claims", {
        unit_id: form.unit_id, category: form.category, title: form.title.trim(),
        description: (form.description || "").trim() || null,
      });
      toast.success(res.data?.message || "Klaim garansi terkirim.");
      setForm(null);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengirim klaim garansi.");
    } finally { setBusy(false); }
  };

  if (loading) {
    return <p className="text-sm text-slate-500">Memuat data garansi…</p>;
  }
  if (error) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        {error}
      </div>
    );
  }

  return (
    <div data-testid={P50.portalWarrantyPanel} className="space-y-5">
      <div>
        <h2 className="flex items-center gap-2 font-heading text-lg font-semibold">
          <ShieldCheck className="h-5 w-5 text-indigo-600" /> Garansi rumah saya
        </h2>
        <p className="text-sm text-slate-500">{detail}</p>
      </div>

      {rows.map((r) => (
        <div key={r.unit.id} data-testid={P50.portalWarrantyRow}
          className="rounded-2xl border bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="section-title">
                Rumah {r.unit.code} · {r.unit.type || "—"}
              </p>
              <p className="text-sm text-slate-500">{r.detail}</p>
            </div>
            {!r.missing ? (
              <button data-testid={P50.portalClaimBtn}
                onClick={() => setForm({ unit_id: r.unit.id, unit_code: r.unit.code,
                  category: "", title: "", description: "" })}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700">
                <Plus className="h-4 w-4" /> Ajukan klaim garansi
              </button>
            ) : null}
          </div>

          {r.missing ? (
            <p className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
              {r.detail}
            </p>
          ) : (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {(r.warranty || []).map((w) => (
                <div key={w.category}
                  className="flex items-center justify-between rounded-xl border p-2.5 text-sm">
                  <div>
                    <p className="font-medium">{w.label}</p>
                    <p className="text-xs text-slate-500">
                      {w.months} bulan · sampai {w.expires_at}
                    </p>
                  </div>
                  <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
                    PILL[w.state] || PILL.habis}`}>
                    {w.state_label}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      <div className="space-y-2">
        <h3 className="section-title">Klaim yang pernah saya ajukan</h3>
        {!claims.length ? (
          <p className="rounded-xl border bg-white p-4 text-sm text-slate-500">
            Belum ada klaim garansi yang Anda ajukan.
          </p>
        ) : claims.map((c) => (
          <div key={c.id} data-testid={P50.portalClaimRow}
            className="rounded-xl border bg-white p-3 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-medium">{c.number} · {c.title}</p>
                <p className="text-xs text-slate-500">
                  {c.unit_code} · {labelOf("warranty_category", c.category)} · diajukan{" "}
                  {String(c.submitted_on || c.submitted_at || "").slice(0, 10)}
                </p>
                {c.reject_detail ? (
                  <p className="mt-1 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700">
                    {c.reject_detail}
                  </p>
                ) : null}
                {c.ack_by ? (
                  <p data-testid={P51.portalAckDone}
                    className="mt-1 flex items-start gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs text-emerald-800">
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    Anda sudah mengakui perbaikan ini selesai
                    {c.ack_note ? ` — “${c.ack_note}”` : ""}.
                  </p>
                ) : null}
                {c.state === "selesai" ? (
                  <p data-testid={P51.portalAckWaiting}
                    className="mt-1 rounded-lg border border-sky-200 bg-sky-50 px-2 py-1 text-xs text-sky-900">
                    Perbaikan dilaporkan selesai dan sedang diperiksa mutunya oleh tim.
                    Anda akan diminta mengakuinya setelah pemeriksaan itu lulus.
                  </p>
                ) : null}
              </div>
              <div className="flex flex-col items-end gap-1.5">
                <span className="rounded-full border bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700">
                  {labelOf("warranty_claim_state", c.state)}
                </span>
                {c.state === "diverifikasi" ? (
                  <button type="button" data-testid={P51.portalAckBtn}
                    onClick={() => setAckClaim(c)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Konfirmasi perbaikan
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        ))}
      </div>

      {form ? (
        <div className="fixed inset-0 z-30 grid place-items-center bg-slate-900/40 p-4">
          <div data-testid={P50.portalClaimDialog}
            className="w-full max-w-md rounded-2xl bg-white p-4 shadow-xl">
            <p className="section-title">
              Ajukan klaim garansi — rumah {form.unit_code}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              Bila masa garansi bagian yang Anda pilih sudah lewat, klaim tetap tercatat dan
              Anda menerima jawaban tertulis beserta tanggal habisnya.
            </p>
            <div className="mt-3 space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-medium" htmlFor="pw-cat">Bagian yang dikeluhkan</label>
                <select id="pw-cat" data-testid={P50.portalClaimCategory}
                  value={form.category}
                  onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                  className="w-full rounded-lg border bg-white px-3 py-2 text-sm">
                  <option value="">Pilih bagian…</option>
                  {catOptions.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium" htmlFor="pw-title">Judul keluhan</label>
                <input id="pw-title" data-testid={P50.portalClaimTitle} value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                  placeholder="mis. plafon kamar depan bocor"
                  className="w-full rounded-lg border bg-white px-3 py-2 text-sm" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium" htmlFor="pw-desc">Uraian (opsional)</label>
                <textarea id="pw-desc" rows={3} data-testid={P50.portalClaimDescription}
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  className="w-full rounded-lg border bg-white px-3 py-2 text-sm" />
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setForm(null)} disabled={busy}
                className="rounded-lg border px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">
                Batal
              </button>
              <button data-testid={P50.portalClaimSubmit} onClick={submit} disabled={busy}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
                {busy ? "Mengirim…" : "Kirim klaim"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <ClaimAckDialog claim={ackClaim} onOpenChange={() => setAckClaim(null)}
        onDone={() => { setAckClaim(null); load(); }} />
    </div>
  );
}
