import { AllowlistManager } from "@/components/AllowlistManager";

export default function AdminPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 w-full space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Allowlist</h1>
      <AllowlistManager />
    </div>
  );
}
