import type { Metadata } from "next";
import "./globals.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL
  || (process.env.VERCEL_PROJECT_PRODUCTION_URL
    ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
    : "http://localhost:3000");

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "RPT Vault Developer Concierge",
  description: "Provision policy-aware secrets through a secure self-service developer portal.",
  openGraph: {
    title: "RPT Vault Developer Concierge",
    description: "Secrets, provisioned safely.",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "RPT Vault Developer Concierge" }],
  },
  twitter: { card: "summary_large_image", title: "RPT Vault Developer Concierge", description: "Secrets, provisioned safely.", images: ["/og.png"] },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
