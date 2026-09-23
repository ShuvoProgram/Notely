import type { Metadata, Viewport } from "next";
import { Geist_Mono } from "next/font/google";
import Script from "next/script";

import { AppProviders } from "@/components/providers/app-providers";
import { PREPAINT_SCRIPT } from "@/lib/appearance/apply";

import "./globals.css";

const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Notely AI", template: "%s · Notely AI" },
  description: "Capture thoughts. Connect your work. Let AI move things forward.",
  applicationName: "Notely AI",
};

export const viewport: Viewport = {
  themeColor: "#1c1d22",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${geistMono.variable} dark h-full`}
      suppressHydrationWarning
    >
      <head>
        {/* Satoshi (Fontshare): the app's only text face. Preconnect so the font files start early. */}
        <link rel="preconnect" href="https://api.fontshare.com" />
        <link rel="preconnect" href="https://cdn.fontshare.com" crossOrigin="anonymous" />
        <link rel="stylesheet" href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,900&display=swap" />
      </head>
      <body className="flex min-h-full flex-col">
        {/* Applies the saved background and glass strength before first paint (no flash on refresh). */}
        <Script id="notely-appearance" strategy="beforeInteractive">
          {PREPAINT_SCRIPT}
        </Script>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
