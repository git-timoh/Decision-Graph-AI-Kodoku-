import { SessionSidebar } from "@/app/_components/SessionSidebar";
import { SettingsForm } from "@/app/settings/SettingsForm";

export default function SettingsPage() {
  return (
    <div className="flex h-screen">
      <SessionSidebar />
      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="border-b border-border px-6 py-4">
          <h1 className="text-lg font-semibold tracking-tight">Settings</h1>
          <p className="text-xs text-muted-foreground">
            Bring your own provider keys and pick a model per role.
          </p>
        </header>
        <section className="flex-1 overflow-y-auto px-6 py-6">
          <SettingsForm />
        </section>
      </main>
    </div>
  );
}
