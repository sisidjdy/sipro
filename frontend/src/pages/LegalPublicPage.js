import React, { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Building2, Languages, ShieldCheck } from "lucide-react";
import SimpleMarkdown from "@/components/legal/SimpleMarkdown";
import DeletionRequestForm from "@/components/legal/DeletionRequestForm";
import { LEGAL } from "@/constants/testIds";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const PAGE_BY_PATH = { "/privacy": "privacy", "/terms": "terms", "/data-deletion": "deletion" };
const NAV = [
  { key: "privacy", path: "/privacy", id: "Kebijakan Privasi", en: "Privacy Policy", tid: LEGAL.navPrivacy },
  { key: "terms", path: "/terms", id: "Syarat & Ketentuan", en: "Terms & Conditions", tid: LEGAL.navTerms },
  { key: "deletion", path: "/data-deletion", id: "Penghapusan Data", en: "Data Deletion", tid: LEGAL.navDeletion },
];

/** Halaman legal PUBLIK (tanpa login) — dibaca calon pembeli & Meta App Review. */
export default function LegalPublicPage() {
  const { pathname } = useLocation();
  const [params, setParams] = useSearchParams();
  const lang = params.get("lang") === "en" ? "en" : "id";
  const page = PAGE_BY_PATH[pathname] || "privacy";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    axios.get(`${API}/legal/public`, { params: { lang, public_base: window.location.origin } })
      .then((r) => setData(r.data.data))
      .catch(() => setError(lang === "en" ? "Failed to load page." : "Gagal memuat halaman."));
  }, [lang]);

  const toggleLang = () => { const n = new URLSearchParams(params); n.set("lang", lang === "id" ? "en" : "id"); setParams(n, { replace: true }); };
  const content = data?.pages?.[page]?.content || "";
  const brand = data?.identity?.brand || "SIPRO";

  return (
    <div data-testid={LEGAL.publicPage} className="min-h-screen bg-background app-noise">
      <header className="border-b bg-card/80 backdrop-blur">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-foreground"><Building2 className="h-5 w-5" /></div>
            <div><p className="font-heading font-bold leading-none">{brand}</p>
              <p className="text-[11px] text-muted-foreground">{data?.identity?.company_name || ""}</p></div>
          </div>
          <button type="button" data-testid={LEGAL.langToggle} onClick={toggleLang}
            className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors hover:bg-secondary">
            <Languages className="h-3.5 w-3.5" /> {lang === "id" ? "English" : "Bahasa Indonesia"}
          </button>
        </div>
        <nav className="mx-auto flex max-w-3xl gap-1 px-4 pb-3 text-sm">
          {NAV.map((n) => (
            <Link key={n.key} to={`${n.path}?lang=${lang}`} data-testid={n.tid}
              className={`rounded-lg px-3 py-1.5 transition-colors ${page === n.key ? "bg-primary text-primary-foreground" : "text-foreground/70 hover:bg-secondary"}`}>
              {lang === "en" ? n.en : n.id}
            </Link>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-3xl space-y-8 px-4 py-8">
        {error ? <p className="text-sm text-rose-600">{error}</p> : null}
        {!data && !error ? <p className="animate-pulse text-sm text-muted-foreground">{lang === "en" ? "Loading…" : "Memuat…"}</p> : null}
        {data ? (
          <article data-testid={LEGAL.publicContent} className="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
            <SimpleMarkdown text={content} />
          </article>
        ) : null}
        {page === "deletion" && data ? <DeletionRequestForm lang={lang} /> : null}
        <p className="flex items-center gap-1.5 text-center text-[11px] text-muted-foreground">
          <ShieldCheck className="h-3.5 w-3.5" />
          {lang === "en" ? "Complies with Indonesian PDP Law No. 27/2022 and the WhatsApp Business Policy." : "Mematuhi UU PDP No. 27/2022 dan Kebijakan Bisnis WhatsApp."}
          {data?.updated_at ? ` · ${lang === "en" ? "Updated" : "Diperbarui"} ${data.updated_at.slice(0, 10)}` : ""}
        </p>
      </main>
    </div>
  );
}
