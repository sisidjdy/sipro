import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Building2, Compass, Lock, MapPin, MessageCircle, Search, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { LoadingCards } from "@/components/patterns/StateViews";
import ShowroomLeadDialog from "@/components/showroom/ShowroomLeadDialog";
import LegalFooterLinks from "@/components/legal/LegalFooterLinks";
import ShowroomUnitCard from "@/components/showroom/ShowroomUnitCard";
import ShowroomUnitSheet from "@/components/showroom/ShowroomUnitSheet";
import SvgPlanMap from "@/components/siteplan/SvgPlanMap";
import { SALES_COLORS, SALES_ORDER } from "@/components/siteplan/planStyles";
import { formatIDR } from "@/utils/formatters";
import MetricCard from "@/components/patterns/MetricCard";
import publicApi from "@/services/publicClient";
import { SHOWROOM } from "@/constants/testIds";

const PUBLIC_STATUSES = SALES_ORDER.filter((k) => !["ppjb", "akad"].includes(k));

function Metric({ label, value, hint }) {
  return (
    <MetricCard testId={SHOWROOM.metric} label={label} value={value} hint={hint}
      tone="text-foreground" dot={false} />
  );
}

/**
 * PublicShowroom — halaman marketing PUBLIK per proyek (Fase 28b), tanpa login.
 *
 * Dibuka lewat token acak yang dibagikan owner/marketing (`/showroom/:token`). Data yang
 * tampil hanya yang layak publik: kode kavling, tipe, luas, orientasi, harga (bisa
 * dimatikan), status tersedia/terjual, dan peta. Tidak ada nama pembeli maupun angka
 * transaksi — batasannya di backend, bukan sekadar disembunyikan di UI.
 * Form minat langsung menjadi LEAD nyata (dedup nomor + penugasan sales otomatis).
 */
