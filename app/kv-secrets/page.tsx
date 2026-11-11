import Link from "next/link";
import { KVSecretList } from "../components/KVSecretList";

export default function ListKVSecrets() {
  return <main className="kv-list-workspace"><header className="kv-mount-header"><h1>List KV Secrets</h1><Link href="/">← Back to patterns</Link></header><KVSecretList /></main>;
}
