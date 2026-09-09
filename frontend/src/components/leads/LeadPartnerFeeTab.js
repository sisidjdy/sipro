import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Handshake, Info } from "lucide-react";

import EmptyState from "@/components/patterns/EmptyState";
import MoneyText from "@/components/patterns/MoneyText";
import RefLabel from "@/components/patterns/RefLabel";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { formatDateWIB } from "@/utils/formatters";
import { CRMC } from "@/constants/testIds";

/**
 * Tab “Fee Mitra” pada profil lead.
 *
 * Tab ini sempat MATI dengan keterangan “aturan fee mitra baru dibuat pada Fase 45” —
 * keterangan yang sudah kadaluarsa: master mitra, aturan fee (7 basis, split, pajak), dan
 * fee otomatis dari pemicu nyata SUDAH berjalan sejak fase mitra & fee dikerjakan. Jadi
 * layar ini bukan fitur baru; ia menutup lubang “datanya ada tetapi tidak bisa dilihat dari
 * lead yang menghasilkannya”.
 *
 * Yang ditampilkan: atribusi mitra pada lead ini, fee yang benar-benar terbit untuknya
 * (bruto, PPh, neto, status persetujuan), dan aturan fee yang berlaku. Bila lead ini bukan
 * dari mitra, layar mengatakannya — bukan menampilkan tabel kosong yang seolah rusak.
 */
