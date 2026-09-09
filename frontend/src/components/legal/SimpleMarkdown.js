import React from "react";

// Inline: **bold**, *italic*, [teks](url). Cukup untuk naskah legal; tanpa dependensi baru.
function inline(text, key) {
  const parts = [];
  const re = /\*\*(.+?)\*\*|\*(?!\s)([^*]+?)\*|\[([^\]]+)\]\((https?:\/\/[^\s)]+|\/[^\s)]*)\)/g;
  let last = 0; let m; let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[1]) parts.push(<strong key={`${key}-b${i++}`}>{m[1]}</strong>);
    else if (m[2]) parts.push(<em key={`${key}-i${i++}`}>{m[2]}</em>);
    else parts.push(<a key={`${key}-a${i++}`} href={m[4]} className="text-primary underline underline-offset-2" target={m[4].startsWith("http") ? "_blank" : undefined} rel="noreferrer">{m[3]}</a>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

const ORDERED = /^(\s*)(\d+|[a-z]|[ivx]+)[.)]\s+(.*)$/i;
const BULLET = /^(\s*)[-*•]\s+(.*)$/;

/** Ubah baris-baris daftar menjadi pohon bersarang berdasarkan indentasi (2 spasi = 1 tingkat). */
function parseList(lines) {
  const root = { items: [] };
  const stack = [{ node: root, depth: -1 }];
  lines.forEach((l) => {
    const m = ORDERED.exec(l) || BULLET.exec(l);
    if (!m) { // baris lanjutan paragraf di dalam butir
      const parent = stack[stack.length - 1].node;
      const lastItem = parent.items[parent.items.length - 1];
      if (lastItem) lastItem.text += ` ${l.trim()}`;
      return;
    }
    const ordered = m.length === 4;
    const depth = Math.floor(m[1].replace(/\t/g, "  ").length / 2);
    const item = { text: ordered ? m[3] : m[2], marker: ordered ? m[2] : null, items: [], ordered };
    while (stack.length > 1 && stack[stack.length - 1].depth >= depth) stack.pop();
    stack[stack.length - 1].node.items.push(item);
    stack.push({ node: item, depth });
  });
  return root.items;
}

function markerType(marker) {
  if (!marker) return "disc";
  if (/^\d+$/.test(marker)) return "decimal";
  if (/^[ivx]+$/i.test(marker)) return marker === marker.toLowerCase() ? "lower-roman" : "upper-roman";
  return marker === marker.toLowerCase() ? "lower-alpha" : "upper-alpha";
}

/** Daftar dengan indentasi gantung: nomor di kolom kiri, teks & sub-butir rata pada kolom teks. */
function List({ items, keyBase }) {
  const first = items[0];
  const style = { listStyleType: markerType(first.marker) };
  const start = first.ordered && /^\d+$/.test(first.marker) ? Number(first.marker) : undefined;
  const children = items.map((it, i) => renderItem(it, `${keyBase}-${i}`));
  if (first.ordered) return <ol start={start} className="legal-list mt-1.5 space-y-1.5" style={style}>{children}</ol>;
  return <ul className="legal-list mt-1.5 space-y-1.5" style={style}>{children}</ul>;
}

function renderItem(it, key) {
  const sub = it.items.length ? <List items={it.items} keyBase={key} /> : null;
  return <li key={key} className="pl-1.5">{inline(it.text, key)}{sub}</li>;
}

/**
 * Perender Markdown ringan untuk naskah legal, mengikuti kaidah tata letak dokumen resmi:
 * seluruh teks rata kiri (bukan justify agar spasi kata tidak melebar), judul berjenjang,
 * daftar bernomor 1./a./i. dengan indentasi gantung (baris lanjutan sejajar dengan awal teks,
 * bukan dengan nomor), sub-butir menjorok di bawah teks induknya, dan paragraf dipisah
 * satu baris kosong.
 */
export default function SimpleMarkdown({ text = "", className = "" }) {
  const blocks = text.replace(/\r/g, "").split(/\n{2,}/);
  return (
    <div className={`legal-prose space-y-4 text-left text-[15px] leading-relaxed ${className}`}>
      {blocks.map((raw, bi) => {
        const b = raw.replace(/\s+$/, "");
        if (!b.trim()) return null;
        const t = b.trim();
        if (t.startsWith("### ")) return <h3 key={bi} className="font-heading pt-1 text-base font-semibold">{inline(t.slice(4), bi)}</h3>;
        if (t.startsWith("## ")) return <h2 key={bi} className="font-heading pt-3 text-lg font-semibold">{inline(t.slice(3), bi)}</h2>;
        if (t.startsWith("# ")) return <h1 key={bi} className="page-title">{inline(t.slice(2), bi)}</h1>;
        if (/^-{3,}$/.test(t)) return <hr key={bi} className="border-border" />;
        const lines = b.split("\n");
        if (ORDERED.test(lines[0]) || BULLET.test(lines[0])) {
          return <List key={bi} items={parseList(lines)} keyBase={bi} />;
        }
        if (t.startsWith("> ")) {
          return <blockquote key={bi} className="border-l-4 border-primary/40 pl-4 italic text-muted-foreground">{inline(t.replace(/^> ?/gm, ""), bi)}</blockquote>;
        }
        return (
          <p key={bi}>
            {lines.map((l, li) => <React.Fragment key={li}>{li ? <br /> : null}{inline(l.trim(), `${bi}-${li}`)}</React.Fragment>)}
          </p>
        );
      })}
    </div>
  );
}
