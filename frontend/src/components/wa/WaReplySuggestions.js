import React, { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

import api from "@/services/apiClient";
import { cn } from "@/lib/utils";
import { P97 } from "@/constants/testIds";

/** Balasan Cerdas (Fase 99): saran berbasis playbook tahap lead & kata kunci pesan masuk — tanpa LLM. */
export default function WaReplySuggestions({ contactId, onPick }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!contactId) return;
    setData(null); setError("");
    api.get(`/wa/contacts/${contactId}/suggestions`).then((r) => setData(r.data.data))
      .catch((e) => setError(e?.response?.data?.detail || "Saran balasan gagal dimuat."));
  }, [contactId]);

  if (error) return <p className="text-xs text-destructive" data-testid={P97.replySuggestions}>{error}</p>;
  if (!data) return <p className="text-xs text-muted-foreground" data-testid={P97.replySuggestions}>Memuat saran…</p>;
  return (
    <div className="space-y-1.5" data-testid={P97.replySuggestions} data-stage={data.stage || "none"}>
      <p className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
        <Sparkles className="h-3 w-3" /> Saran balasan {data.stage ? `· tahap lead: ${data.stage}` : "· belum jadi lead"}
      </p>
      {!data.items.length ? (
        <p className="text-xs italic text-muted-foreground">Tidak ada saran untuk tahap ini — playbook belum menyasar tahap lead ini atau template-nya belum ada.</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {data.items.map((s) => (
            <button key={s.template_code || s.body} type="button" disabled={!s.usable}
              data-testid={P97.replySuggestion} data-template={s.template_code || ""} data-source={s.source}
              title={s.hint || `${s.reason}\n\n${s.body}`} onClick={() => onPick(s)}
              className={cn("rounded-full border px-2.5 py-1 text-left text-xs transition-colors",
                s.usable ? "bg-card hover:border-primary/50 hover:bg-accent" : "cursor-not-allowed opacity-50")}>
              <span className="font-medium">{s.title}</span>
              <span className="ml-1 text-muted-foreground">· {s.template_name}{s.ready ? "" : " (belum approved)"}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
