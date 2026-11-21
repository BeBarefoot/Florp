import Link from "next/link";
import { Box } from "lucide-react";
import "./phone.css";

export default function PhoneLayout({children}:{children:React.ReactNode}){
  return <div className="tour-shell"><div className="tour-mast">
    <Link href="/phone" aria-label="Florp walkthrough library"><Box size={26}/> Florp</Link>
    <span>Walkthrough studio</span>
  </div>{children}</div>;
}
