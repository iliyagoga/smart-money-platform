import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AuthProvider } from "../components/auth/AuthProvider";
import { ThemeRegistry } from "./ThemeRegistry";
import "./styles.css";

export const metadata: Metadata = {
  title: "Elliott Wave",
  description: "Trading intelligence platform",
};

export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="ru"><body><ThemeRegistry><AuthProvider>{children}</AuthProvider></ThemeRegistry></body></html>;
}
