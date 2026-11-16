import { redirect } from "next/navigation";
import { bridgeOrigin } from "@/lib/vault-bridge";

export const dynamic = "force-dynamic";

export default function FulfilledRequests() {
  redirect(`${bridgeOrigin()}/fulfilled`);
}
