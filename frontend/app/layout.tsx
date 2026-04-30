import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Voxr AI PR Reviewer – Multi-Agent Code Review & Documentation",
  description:
    "Ship better pull requests with AI-powered multi-agent code review, automated documentation generation, and persona-aware insights.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>{children}</body>
    </html>
  );
}
