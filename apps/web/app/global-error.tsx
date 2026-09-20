"use client";

/** Last-resort boundary for errors in the root layout itself; must render its own <html>. */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", padding: "3rem 1rem", textAlign: "center" }}>
        <h1 style={{ fontSize: "1.125rem", fontWeight: 600 }}>Something went wrong</h1>
        <p style={{ color: "#666", maxWidth: 420, margin: "0.75rem auto" }}>
          Notely couldn&apos;t load this page{error.digest ? ` (reference ${error.digest})` : ""}. Please try again.
        </p>
        <button type="button" onClick={reset} style={{ padding: "0.5rem 1rem", borderRadius: 8, border: "1px solid #ccc" }}>
          Try again
        </button>
      </body>
    </html>
  );
}
