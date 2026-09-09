import React, { useRef } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { rememberReturnTo, takeReturnTo } from "@/services/sessionBus";
import { ReferenceProvider } from "@/context/ReferenceContext";
import { OfflineProvider } from "@/context/OfflineContext";
import AppShell from "@/components/layout/AppShell";
import Login from "@/pages/Login";
import Home from "@/pages/Home";
import TasksPage from "@/pages/TasksPage";
import NotificationsPage from "@/pages/NotificationsPage";
import LeadsPage from "@/pages/LeadsPage";
import LeadProfilePage from "@/pages/LeadProfilePage";
import AppointmentsPage from "@/pages/AppointmentsPage";
import InboxPage from "@/pages/InboxPage";
import OmnichannelPage from "@/pages/OmnichannelPage";
import CampaignsPage from "@/pages/CampaignsPage";
import AttributionPage from "@/pages/AttributionPage";
import BiPage from "@/pages/BiPage";
import DealsPage from "@/pages/DealsPage";
import SitePlanPage from "@/pages/SitePlanPage";
import DocumentsPage from "@/pages/DocumentsPage";
import ProjectsPage from "@/pages/ProjectsPage";
import ProjectDetailPage from "@/pages/ProjectDetailPage";
import UnitDetailPage from "@/pages/UnitDetailPage";
import ConfigCenterPage from "@/pages/ConfigCenterPage";
import ConstructionPage from "@/pages/ConstructionPage";
import BuildHubPage from "@/pages/BuildHubPage";
import BuildCalendarPage from "@/pages/BuildCalendarPage";
import BuildCalibrationPage from "@/pages/BuildCalibrationPage";
import MaterialsPage from "@/pages/MaterialsPage";
import FinancePage from "@/pages/FinancePage";
import CustomersPage from "@/pages/CustomersPage";
import CustomerProfilePage from "@/pages/CustomerProfilePage";
import ComplaintsPage from "@/pages/ComplaintsPage";
import PermitsPage from "@/pages/PermitsPage";
import FieldPage from "@/pages/FieldPage";
import BoQPage from "@/pages/BoQPage";
import SubconPage from "@/pages/SubconPage";
import ProcurementPage from "@/pages/ProcurementPage";
import AccountingPage from "@/pages/AccountingPage";
import AccountingReportsPage from "@/pages/AccountingReportsPage";
import TaxPage from "@/pages/TaxPage";
import PettyCashPage from "@/pages/PettyCashPage";
import FixedAssetsPage from "@/pages/FixedAssetsPage";
import CorporateFinancingPage from "@/pages/CorporateFinancingPage";
import PartnersPage from "@/pages/PartnersPage";
import PartnerProfilePage from "@/pages/PartnerProfilePage";
import AdminUsers from "@/pages/AdminUsers";
import AdminPermissions from "@/pages/AdminPermissions";
import OrganizationsPage from "@/pages/OrganizationsPage";
import MasterDataPage from "@/pages/MasterDataPage";
import AuditLogsPage from "@/pages/AuditLogsPage";
import PortalApp from "@/pages/portal/PortalApp";
import PublicShowroom from "@/pages/PublicShowroom";

function Splash() {
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="animate-pulse text-muted-foreground">Memuat SIPRO…</div>
    </div>
  );
}

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Splash />;
  if (!user) {
    // Fase 54 — catat DI MANA pekerjaan ditinggalkan sebelum mengantar ke halaman masuk.
    // Ini satu-satunya tempat yang tahu halaman apa yang sedang dituju, dan tanpa catatan
    // ini "sesi habis" berarti kehilangan jejak: orang yang sedang membuka satu unit di
    // antara ratusan harus mencarinya lagi dari awal sesudah masuk kembali.
    rememberReturnTo(location.pathname + location.search);
    return <Navigate to="/login" replace />;
  }
  return children;
}

function RequireAdmin({ children }) {
  const { can } = useAuth();
  // Resource `permissions` sengaja KOSONG di matriks RBAC = hanya peran FULL_ACCESS
  // (owner/super_admin) yang lolos. Memakai izin efektif berarti area Admin ikut aturan
  // yang sama dengan backend `admin_router`, tanpa menyalin nama peran ke frontend.
  if (!can("permissions", "manage")) return <Navigate to="/" replace />;
  return children;
}

function LoginRoute() {
  const { user, loading } = useAuth();
  // Fase 54 — tujuan kembali dihitung SEKALI per pemasangan komponen dan disimpan di ref.
  //
  // `takeReturnTo()` sekali-pakai (ia menghapus catatannya), dan `React.StrictMode`
  // (lihat index.js) MEMANGGIL fungsi render dua kali. Tanpa penjaga ref di bawah ini,
  // pemanggilan pertama memakan "/customers" dan pemanggilan kedua mendapat null, sehingga
  // yang benar-benar dipakai adalah "/" — pengguna dijanjikan kembali ke tempat kerjanya,
  // lalu tetap didaratkan di Beranda.
  const tujuan = useRef(null);
  if (loading) return <Splash />;
  if (user) {
    if (tujuan.current === null) tujuan.current = takeReturnTo() || "/";
    return <Navigate to={tujuan.current} replace />;
  }
  return <Login />;
}