export default function PublicShowroom() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("all");
  const [type, setType] = useState("all");
  const [term, setTerm] = useState("");
  const [pick, setPick] = useState(null);
  const [lead, setLead] = useState(null);   // {open, unitCode}

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await publicApi.get(`/public/showroom/${token}`);
      setData(res.data?.data || null);
    } catch (e) {
      setError(e?.response?.status === 404
        ? "Halaman showroom ini tidak aktif atau tautannya sudah tidak berlaku."
        : (e?.response?.data?.detail || "Gagal memuat halaman showroom."));
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const units = useMemo(() => data?.units || [], [data]);
  const labels = data?.labels || {};
  const project = data?.project || {};
  const stats = data?.stats || {};

  const isMatch = useCallback((u) => {
    if (status !== "all" && u.status !== status) return false;
    if (type !== "all" && u.type !== type) return false;
    if (term && !`${u.code} ${u.type || ""}`.toLowerCase().includes(term.toLowerCase())) return false;
    return true;
  }, [status, type, term]);

  const visible = useMemo(() => units.filter(isMatch), [units, isMatch]);
  const unitsById = useMemo(
    () => Object.fromEntries(units.map((u) => [u.id, u])), [units]);
  const waLink = project.contact_wa
    ? `https://wa.me/${String(project.contact_wa).replace(/\D/g, "")}?text=${encodeURIComponent(`Halo, saya melihat showroom ${project.name || ""} dan ingin bertanya.`)}`
    : null;

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-10">
        <LoadingCards count={3} />
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid={SHOWROOM.closed}
        className="flex min-h-screen items-center justify-center bg-secondary/30 px-4">
        <div className="max-w-md rounded-2xl border bg-card p-8 text-center shadow-sm">
          <Lock className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <h1 className="font-heading text-lg font-semibold">Halaman tidak tersedia</h1>
          <p className="mt-2 text-sm text-muted-foreground">{error}</p>
          <Button variant="outline" className="mt-4" onClick={load}>Coba lagi</Button>
        </div>
      </div>
    );
  }

  return (
    <div data-testid={SHOWROOM.page} className="min-h-screen bg-secondary/20 pb-16">
      <header className="sticky top-0 z-20 border-b bg-card/95 backdrop-blur shadow-[var(--shadow-card)]">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-primary text-primary-foreground">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <p className="font-heading text-sm font-semibold leading-tight">{project.name || "Showroom"}</p>
              <p className="text-[11px] text-muted-foreground">{project.code || "Showroom digital"}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {waLink ? (
              <Button variant="outline" size="sm" data-testid={SHOWROOM.waBtn} asChild>
                <a href={waLink} target="_blank" rel="noreferrer">
                  <MessageCircle className="mr-1.5 h-4 w-4" /> WhatsApp
                </a>
              </Button>
            ) : null}
            <Button size="sm" data-testid={SHOWROOM.leadBtn}
              onClick={() => setLead({ open: true, unitCode: null })}>
              <Sparkles className="mr-1.5 h-4 w-4" /> Saya Tertarik
            </Button>
          </div>
        </div>
      </header>

      <section data-testid={SHOWROOM.hero}
        className="border-b bg-gradient-to-br from-primary/10 via-card to-card">
        <div className="mx-auto max-w-6xl px-4 py-8">
          <h1 data-testid={SHOWROOM.headline}
            className="page-title sm:text-3xl">
            {project.headline || `${project.name || "Proyek kami"} — pilih kavling favorit Anda`}
          </h1>
          <p className="mt-1.5 flex items-center gap-1.5 text-sm text-muted-foreground">
            <MapPin className="h-4 w-4" /> {project.location || "Lokasi proyek"}
          </p>
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="Total kavling" value={stats.total || 0} />
            <Metric label="Masih tersedia" value={stats.available || 0}
              hint={stats.total ? `${Math.round(((stats.available || 0) / stats.total) * 100)}% dari total` : null} />
            <Metric label="Harga mulai"
              value={stats.price_min ? formatIDR(stats.price_min) : "Hubungi kami"} />
            <Metric label="Progres pembangunan" value={`${stats.progress || 0}%`} />
          </div>
        </div>
      </section>

      <main className="mx-auto max-w-6xl space-y-5 px-4 py-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="w-40 space-y-1">
              <span className="text-xs text-muted-foreground">Status</span>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger data-testid={SHOWROOM.statusFilter} aria-label="Filter status kavling">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua status</SelectItem>
                  {PUBLIC_STATUSES.map((k) => (
                    <SelectItem key={k} value={k}>{labels.unit_status?.[k] || k}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="w-44 space-y-1">
              <span className="text-xs text-muted-foreground">Tipe unit</span>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger data-testid={SHOWROOM.typeFilter} aria-label="Filter tipe unit">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Semua tipe</SelectItem>
                  {(data?.types || []).map((t) => (
                    <SelectItem key={t} value={t}>{labels.unit_type?.[t] || t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="w-52 space-y-1">
              <span className="text-xs text-muted-foreground">Cari kavling</span>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input data-testid={SHOWROOM.search} value={term} className="pl-8"
                  placeholder="mis. A-01" aria-label="Cari kode kavling"
                  onChange={(e) => setTerm(e.target.value)} />
              </div>
            </div>
          </div>
          <p data-testid={SHOWROOM.visibleCount} className="text-sm text-muted-foreground">
            Menampilkan <span className="font-semibold text-foreground">{visible.length}</span> dari {units.length} kavling
          </p>
        </div>

        {data?.plan?.shapes?.length ? (
          <div data-testid={SHOWROOM.map} className="rounded-2xl border bg-card p-3 shadow-sm">
            <p className="mb-2 text-xs text-muted-foreground">
              Ketuk kavling untuk melihat detail · cubit dua jari atau tombol +/− untuk zoom.
            </p>
            <SvgPlanMap viewBox={data.plan.view_box} shapes={data.plan.shapes}
              background={data.plan.background}
              unitsById={unitsById} mode="sales" height={460} isMatch={isMatch}
              selectedId={pick?.id} onSelect={(p) => setPick(p.unit)} />
            <div data-testid={SHOWROOM.legend} className="mt-2 flex flex-wrap items-center gap-2">
              {PUBLIC_STATUSES.map((k) => (
                <span key={k} data-testid={SHOWROOM.legendItem}
                  className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs">
                  <span className="h-2.5 w-2.5 rounded-sm"
                    style={{ backgroundColor: SALES_COLORS[k].dot }} />
                  {labels.unit_status?.[k] || k}
                  <span className="tabular-nums text-muted-foreground">
                    {units.filter((u) => u.status === k).length}
                  </span>
                </span>
              ))}
            </div>
          </div>
        ) : (
          <p className="rounded-2xl border bg-card p-6 text-center text-sm text-muted-foreground shadow-[var(--shadow-card)]">
            Peta kavling sedang disiapkan — daftar kavling di bawah tetap bisa dilihat.
          </p>
        )}

        <div>
          <h2 className="mb-2 flex items-center gap-1.5 font-heading text-base font-semibold">
            <Compass className="h-4 w-4 text-primary" /> Daftar kavling
          </h2>
          {!units.length ? (
            <p className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground shadow-[var(--shadow-card)]">
              Belum ada kavling yang dipublikasikan untuk proyek ini.
            </p>
          ) : !visible.length ? (
            <p className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground shadow-[var(--shadow-card)]">
              Tidak ada kavling yang cocok dengan filter Anda.
            </p>
          ) : (
            <div data-testid={SHOWROOM.list}
              className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {visible.map((u) => (
                <ShowroomUnitCard key={u.id} unit={u} labels={labels} onOpen={setPick} />
              ))}
            </div>
          )}
        </div>

        <div className="rounded-2xl border bg-card p-5 text-center shadow-sm">
          <p className="section-title">Butuh bantuan memilih kavling?</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Tinggalkan nama & nomor WhatsApp — tim marketing akan membantu Anda.
          </p>
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            <Button onClick={() => setLead({ open: true, unitCode: null })}>
              <Sparkles className="mr-1.5 h-4 w-4" /> Saya Tertarik
            </Button>
            {waLink ? (
              <Button variant="outline" asChild>
                <a href={waLink} target="_blank" rel="noreferrer">
                  <MessageCircle className="mr-1.5 h-4 w-4" /> Chat WhatsApp
                </a>
              </Button>
            ) : null}
          </div>
        </div>

        <p className="text-center text-[11px] text-muted-foreground">
          Ketersediaan, harga, dan spesifikasi dapat berubah sewaktu-waktu. Data pembeli lain
          tidak ditampilkan di halaman ini.
        </p>
        <LegalFooterLinks />
      </main>

      {pick ? (
        <ShowroomUnitSheet unit={pick} labels={labels} onClose={() => setPick(null)}
          onAsk={(u) => { setPick(null); setLead({ open: true, unitCode: u.code }); }} />
      ) : null}

      <ShowroomLeadDialog open={!!lead?.open} token={token} unitCode={lead?.unitCode}
        projectName={project.name} onOpenChange={(v) => setLead(v ? lead : null)} />
    </div>
  );
}
