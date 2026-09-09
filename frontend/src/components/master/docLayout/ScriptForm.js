import React, { useRef } from "react";
import { FileText, RotateCcw, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { RichScriptEditor } from "./RichScriptEditor";
import { Label } from "@/components/ui/label";
import { P60 } from "@/constants/testIds";

/**
 * ScriptForm — NASKAH dokumen per jenis (Fase 66).
 *
 * Dulu naskah hidup di tab lain ("Isi template") dengan kode bebas, sehingga tidak ada yang
 * tahu naskah mana yang dipakai dokumen mana, dan pratinjau tidak pernah menampilkan isinya.
 * Sekarang naskah menempel pada JENIS dokumen yang sedang disetel: placeholder yang
 * ditawarkan mengikuti kategorinya (kwitansi tidak ditawari "batas booking"), dan naskah ini
 * yang benar-benar tercetak — pratinjau di kanan memakainya.
 */
export default function ScriptForm({ script, content, onChange, onSave, onUseDefault,
  saving }) {
  const editorRef = useRef(null);
  if (!script) return null;
  const insert = (token) => editorRef.current?.insert(token);
  const vocab = new Set((script.placeholders || []).map((p) => p.token));
  // Peringatan HIDUP saat mengetik: pemakai tahu tokennya salah sebelum menekan simpan,
  // bukan sesudah server menolak (temuan uji Fase 66).
  const dariLayar = [...new Set(
    Array.from((content || "").matchAll(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g), (m) => m[1])
      .filter((t) => !vocab.has(t)))].sort();
  const unknown = dariLayar;

  return (
    <div className="space-y-3">
      <p data-testid={P60.scriptCategory}
        className="rounded-lg border bg-secondary/40 px-3 py-2 text-[12px] text-muted-foreground">
        Kategori naskah: <strong>{script.category_label}</strong>. Placeholder di bawah
        adalah satu-satunya yang akan terisi untuk jenis dokumen ini.
      </p>

      <div className="space-y-1.5">
        <Label htmlFor="doc-script-content">Naskah dokumen (tercetak di dalam dokumen)</Label>
        <RichScriptEditor ref={editorRef} value={content || ""} onChange={onChange} />
      </div>

      {unknown.length ? (
        <p data-testid={P60.scriptUnknown}
          className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
          Placeholder ini tidak dikenal untuk jenis dokumen ini dan akan tercetak mentah:{" "}
          {unknown.map((t) => `{{${t}}}`).join(", ")}
        </p>
      ) : null}

      <div className="space-y-1.5">
        <p className="text-[12px] font-medium">Placeholder yang tersedia (klik untuk menyisipkan)</p>
        <div className="flex flex-wrap gap-1.5">
          {(script.placeholders || []).map((p) => (
            <button key={p.token} type="button" data-testid={`${P60.scriptPlaceholder}-${p.token}`}
              onClick={() => insert(p.token)} title={`Contoh: ${p.sample}`}
              className="rounded-full border bg-card px-2.5 py-1 font-mono text-[11px] transition-colors hover:bg-secondary shadow-[var(--shadow-card)]">
              {`{{${p.token}}}`} <span className="font-sans text-muted-foreground">{p.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" data-testid={P60.scriptSave} onClick={onSave} disabled={saving || !!unknown.length}>
          <Save className="mr-1.5 h-3.5 w-3.5" />
          {saving ? "Menyimpan…" : "Simpan naskah"}
        </Button>
        <Button size="sm" variant="outline" data-testid={P60.scriptDefault}
          onClick={onUseDefault}>
          <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Pakai naskah bawaan kategori
        </Button>
        <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
          <FileText className="h-3.5 w-3.5" />
          Naskah ini dipakai saat dokumen {script.code} diterbitkan.
        </span>
      </div>
    </div>
  );
}
