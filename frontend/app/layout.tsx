import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kodoku",
  description: "Decision Graph AI — explore, evaluate, and synthesize ideas",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
