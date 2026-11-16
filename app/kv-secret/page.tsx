import Link from "next/link";
import { KVMountChat } from "../components/KVMountChat";

export default function KVSecretOnboarding() {
  return (
    <main className="kv-mount-workspace">
      <header className="kv-mount-header"><h1>Create KV Secret</h1><Link href="/">← Back to patterns</Link></header>
      <KVMountChat mode="secret" />
    </main>
  );
}
