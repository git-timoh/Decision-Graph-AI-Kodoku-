import { SessionPageClient } from "@/app/s/[sessionId]/SessionPageClient";

// Static export needs at least one param; the page is client-rendered and
// param-independent, so one shell ("_") is served by the backend for every id.
export const dynamicParams = false;

export function generateStaticParams() {
  return [{ sessionId: "_" }];
}

export default function SessionPage() {
  return <SessionPageClient />;
}
