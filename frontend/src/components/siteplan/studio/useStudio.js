import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import api from "@/services/apiClient";
import { buildExportSvg, downloadPng } from "@/components/siteplan/studio/exportPng";
import { COLOR_MODES, mergePalette } from "@/components/siteplan/studio/studioPalette";
import { useReference } from "@/context/ReferenceContext";

const MODE_KEY = "sipro.studio.colorMode";
const readMode = () => { const v = localStorage.getItem(MODE_KEY); return COLOR_MODES.some((m) => m.key === v) ? v : "mapping"; };

const pointsOf = (sh) => String(sh?.geom?.points || "").trim().split(/\s+/).filter(Boolean)
  .map((p) => p.split(",").map(Number)).filter((p) => p.length === 2 && p.every((n) => !Number.isNaN(n)));

/** State & aksi Studio Site Plan — satu sumber untuk kanvas, toolbar, dan panel sisi. */
export default function useStudio(projectId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [tool, setTool] = useState("select"); // select | draw | sequence
  const [selectedId, setSelectedId] = useState(null);
  const [seqQueue, setSeqQueue] = useState([]);
  const [colorMode, setColorModeState] = useState(readMode); // mapping | sales | build | dual (diingat per browser)
  const setColorMode = (m) => { localStorage.setItem(MODE_KEY, m); setColorModeState(m); };
  const [undoStack, setUndoStack] = useState([]);
  const pushUndo = (entry) => setUndoStack((st) => [...st.slice(-29), entry]);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const res = await api.get(`/site-plan-studio/${projectId}`);
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat studio.");
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const run = useCallback(async (label, fn, okMsg) => {
    setBusy(label);
    try {
      const out = await fn();
      if (okMsg) toast.success(typeof okMsg === "function" ? okMsg(out) : okMsg);
      await load();
      return out;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aksi gagal diproses.");
      return null;
    } finally { setBusy(""); }
  }, [load]);

  const plan = data?.plan || null;
  const { labelOf } = useReference();
  const palette = useMemo(() => mergePalette(data?.palette, labelOf), [data, labelOf]);
  const savePalette = (diff) => run("palette", () => api.put("/site-plan-studio/palette", { palette: diff }), "Palet warna disimpan untuk seluruh tim.");
  const shapes = useMemo(() => plan?.shapes || [], [plan]);
  const units = useMemo(() => data?.units || [], [data]);
  const unitsById = useMemo(() => Object.fromEntries(units.map((u) => [u.id, u])), [units]);
  const mappedIds = useMemo(() => new Set(shapes.map((s) => s.unit_id).filter(Boolean)), [shapes]);
  const unmappedUnits = useMemo(() => units.filter((u) => !mappedIds.has(u.id))
    .sort((a, b) => String(a.code).localeCompare(String(b.code), "id", { numeric: true })),
  [units, mappedIds]);
  const unmappedLots = useMemo(() => shapes.filter((s) => s.kind === "lot" && !s.unit_id), [shapes]);
  const selected = shapes.find((s) => s.shape_id === selectedId) || null;

  const uploadSvg = (file) => new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(run("svg", async () => (await api.post(
      `/site-plan-studio/${projectId}/svg`, { svg: String(reader.result || ""), filename: file.name },
    )).data.data, (d) => `SVG terbaca: ${d.detected.shapes} bentuk, ${d.detected.lots} kavling, ${d.detected.labeled} berlabel, ${d.auto_matched} cocok otomatis.`));
    reader.readAsText(file);
  });

  const uploadImage = (file, page = 1) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("page", String(page));
    return run("image", async () => (await api.post(`/site-plan-studio/${projectId}/background`, fd,
      { headers: { "Content-Type": "multipart/form-data" } })).data.data,
    (d) => d.plan?.background?.source === "pdf" ? `Halaman ${d.plan.background.pdf_page}/${d.plan.background.pdf_pages} PDF dirender jadi latar — gambar poligon kavling di atasnya.` : "Gambar latar dipasang — gambar poligon kavling di atasnya.");
  };

  const removeImage = () => run("image", () => api.delete(`/site-plan-studio/${projectId}/background`), "Gambar latar dilepas.");
  const autoMatch = () => run("match", async () => (await api.post(`/site-plan-studio/${projectId}/auto-match`)).data.data,
    (d) => `${d.matched} kavling tercocokkan otomatis · cakupan ${d.stats.coverage_pct}%.`);
  const generate = () => run("generate", () => api.post(`/site-plan/${projectId}/generate`), "Peta contoh dibangkitkan dari daftar unit.");
  const deletePlan = () => run("delete", () => api.delete(`/site-plan/${projectId}/plan`), "Peta dihapus.");

  const addShape = (points, kind = "lot", extra = {}) => run("shape", async () => {
    const res = await api.post(`/site-plan-studio/${projectId}/shapes`, { items: [{ points, kind, ...extra }] });
    const added = res.data.data.added?.[0];
    if (added) { setSelectedId(added.shape_id); pushUndo({ type: "delete", sid: added.shape_id }); }
    return added;
  }, "Bentuk ditambahkan.");

  const patchShape = (sid, patch, { silent = false } = {}) => run("shape", async () => {
    const before = shapes.find((x) => x.shape_id === sid);
    if (before && patch.points) pushUndo({ type: "points", sid, points: pointsOf(before) });
    return api.put(`/site-plan-studio/${projectId}/shapes/${sid}`, patch);
  }, silent ? null : "Bentuk diperbarui.");
  const deleteShape = (sid) => run("shape", async () => {
    const before = shapes.find((x) => x.shape_id === sid);
    await api.delete(`/site-plan-studio/${projectId}/shapes/${sid}`);
    setSelectedId(null);
    if (before) pushUndo({ type: "restore", shape: before });
  }, "Bentuk dihapus.");

  /** Undo langkah terakhir pada bentuk (titik, tambah, hapus). */
  const undo = async () => {
    const last = undoStack[undoStack.length - 1];
    if (!last) return;
    setUndoStack((st) => st.slice(0, -1));
    await run("undo", async () => {
      if (last.type === "points") await api.put(`/site-plan-studio/${projectId}/shapes/${last.sid}`, { points: last.points });
      else if (last.type === "delete") { await api.delete(`/site-plan-studio/${projectId}/shapes/${last.sid}`); setSelectedId(null); }
      else if (last.type === "restore") {
        const sh = last.shape;
        const res = await api.post(`/site-plan-studio/${projectId}/shapes`, { items: [{ points: pointsOf(sh), kind: sh.kind, label: sh.label, unit_id: sh.unit_id }] });
        setSelectedId(res.data.data.added?.[0]?.shape_id || null);
      }
    }, "Langkah dibatalkan.");
  };

  const exportPng = async () => {
    if (!plan) return;
    setBusy("export");
    try {
      const svg = await buildExportSvg({ plan, unitsById, colorMode, palette, title: data?.project_name || "" });
      await downloadPng(svg, `siteplan-${projectId.slice(0, 8)}-${colorMode}.png`);
      toast.success("PNG site plan diunduh — siap untuk brosur / WhatsApp.");
    } catch (e) { toast.error(e?.message || "Gagal mengekspor PNG."); } finally { setBusy(""); }
  };

  const assignUnit = (sid, unitId) => run("map", () => api.put(`/site-plan/${projectId}/mapping`,
    { items: [{ shape_id: sid, unit_id: unitId || "" }] }), unitId ? "Kavling dipetakan ke unit." : "Pemetaan dilepas.");

  /** Mode berurutan: klik kavling kosong → unit teratas antrean dipetakan. */
  const clickShape = async (shape) => {
    if (tool === "sequence" && shape.kind === "lot" && !shape.unit_id) {
      const next = seqQueue[0] || unmappedUnits[0];
      if (!next) { toast.info("Semua unit sudah terpetakan."); return; }
      setSelectedId(shape.shape_id);
      await assignUnit(shape.shape_id, next.id);
      setSeqQueue((q) => q.filter((u) => u.id !== next.id));
      return;
    }
    setSelectedId(shape.shape_id);
  };

  return {
    data, plan, shapes, units, unitsById, unmappedUnits, unmappedLots, selected, selectedId,
    loading, error, busy, tool, setTool, seqQueue, setSeqQueue, setSelectedId, load,
    uploadSvg, uploadImage, removeImage, autoMatch, generate, deletePlan, addShape,
    patchShape, deleteShape, assignUnit, clickShape, projectId,
    colorMode, setColorMode, undo, canUndo: undoStack.length > 0, exportPng, palette, savePalette,
  };
}
