"use client";
import { useEffect } from "react";

export default function MobileApp() {
  useEffect(() => {
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(error => console.warn("Florp offline launch unavailable", error));
    }
  }, []);
  return null;
}
