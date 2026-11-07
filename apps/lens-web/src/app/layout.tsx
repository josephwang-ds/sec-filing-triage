import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Company Lens",
};

/**
 * The locale layout below renders `<html>`, because the `lang` attribute has to
 * be the reader's language on the very first server render. This root layout
 * exists only because the App Router requires one.
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
