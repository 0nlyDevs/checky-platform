"use client";

import { useParams } from "next/navigation";
import { ScannerView } from "./scanner-view";

/** The scanner inside the desk: a page photo goes to this newsroom's Vérifier. */
export function DeskScanner() {
  const { ws } = useParams<{ ws: string }>();
  return <ScannerView ws={ws} />;
}
