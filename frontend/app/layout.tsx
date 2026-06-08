import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "EV Charger Simulator",
  description: "OCPP 1.6J Charge Point Simulator",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