export default function LeadPartnerFeeTab({ leadId, lead }) {
  const [fees, setFees] = useState([]);
  const [rules, setRules] = useState([]);
  const [partner, setPartner] = useState(null);
  const [scope, setScope] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [denied, setDenied] = useState(false);

  const partnerId = lead?.partner_id || lead?.agent_id || null;

  const load = useCallback(async () => {
    setLoading(true); setError(""); setDenied(false);
    try {
      const f = await api.get("/marketing/fees", {
        params: { lead_id: leadId, limit: 50 },
      }).catch((e) => {
        if (e?.response?.status === 403) { setDenied(true); return { data: { data: [] } }; }
        throw e;
      });
      setFees(f.data.data || []);
      setScope(f.data.scope || "all");
      const [r, p] = await Promise.all([
        api.get("/partners/rules").catch(() => ({ data: { data: [] } })),
        partnerId ? api.get(`/partners/${partnerId}`).catch(() => ({ data: { data: null } }))
          : Promise.resolve({ data: { data: null } }),
      ]);
      setRules(r.data.data || []);
      // `/partners/{id}` menjawab satu BUNDEL (partner + metrics + fees + rules), bukan
      // dokumen mitra langsung. Membacanya salah membuat nama mitra tampil kosong.
      setPartner((p.data.data || {}).partner || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat fee mitra lead ini.");
    } finally { setLoading(false); }
  }, [leadId, partnerId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  if (denied) {
    return (
      <div data-testid={CRMC.feeDenied}
        className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
        <p className="font-medium">Akses fee mitra dibatasi</p>
        <p className="mt-1">
          Nominal fee mitra hanya bisa dilihat peran yang berwenang (sales, sales manager,
          marketing, keuangan, direksi). Anda tetap bisa melihat atribusi mitra pada tab
          Ringkasan.
        </p>
      </div>
    );
  }

  const total = fees.reduce((a, f) => a + Number(f.amount_gross || 0), 0);
  const waiting = fees.filter((f) => f.status === "submitted");

  return (
    <div data-testid={CRMC.feeTab} className="space-y-4">
      {scope === "own" ? (
        <p data-testid={CRMC.feeScopeNote}
          className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
          Daftar ini dibatasi pada fee yang <b>Anda ajukan</b> atau yang lahir dari{" "}
          <b>lead/transaksi yang ditugaskan kepada Anda</b>. Fee milik rekan lain memang tidak
          ditampilkan — bukan berarti tidak ada.
        </p>
      ) : null}
      <div data-testid={CRMC.feeAttribution}
        className="rounded-xl border bg-card p-3 text-[13px] shadow-[var(--shadow-card)]">
        <p className="flex items-center gap-1.5 font-medium">
          <Handshake className="h-4 w-4 text-primary" /> Atribusi mitra
        </p>
        {partner ? (
          <p className="mt-1">
            Lead ini teratribusi ke <b>{partner.name}</b>
            {partner.partner_kind ? ` (${partner.partner_kind})` : ""}.{" "}
            <Link to={`/partners/${partner.id}`} data-testid={CRMC.feeOpenPartner}
              className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
              Buka profil mitra <ExternalLink className="h-3 w-3" />
            </Link>
          </p>
        ) : (
          <p className="mt-1 text-muted-foreground">
            Lead ini <b>tidak berasal dari mitra</b> (sumbernya{" "}
            {lead?.source
              ? <RefLabel group="lead_source" value={lead.source} />
              : "tidak dicatat"}),
            jadi tidak ada hak fee yang lahir OTOMATIS darinya.
            {fees.length ? (
              <>
                {" "}Tabel di bawah tetap berisi <b>{fees.length} tagihan fee</b> karena fee itu
                diajukan MANUAL atas transaksi yang lahir dari lead ini — sah, tetapi bukan
                hasil atribusi mitra.
              </>
            ) : (
              " Ini keadaan yang benar, bukan data hilang."
            )}
          </p>
        )}
      </div>

      {!fees.length ? (
        <div data-testid={CRMC.feeEmpty}>
          <EmptyState icon={Handshake} title="Belum ada fee mitra untuk lead ini"
            description={partner
              ? "Fee lahir OTOMATIS saat pemicunya tercapai (mis. booking/akad), bukan diketik manual. Selama pemicunya belum terjadi, memang belum ada angka."
              : "Fee mitra hanya lahir dari lead yang teratribusi ke mitra."} />
        </div>
      ) : (
        <div className="space-y-2">
          <div data-testid={CRMC.feeSummary} className="grid gap-2 sm:grid-cols-3">
            {[["Fee terbit", fees.length], ["Nilai bruto", total],
              ["Menunggu persetujuan", waiting.length]].map(([label, val], i) => (
              <div key={label} className="rounded-lg border bg-secondary/40 px-2.5 py-1.5">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  {label}
                </p>
                <p className="font-semibold tabular-nums">
                  {i === 1 ? <MoneyText value={val} /> : val}
                </p>
              </div>
            ))}
          </div>
          <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <table className="w-full text-[13px]">
              <thead className="bg-secondary/60 text-left text-[12px] text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">No</th>
                  <th className="px-3 py-2">Mitra</th>
                  <th className="px-3 py-2">Pemicu</th>
                  <th className="px-3 py-2 text-right">Bruto</th>
                  <th className="px-3 py-2 text-right">PPh</th>
                  <th className="px-3 py-2 text-right">Neto</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {fees.map((f) => (
                  <tr key={f.id} data-testid={CRMC.feeRow} className="border-t">
                    <td className="px-3 py-2 font-medium">{f.no}</td>
                    <td className="px-3 py-2">{f.agent_name || f.partner_id || "—"}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      <RefLabel group="marketing_fee_trigger" value={f.trigger} /> ·{" "}
                      {formatDateWIB(f.created_at)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      <MoneyText value={f.amount_gross} />
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      <MoneyText value={f.pph_amount} />
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      <MoneyText value={f.amount_net} />
                    </td>
                    <td className="px-3 py-2">
                      <StatusPill group="marketing_fee_status" status={f.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        <p className="flex items-center gap-1.5 text-[13px] font-medium">
          <Info className="h-4 w-4" /> Aturan fee yang berlaku
        </p>
        {!rules.length ? (
          <p className="text-[12px] text-muted-foreground">
            Belum ada aturan fee mitra yang dibuat — tanpa aturan, fee tidak bisa lahir
            otomatis.
          </p>
        ) : (
          <ul className="space-y-1">
            {rules.slice(0, 6).map((r) => (
              <li key={r.id} data-testid={CRMC.feeRuleRow}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-[12px]">
                <span>
                  <b>{r.code}</b> · {r.name}
                  {r.basis ? (
                    <> · basis <RefLabel group="partner_fee_basis" value={r.basis} /></>
                  ) : null}
                  {r.trigger ? (
                    <> · pemicu <RefLabel group="partner_fee_trigger" value={r.trigger} /></>
                  ) : null}
                </span>
                {/* Nilai aturan dibaca sesuai BASISNYA: persentase harga ditulis %, nominal
                    tetap ditulis rupiah, dan aturan berjenjang tidak punya satu angka
                    tunggal — menuliskannya "0" akan menyesatkan. */}
                <span className="tabular-nums text-muted-foreground">
                  {String(r.basis || "").startsWith("percent") ? `${r.value}%`
                    : String(r.basis || "").startsWith("tier")
                      ? `${(r.tiers || []).length} jenjang`
                      : <MoneyText value={r.value} />}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
