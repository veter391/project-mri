import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/nav";
import { ScanField } from "@/components/scan-field";
import { SiteFooter } from "@/components/site-footer";

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

// Minimal, accurate structured data. No ratings/prices — the tool is free, MIT-licensed.
const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "project-mri",
  applicationCategory: "DeveloperApplication",
  operatingSystem: "Cross-platform",
  description:
    "Open-source, agent-native engine that mines Git history and structure into explainable code-health scores. Local-first developer tool.",
  license: "https://opensource.org/licenses/MIT",
  isAccessibleForFree: true,
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
  },
  url: "https://github.com/veter391/project-mri",
} as const;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={jetbrainsMono.variable}>
      <body>
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        <ScanField />
        <Nav />
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
