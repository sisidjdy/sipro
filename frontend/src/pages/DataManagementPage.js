import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { DatabaseBackup } from "lucide-react";

import api from "@/services/apiClient";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DATAMGMT } from "@/constants/testIds";
import MigrationPanel from "@/components/datamgmt/MigrationPanel";
import BackupPanel from "@/components/datamgmt/BackupPanel";
import RestoreUploadPanel from "@/components/datamgmt/RestoreUploadPanel";
import PurgePanel from "@/components/datamgmt/PurgePanel";

/** Admin → Manajemen Data: migrasi master via Excel, backup & restore (admin/owner). */
export default function DataManagementPage() {
  const [data, setData] = useState({ entities: [], counts: [], snapshots: [] });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await api.get("/data-mgmt/overview");
      setData(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memuat ringkasan data.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const totalMaster = data.counts.reduce((s, c) => s + c.count, 0);

  return (
    <div data-testid={DATAMGMT.page} className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow flex items-center gap-1.5"><DatabaseBackup className="h-3.5 w-3.5" /> Admin</p>
          <h1 className="page-title">Manajemen Data</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Bawa data nyata bisnis masuk ke sistem lewat template Excel, amankan seluruh data
            dengan backup/restore, atau bersihkan data operasional sebelum produksi.
          </p>
        </div>
        <div className="flex gap-6 text-right">
          <Stat l="Master data" v={loading ? "…" : totalMaster} />
          <Stat l="Sheet template" v={data.entities.length} />
          <Stat l="Snapshot" v={data.snapshots.length} />
        </div>
      </div>

      <Tabs defaultValue="migration">
        <TabsList>
          <TabsTrigger data-testid={DATAMGMT.tabMigration} value="migration">Migrasi Excel</TabsTrigger>
          <TabsTrigger data-testid={DATAMGMT.tabBackup} value="backup">Backup & Snapshot</TabsTrigger>
          <TabsTrigger data-testid={DATAMGMT.tabRestore} value="restore">Restore dari Berkas</TabsTrigger>
          <TabsTrigger data-testid={DATAMGMT.tabPurge} value="purge" className="text-destructive data-[state=active]:text-destructive">Hapus Massal</TabsTrigger>
        </TabsList>
        <TabsContent value="migration" className="mt-4">
          <MigrationPanel entities={data.entities} counts={data.counts} onImported={load} />
        </TabsContent>
        <TabsContent value="backup" className="mt-4">
          <BackupPanel snapshots={data.snapshots} onChanged={load} />
        </TabsContent>
        <TabsContent value="restore" className="mt-4">
          <RestoreUploadPanel onChanged={load} />
        </TabsContent>
        <TabsContent value="purge" className="mt-4">
          <PurgePanel onChanged={load} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Stat({ l, v }) {
  return <div><p className="text-[11px] uppercase text-muted-foreground">{l}</p><p className="text-xl font-semibold tabular-nums">{v}</p></div>;
}
