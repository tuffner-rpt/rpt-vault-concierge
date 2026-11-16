import Link from "next/link";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function AdminReviews() {
  const value = process.env.WXO_BRIDGE_URL;
  let destination: string | null = null;
  if (value) {
    try {
      const url = new URL(value);
      if (url.protocol === "https:" && !url.username && !url.password && url.pathname === "/" && !url.search && !url.hash) destination = `${url.origin}/admin`;
    } catch { /* Show setup state for invalid configuration. */ }
  }
  if (destination) redirect(destination);
  return <main className="onboarding-workspace"><h1>Review &amp; approve</h1><p>The secure administrator review service needs to be configured.</p><Link href="/">Return to catalog</Link></main>;
}