export default function App() {
  return (
    <AuthProvider>
      <ReferenceProvider>
      <OfflineProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route path="/portal/*" element={<PortalApp />} />
          {/* Fase 28b — halaman showroom PUBLIK: sengaja di luar RequireAuth (calon
              pembeli tidak punya akun) dan diakses lewat token acak per proyek. */}
          <Route path="/showroom/:token" element={<PublicShowroom />} />
          <Route element={<RequireAuth><AppShell /></RequireAuth>}>
            <Route path="/" element={<Home />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/leads" element={<LeadsPage />} />
            <Route path="/leads/:id" element={<LeadProfilePage />} />
            <Route path="/appointments" element={<AppointmentsPage />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/automation" element={<OmnichannelPage />} />
            {/* Fase 43 — dua menu yang sebelumnya "Segera Hadir" kini punya halaman nyata. */}
            <Route path="/campaigns" element={<CampaignsPage />} />
            <Route path="/attribution" element={<AttributionPage />} />
            <Route path="/bi" element={<BiPage />} />
            <Route path="/deals" element={<DealsPage />} />
            <Route path="/site-plan" element={<SitePlanPage />} />
            <Route path="/customers" element={<CustomersPage />} />
            <Route path="/customers/:id" element={<CustomerProfilePage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:id" element={<ProjectDetailPage />} />
            <Route path="/units/:id" element={<UnitDetailPage />} />
            <Route path="/config" element={<RequireAdmin><ConfigCenterPage /></RequireAdmin>} />
            {/* Fase 40c — hub Pembangunan (Papan Unit · Progres & Mutu · Kalender ·
                Lapangan · Kalibrasi). Rute lama di bawahnya SENGAJA tetap hidup supaya
                bookmark, pintasan notifikasi, dan tautan lama tidak rusak. */}
            <Route path="/build" element={<BuildHubPage />} />
            <Route path="/construction" element={<ConstructionPage />} />
            <Route path="/build-calendar" element={<BuildCalendarPage />} />
            <Route path="/build-calibration" element={<BuildCalibrationPage />} />
            <Route path="/materials" element={<MaterialsPage />} />
            <Route path="/permits" element={<PermitsPage />} />
            <Route path="/field" element={<FieldPage />} />
            <Route path="/boq" element={<BoQPage />} />
            <Route path="/subcon" element={<SubconPage />} />
            <Route path="/procurement" element={<ProcurementPage />} />
            <Route path="/accounting" element={<AccountingPage />} />
            <Route path="/accounting/reports" element={<AccountingReportsPage />} />
            <Route path="/tax" element={<TaxPage />} />
            <Route path="/finance" element={<FinancePage />} />
            <Route path="/petty-cash" element={<PettyCashPage />} />
            <Route path="/fixed-assets" element={<FixedAssetsPage />} />
            <Route path="/corporate-financing" element={<CorporateFinancingPage />} />
            {/* Fase 42 — SATU PINTU untuk urusan fee mitra. Rute lama ini SENGAJA tetap
                terdaftar (bookmark, notifikasi, dan tautan yang sudah terbit menyimpannya)
                tetapi tidak lagi punya halaman sendiri: dulu ada DUA pintu untuk satu
                urusan — `/marketing-fee` (Pengajuan Fee + Master Agen) dan `/partners`
                (Tagihan Fee + Master Mitra) — dengan master mitra kembar. Sekarang
                pemakai lama langsung mendarat di tab "Tagihan Fee" hub Mitra & Fee. */}
            <Route path="/marketing-fee"
              element={<Navigate to="/partners?hub=tagihan" replace />} />
            <Route path="/partners" element={<PartnersPage />} />
            <Route path="/partners/:id" element={<PartnerProfilePage />} />
            <Route path="/complaints" element={<ComplaintsPage />} />
            <Route path="/admin/users" element={<RequireAdmin><AdminUsers /></RequireAdmin>} />
            <Route path="/admin/permissions" element={<RequireAdmin><AdminPermissions /></RequireAdmin>} />
            <Route path="/admin/organizations" element={<RequireAdmin><OrganizationsPage /></RequireAdmin>} />
            <Route path="/admin/master-data" element={<RequireAdmin><MasterDataPage /></RequireAdmin>} />
            <Route path="/admin/audit" element={<RequireAdmin><AuditLogsPage /></RequireAdmin>} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors />
      </OfflineProvider>
      </ReferenceProvider>
    </AuthProvider>
  );
}
