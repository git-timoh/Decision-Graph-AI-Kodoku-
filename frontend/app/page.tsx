import { SessionSidebar } from "@/app/_components/SessionSidebar";
import { NewSessionDialog } from "@/app/_components/NewSessionDialog";

export default function HomePage() {
  return (
    <div className="flex h-screen">
      <SessionSidebar />
      <main className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Sessions</h1>
            <p className="text-xs text-muted-foreground">
              Pick a session from the sidebar or start a new one.
            </p>
          </div>
          <NewSessionDialog />
        </header>
        <section className="flex flex-1 items-center justify-center">
          <div className="max-w-md text-center text-sm text-muted-foreground">
            Each session expands a goal into branches, scores them, and
            synthesises a recommendation. Click &quot;New session&quot; to seed the root
            node.
          </div>
        </section>
      </main>
    </div>
  );
}
