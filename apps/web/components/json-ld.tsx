import { SITE } from "@/lib/site";

// Structured data must describe what's genuinely on the page (SEO.md §3) — no
// schema added purely to game a SERP feature. Rendered as application/ld+json,
// which is data, not executable script.
export function HomeJsonLd() {
  const data = [
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      name: "MRI",
      alternateName: "project-mri",
      applicationCategory: "DeveloperApplication",
      operatingSystem: "macOS, Linux, Windows (WSL)",
      description: SITE.description,
      softwareVersion: SITE.version,
      url: SITE.url,
      license: "https://opensource.org/licenses/MIT",
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "USD",
      },
      isAccessibleForFree: true,
    },
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: "project-mri",
      url: SITE.url,
      sameAs: [SITE.github],
    },
  ];
  return (
    <script
      type="application/ld+json"
      // Escape `<` so a future field containing "</script>" can't break out of
      // the tag (current values are trusted constants; this is a guard).
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{
        __html: JSON.stringify(data).replace(/</g, "\\u003c"),
      }}
    />
  );
}
