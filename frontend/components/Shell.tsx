import { AdminShell } from "./admin/AdminShell";

export function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return <AdminShell title={title}>{children}</AdminShell>;
}
