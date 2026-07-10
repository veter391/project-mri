import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "project-mri — an MRI for your codebase",
  description:
    "Open-source, agent-native engine that x-rays a codebase — mining Git history and structure into explainable code-health scores: hotspots, complexity, single-owner risk, and the fingerprint of AI-generated code. Local-first. Built for the AI coding era.",
  metadataBase: new URL("https://project-mri.dev"),
  openGraph: {
    title: "project-mri — an MRI for your codebase",
    description:
      "Explainable, local-first codebase intelligence. Git history + structure → auditable health scores. Open source, MIT.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={jetbrainsMono.variable}>
      <body>{children}</body>
    </html>
  );
}
