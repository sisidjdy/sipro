import React, { useEffect, useState } from "react";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";

const CACHE_KEY = "sipro:projects";

/**
 * Pemilih proyek bersama; memilih proyek pertama otomatis dan melaporkan daftarnya.
 *
 * Fase 35: daftar proyek ikut disimpan di perangkat. Tanpa ini, mandor yang membuka ulang
 * aplikasi di lokasi tanpa sinyal mendapat "Pilih proyek" kosong sehingga Papan Mandor
 * (beserta antrean pekerjaannya) tidak bisa dibuka sama sekali.
 */
export default function ProjectSelect({ value, onChange, testId, onLoaded }) {
  const [projects, setProjects] = useState([]);

  useEffect(() => {
    let alive = true;
    const apply = (list, cache) => {
      if (!alive) return;
      setProjects(list);
      onLoaded && onLoaded(list);
      if (!value && list.length) onChange(list[0].id);
      if (cache) {
        try { localStorage.setItem(CACHE_KEY, JSON.stringify(list)); } catch { /* kuota */ }
      }
    };
    (async () => {
      try {
        const res = await api.get("/projects");
        apply(res.data.data || [], true);
      } catch (e) {
        let list = [];
        if (!e?.response) {
          try { list = JSON.parse(localStorage.getItem(CACHE_KEY) || "[]"); } catch { list = []; }
        }
        apply(Array.isArray(list) ? list : [], false);
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Select value={value || ""} onValueChange={onChange}>
      <SelectTrigger data-testid={testId} className="w-full sm:w-72">
        <SelectValue placeholder="Pilih proyek" />
      </SelectTrigger>
      <SelectContent>
        {projects.map((p) => (
          <SelectItem key={p.id} value={p.id}>{p.name} ({p.code})</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
