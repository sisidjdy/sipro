"""Model masukan Fase 60 — konfigurasi tampilan dokumen.

Validasi di sini menjaga tiga hal yang paling mudah rusak: warna yang bukan warna, margin
yang membuat isi keluar kertas, dan baris biaya manual tanpa label (yang akan tercetak
sebagai baris kosong di dokumen resmi).
"""
import re

from pydantic import BaseModel, Field, field_validator

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandIn(BaseModel):
    company_name: str | None = None
    tagline: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    npwp: str | None = None
    logo_file_id: str | None = None
    header_image_file_id: str | None = None
    footer_image_file_id: str | None = None
    header_mode: str | None = None      # system | image | none
    footer_mode: str | None = None      # system | image | none
    accent_color: str | None = None
    text_color: str | None = None
    footer_text: str | None = None
    show_page_numbers: bool | None = None
    paper: str | None = None            # A4 | LETTER | LEGAL
    margin_top_mm: float | None = Field(default=None, ge=8, le=60)
    margin_bottom_mm: float | None = Field(default=None, ge=8, le=60)
    margin_left_mm: float | None = Field(default=None, ge=8, le=50)
    margin_right_mm: float | None = Field(default=None, ge=8, le=50)
    watermark_text: str | None = None
    watermark_file_id: str | None = None
    watermark_opacity: int | None = Field(default=None, ge=0, le=60)

    @field_validator("accent_color", "text_color")
    @classmethod
    def _v_color(cls, v):
        if v and not HEX.match(v):
            raise ValueError("Warna harus berupa kode heksadesimal, mis. #0f766e.")
        return v

    @field_validator("header_mode", "footer_mode")
    @classmethod
    def _v_mode(cls, v):
        if v and v not in ("system", "image", "none"):
            raise ValueError("Mode kop/footer hanya: system, image, none.")
        return v

    @field_validator("paper")
    @classmethod
    def _v_paper(cls, v):
        if v and v not in ("A4", "LETTER", "LEGAL"):
            raise ValueError("Ukuran kertas hanya: A4, LETTER, LEGAL.")
        return v


class SectionIn(BaseModel):
    key: str
    label: str | None = None
    visible: bool = True
    order: int = 0


class MoneyRowIn(BaseModel):
    code: str
    label: str
    visible: bool = True
    order: int = 0
    hide_if_zero: bool = True
    manual: bool = False
    amount: int | None = None

    @field_validator("label")
    @classmethod
    def _v_label(cls, v):
        if not (v or "").strip():
            raise ValueError("Label baris biaya tidak boleh kosong — ia tercetak di dokumen.")
        return v.strip()


class SignatureIn(BaseModel):
    title: str
    name: str | None = None
    position: str | None = None
    show_stamp: bool = False
    stamp_file_id: str | None = None
    sign_file_id: str | None = None
    auto_from_issuer: bool = False

    @field_validator("title")
    @classmethod
    def _v_title(cls, v):
        if not (v or "").strip():
            raise ValueError("Judul kolom tanda tangan wajib diisi.")
        return v.strip()


class TableIn(BaseModel):
    """Gaya tabel dokumen (Fase 66) — garis, kepala tabel, baris belang, ukuran huruf."""
    grid: str | None = None            # full | horizontal | none (transparan)
    show_header: bool | None = None
    header_fill: bool | None = None
    zebra: bool | None = None
    total_highlight: bool | None = None
    font_size: float | None = Field(default=None, ge=6, le=12)
    grid_color: str | None = None
    width_pct: float | None = Field(default=None, ge=40, le=100)
    alignment: str | None = None

    @field_validator("alignment")
    @classmethod
    def _v_alignment(cls, v):
        if v is not None and v not in ("left", "center", "right"):
            raise ValueError("Posisi tabel hanya: left, center, right.")
        return v

    @field_validator("grid")
    @classmethod
    def _v_grid(cls, v):
        if v and v not in ("full", "horizontal", "none"):
            raise ValueError("Gaya garis tabel hanya: full, horizontal, none.")
        return v

    @field_validator("grid_color")
    @classmethod
    def _v_grid_color(cls, v):
        if v and not HEX.match(v):
            raise ValueError("Warna garis tabel harus heksadesimal, mis. #e2e8f0.")
        return v


class DocScriptSave(BaseModel):
    """Naskah dokumen per jenis (Fase 66) — isi yang benar-benar tercetak."""
    content: str = Field(min_length=0, max_length=20000)
    name: str | None = None

class OptionsIn(BaseModel):
    show_materai: bool | None = None
    materai_note: str | None = None
    show_place_date: bool | None = None
    place: str | None = None
    show_doc_number: bool | None = None
    show_title: bool | None = None
    hide_zero_rows: bool | None = None
    closing_note: str | None = None
    show_generated_note: bool | None = None
    doc_date: str | None = None


class DocLayoutSave(BaseModel):
    brand: BrandIn | None = None
    table: TableIn | None = None
    sections: list[SectionIn] | None = None
    money_rows: list[MoneyRowIn] | None = None
    signatures: list[SignatureIn] | None = Field(default=None, max_length=4)
    options: OptionsIn | None = None


class DocPreviewIn(DocLayoutSave):
    """Pratinjau: rancangan tampilan + NASKAH yang belum disimpan.

    Naskah ikut dikirim karena pratinjau yang tidak menampilkan isi dokumen membuat orang
    menyetel kop surat tanpa tahu naskahnya akan tercetak seperti apa — itulah keluhan yang
    ditutup Fase 66.
    """
    script: str | None = None
