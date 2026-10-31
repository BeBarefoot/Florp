import { notFound } from "next/navigation";
import Dataset from "../../../components/admin/DatasetPage";

// Internal training/annotation tool; not part of the product flow.
export default function AdminDataset() {
  if (process.env.NEXT_PUBLIC_FLORP_ADMIN !== "1") notFound();
  return <Dataset />;
}
