import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "./_components";

export const metadata: Metadata = {
  title: "ContentPilot",
  description: "Resource acquisition and workflow operations console.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <main className="shell">
          <Sidebar />
          <section className="main">{children}</section>
        </main>
      </body>
    </html>
  );
}
