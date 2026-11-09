import { AuthGate } from "@/components/auth-gate";

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return <AuthGate>{children}</AuthGate>;
}
