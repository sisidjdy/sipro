import React, { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

// Worker pdf.js DIBUNDEL webpack (jadi berkas .js ber-hash), bukan diambil dari
// `/pdf.worker.min.mjs`. Di produksi nginx mengirim .mjs sebagai application/octet-stream
// sehingga module worker ditolak browser dan pratinjau selalu gagal.
let sharedWorker = null;
const ensureWorker = () => {
  if (GlobalWorkerOptions.workerPort) return;
  try {
    sharedWorker = new Worker(
      new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url), { type: "module" });
    GlobalWorkerOptions.workerPort = sharedWorker;
  } catch {
    GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
  }
};

const openPdf = async (url) => {
  ensureWorker();
  try {
    const task = getDocument({ url });
    const timeout = new Promise((_, rej) => setTimeout(
      () => rej(new Error("worker pdf.js tidak menjawab")), 15000));
    return await Promise.race([task.promise, timeout]);
  } catch (e) {
    if (!GlobalWorkerOptions.workerPort) throw e;
    // Worker bundel gagal (mis. CSP) → coba jalur berkas publik sebelum menyerah.
    sharedWorker?.terminate?.();
    sharedWorker = null;
    GlobalWorkerOptions.workerPort = null;
    GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
    return getDocument({ url }).promise;
  }
};

export const DocumentPreview = ({ url }) => {
  const canvas = useRef(null);
  const [pdf, setPdf] = useState(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [error, setError] = useState("");
  useEffect(() => {
    setError(""); setPdf(null); setPageNumber(1);
    let active = true, doc;
    openPdf(url).then(d => { doc = d; if (active) setPdf(d); else d.destroy(); }).catch(e => {
      if (active) setError(`Pratinjau belum dapat ditampilkan (${e?.message || "kesalahan tidak dikenal"}). Silakan segarkan.`);
    });
    return () => { active = false; doc?.destroy(); };
  }, [url]);
  useEffect(() => {
    if (!pdf || !canvas.current) return;
    let active = true, render;
    pdf.getPage(pageNumber).then(page => {
      if (!active || !canvas.current) return;
      const viewport = page.getViewport({ scale: 1.5 });
      canvas.current.width = viewport.width; canvas.current.height = viewport.height;
      render = page.render({ canvasContext: canvas.current.getContext("2d"), viewport });
      return render.promise;
    }).catch(e => { if (active && e?.name !== "RenderingCancelledException") setError("Gagal menampilkan halaman PDF."); });
    return () => { active = false; render?.cancel(); };
  }, [pdf, pageNumber]);
  return <div data-testid="doc-layout-preview" className="min-w-0 overflow-hidden rounded-lg border bg-muted/40">
    <div className="flex items-center justify-center gap-3 border-b p-2">
      <Button size="icon" variant="ghost" data-testid="doc-preview-prev" aria-label="Halaman sebelumnya" disabled={!pdf || pageNumber <= 1} onClick={() => setPageNumber(n => n - 1)}><ChevronLeft className="h-4 w-4" /></Button>
      <span data-testid="doc-preview-page" className="text-xs tabular-nums">{pdf ? `Halaman ${pageNumber} dari ${pdf.numPages}` : "Memuat halaman…"}</span>
      <Button size="icon" variant="ghost" data-testid="doc-preview-next" aria-label="Halaman berikutnya" disabled={!pdf || pageNumber >= pdf.numPages} onClick={() => setPageNumber(n => n + 1)}><ChevronRight className="h-4 w-4" /></Button>
    </div>
    {error ? <p role="alert" data-testid="doc-preview-canvas-error" className="p-4 text-sm text-destructive">{error}</p> :
      <canvas ref={canvas} data-testid="doc-preview-canvas" aria-label={`Pratinjau halaman ${pageNumber}`} className="h-auto w-full bg-white" />}
  </div>;
};