import { EquipmentView } from "./view";
import { AuthGuard } from "@/components/AuthGuard";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AuthGuard><EquipmentView id={id} /></AuthGuard>;
}
