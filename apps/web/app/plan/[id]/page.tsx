"use client";
import { useParams } from "next/navigation";
import PlanEditor from "../../../components/plan/PlanEditor";

export default function PlanPage() {
  const { id } = useParams<{ id: string }>();
  return <PlanEditor key={id} id={id} />;
}
