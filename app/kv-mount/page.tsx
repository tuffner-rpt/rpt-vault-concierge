import Link from "next/link";
import { KVMountChat } from "../components/KVMountChat";

export default function KVMountOnboarding() {
  return (
    <main className="kv-mount-workspace">
      <header className="kv-mount-header">
        <h1>Create KV Mount</h1>
        <Link href="/">← Back to patterns</Link>
      </header>
      <KVMountChat />
    </main>
  );
}
