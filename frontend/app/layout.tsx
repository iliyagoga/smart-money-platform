import type { Metadata } from "next";
import type { ReactNode } from "react";
import { ThemeRegistry } from "./ThemeRegistry";
import "./styles.css";

export const metadata: Metadata = {
  title: "Smart Money",
  description: "Trading intelligence platform",
};

export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="ru"><body><ThemeRegistry>{children}</ThemeRegistry></body></html>;
}
