import React from "react";
import { Link } from "react-router-dom";
import { LEGAL } from "@/constants/testIds";

/** Tautan legal untuk halaman publik/login: Privasi · S&K · Penghapusan Data. */
export default function LegalFooterLinks({ className = "" }) {
  const cls = "hover:text-foreground hover:underline underline-offset-2 transition-colors";
  return (
    <p data-testid={LEGAL.footerLinks} className={`flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground ${className}`}>
      <Link data-testid={LEGAL.footerPrivacy} to="/privacy" className={cls}>Kebijakan Privasi</Link>
      <span aria-hidden="true">·</span>
      <Link data-testid={LEGAL.footerTerms} to="/terms" className={cls}>Syarat &amp; Ketentuan</Link>
      <span aria-hidden="true">·</span>
      <Link data-testid={LEGAL.footerDeletion} to="/data-deletion" className={cls}>Penghapusan Data</Link>
    </p>
  );
}
