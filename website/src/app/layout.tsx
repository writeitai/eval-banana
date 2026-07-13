import type { Metadata } from "next";
import { Hanken_Grotesk } from "next/font/google";
import "./globals.css";
import { SiteHeader } from "@/components/site/SiteHeader";

// Open-font stand-in for writeit.ai's domain-locked proxima-nova. Self-hosted
// by next/font so the site stays a self-contained module.
const hanken = Hanken_Grotesk({
  subsets: ["latin"],
  variable: "--font-hanken",
});

const siteUrl = "https://eval-banana.writeit.ai";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "eval-banana — Documentation",
    template: "%s — eval-banana",
  },
  description:
    "Aspect-based evaluation framework — score anything with simple YAML checks. Documentation for eval-banana.",
  // Only site-level Open Graph defaults live here. With no `openGraph.title`
  // or `openGraph.description` set, Next falls those back to each page's own
  // `title`/`description`, so every route gets a specific `og:title`. We also
  // omit `openGraph.url` so pages no longer stamp the root URL onto every route.
  openGraph: {
    siteName: "eval-banana",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${hanken.variable} font-sans antialiased`}>
        <SiteHeader />
        <main>{children}</main>
      </body>
    </html>
  );
}
