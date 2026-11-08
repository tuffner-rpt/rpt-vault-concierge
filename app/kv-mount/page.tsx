import Link from "next/link";

export default function KVMountOnboarding() {
  return (
    <main className="kv-mount-workspace">
      <header className="kv-mount-header">
        <h1>Create KV Mount</h1>
        <Link href="/">← Back to patterns</Link>
      </header>
      <iframe className="kv-mount-chat" src="/vault-onboarding/chat?workflow=kv-mount" title="Ask RPT — KV mount onboarding only" referrerPolicy="no-referrer" />
    </main>
  );
}
