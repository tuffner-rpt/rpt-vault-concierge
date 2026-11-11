import { kvSecretIntake } from "@/lib/kv-secret-intake";

export async function POST(request: Request) {
  return kvSecretIntake(request, "update_secret");
}
