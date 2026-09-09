import React, { forwardRef, useEffect, useImperativeHandle } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import TextAlign from "@tiptap/extension-text-align";
import { TableKit } from "@tiptap/extension-table";
import { TextSelection } from "@tiptap/pm/state";
import { AlignLeft, AlignCenter, AlignRight, AlignJustify, Bold, Italic, Underline,
  List, ListOrdered, Undo2, Redo2, Table2, ArrowUp, ArrowDown, Trash2, Plus, Minus } from "lucide-react";
import DOMPurify from "dompurify";
import { Button } from "@/components/ui/button";
import { P60 } from "@/constants/testIds";
import "./richScript.css";

const html = (value) => /<(p|h[1-3]|table|ul|ol|div|blockquote)(\s|>)/i.test(value || "")
  ? DOMPurify.sanitize(value) : (value || "").split("\n").map(line => `<p>${DOMPurify.sanitize(line) || "<br>"}</p>`).join("");

// Move the selected top-level table without copying or losing its cell formatting.
function moveTable(editor, direction) {
  const { $from } = editor.state.selection;
  let depth = $from.depth;
  while (depth > 0 && $from.node(depth).type.name !== "table") depth--;
  if (!depth || depth !== 1) return;
  const pos = $from.before(depth), table = $from.node(depth), doc = editor.state.doc;
  const index = $from.index(0);
  if (direction < 0 && index > 0) {
    const prev = doc.child(index - 1), start = pos - prev.nodeSize;
    const tr = editor.state.tr.replaceWith(start, pos + table.nodeSize, [table, prev]);
    editor.view.dispatch(tr.setSelection(TextSelection.near(tr.doc.resolve(start + 1))));
  } else if (direction > 0 && index < doc.childCount - 1) {
    const next = doc.child(index + 1);
    const tr = editor.state.tr.replaceWith(pos, pos + table.nodeSize + next.nodeSize, [next, table]);
    editor.view.dispatch(tr.setSelection(TextSelection.near(tr.doc.resolve(pos + next.nodeSize + 1))));
  }
  editor.commands.focus();
}

export const RichScriptEditor = forwardRef(function RichScriptEditor({ value, onChange }, ref) {
  const editor = useEditor({
    extensions: [StarterKit.configure({ heading: { levels: [1, 2, 3] }, link: false }),
      TextAlign.configure({ types: ["heading", "paragraph"] }), TableKit.configure({ table: { resizable: false } })],
    content: html(value),
    editorProps: { attributes: { "data-testid": P60.scriptText, id: "doc-script-content",
      role: "textbox", "aria-label": "Naskah dokumen", "aria-multiline": "true", class: "document-prose" } },
    onUpdate: ({ editor: e }) => onChange(e.getHTML()),
    shouldRerenderOnTransaction: true,
  });
  useImperativeHandle(ref, () => ({ insert: (token) => editor?.chain().focus().insertContent(
    token.startsWith("tabel_") ? `<p>{{${token}}}</p><p></p>` : `{{${token}}}`).run() }), [editor]);
  useEffect(() => {
    if (editor && value !== editor.getHTML()) editor.commands.setContent(html(value), { emitUpdate: false });
  }, [editor, value]);
  if (!editor) return null;
  const tool = (id, label, Icon, action, active = false, disabled = false) => (
    <Button key={id} type="button" size="icon" variant={active ? "secondary" : "ghost"}
      className="h-8 w-8 shrink-0" data-testid={`script-${id}`} title={label} aria-label={label}
      aria-pressed={active} disabled={disabled} onMouseDown={e => e.preventDefault()} onClick={action}>
      <Icon className="h-4 w-4" />
    </Button>
  );
  const table = editor.isActive("table");
  return <div className="script-editor min-w-0 rounded-md border bg-card" data-testid="rich-script-editor">
    <div className="flex flex-wrap items-center gap-0.5 border-b bg-muted/50 p-1" role="toolbar" aria-label="Format naskah">
      {tool("undo", "Urungkan", Undo2, () => editor.chain().focus().undo().run(), false, !editor.can().undo())}
      {tool("redo", "Ulangi", Redo2, () => editor.chain().focus().redo().run(), false, !editor.can().redo())}
      <span className="mx-1 h-5 border-l" />
      {tool("bold", "Tebal", Bold, () => editor.chain().focus().toggleBold().run(), editor.isActive("bold"))}
      {tool("italic", "Miring", Italic, () => editor.chain().focus().toggleItalic().run(), editor.isActive("italic"))}
      {tool("underline", "Garis bawah", Underline, () => editor.chain().focus().toggleUnderline().run(), editor.isActive("underline"))}
      <span className="mx-1 h-5 border-l" />
      {[["left", "Rata kiri", AlignLeft], ["center", "Rata tengah", AlignCenter], ["right", "Rata kanan", AlignRight], ["justify", "Rata kanan kiri", AlignJustify]].map(([id, label, Icon]) => tool(`align-${id}`, label, Icon, () => editor.chain().focus().setTextAlign(id).run(), editor.isActive({ textAlign: id })))}
      {tool("bullet-list", "Daftar berpoin", List, () => editor.chain().focus().toggleBulletList().run(), editor.isActive("bulletList"))}
      {tool("ordered-list", "Daftar bernomor", ListOrdered, () => editor.chain().focus().toggleOrderedList().run(), editor.isActive("orderedList"))}
      {tool("insert-table", "Sisipkan tabel", Table2, () => editor.chain().focus().insertTable({ rows: 3, cols: 2, withHeaderRow: true }).run())}
    </div>
    {table && <div className="flex flex-wrap items-center gap-1 border-b p-1" role="toolbar" aria-label="Atur tabel" data-testid="script-table-toolbar">
      {tool("table-up", "Pindahkan tabel ke atas", ArrowUp, () => moveTable(editor, -1))}
      {tool("table-down", "Pindahkan tabel ke bawah", ArrowDown, () => moveTable(editor, 1))}
      {tool("row-add", "Tambah baris", Plus, () => editor.chain().focus().addRowAfter().run())}
      {tool("row-delete", "Hapus baris", Minus, () => editor.chain().focus().deleteRow().run())}
      <Button type="button" size="sm" variant="ghost" data-testid="script-column-add" onClick={() => editor.chain().focus().addColumnAfter().run()}>+ Kolom</Button>
      <Button type="button" size="sm" variant="ghost" data-testid="script-column-delete" onClick={() => editor.chain().focus().deleteColumn().run()}>− Kolom</Button>
      {tool("table-delete", "Hapus tabel", Trash2, () => editor.chain().focus().deleteTable().run())}
    </div>}
    <EditorContent editor={editor} />
  </div>;
});