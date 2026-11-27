import Link from "next/link";

export default function DesktopBrand() {
  return <Link className="desktop-brand" href="/" aria-label="Florp homes">
    <img src="/florp-180.png" width="34" height="34" alt=""/>
    <span>Florp</span>
  </Link>;
}
