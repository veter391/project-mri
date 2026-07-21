"use client";

// The App Router's top-level error boundary (the equivalent of the old
// pages/_error). Its presence keeps `output: export` from falling back to the
// Pages Router _error/_document during static generation of the 500 page — the
// cause of the "<Html> should not be imported outside of pages/_document" build
// failure. It renders its own <html>/<body> because it replaces the root layout.
export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="en">
      <body
        style={{
          background: "#06080c",
          color: "#f5f2ea",
          fontFamily: "ui-monospace, monospace",
          padding: "3rem 1.5rem",
        }}
      >
        <p style={{ color: "#f4a847", letterSpacing: "0.1em", fontSize: 12 }}>
          // project-mri
        </p>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: "0.5rem 0 1rem" }}>
          Something went wrong
        </h1>
        <button
          onClick={() => reset()}
          style={{
            minHeight: 44,
            padding: "0.5rem 1rem",
            border: "1px solid rgba(244,168,71,0.5)",
            background: "rgba(244,168,71,0.1)",
            color: "#f4a847",
            borderRadius: 2,
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
