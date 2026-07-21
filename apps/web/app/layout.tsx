import type { Metadata, Viewport } from "next";
import { Space_Grotesk, Outfit, JetBrains_Mono } from "next/font/google";
import { Nav } from "@/components/nav";
import { Footer } from "@/components/footer";
import "./globals.css";

// Self-hosted at build time by next/font — no runtime CDN request, CSP-clean.
// JetBrains Mono = data typeface; Space Grotesk = UI/headings; Outfit = body.
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-space-grotesk",
  display: "swap",
});
const outfit = Outfit({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-outfit",
  display: "swap",
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

const SITE_URL = "https://project-mri.dev";
const DESCRIPTION =
  "MRI decomposes AI-authored vs human-authored risk from real session logs, tracks decisions to measured outcomes, and stays MIT-licensed and self-hostable forever.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "MRI — Explainable Risk & AI Provenance for Your Codebase",
    template: "%s — MRI",
  },
  description: DESCRIPTION,
  applicationName: "MRI",
  authors: [{ name: "project-mri contributors" }],
  creator: "project-mri contributors",
  keywords: [
    "comprehension debt",
    "AI code attribution",
    "AI code provenance",
    "codebase intelligence",
    "code risk analysis",
    "git history analysis",
    "technical debt",
    "code hotspots",
    "bus factor",
    "local-first developer tools",
    "self-hosted code analysis",
    "MCP server",
    "SARIF CI gate",
    "open source",
  ],
  robots: { index: true, follow: true },
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: "MRI",
    url: SITE_URL,
    title: "MRI — Explainable Risk & AI Provenance for Your Codebase",
    description: DESCRIPTION,
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "MRI — reads what's actually in your codebase, and who actually wrote it.",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "MRI — Explainable Risk & AI Provenance for Your Codebase",
    description:
      "Explainable risk. Real provenance. Zero telemetry. Local-first, MIT-forever codebase intelligence.",
    images: ["/og.png"],
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#06080f" },
    { media: "(prefers-color-scheme: light)", color: "#ece4d1" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${outfit.variable} ${jetbrainsMono.variable}`}
    >
      <body>
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <Nav />
        <main id="main-content">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
