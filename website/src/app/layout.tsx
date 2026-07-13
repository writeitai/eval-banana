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
  openGraph: {
    title: "eval-banana — Documentation",
    description:
      "Aspect-based evaluation framework — score anything with simple YAML checks.",
    url: siteUrl,
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
