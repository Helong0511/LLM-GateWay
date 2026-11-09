import { AdminArea } from "@/components/admin-area";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminArea>{children}</AdminArea>;
}
