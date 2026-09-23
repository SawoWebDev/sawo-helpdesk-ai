import type { Metadata } from "next";
import { Montserrat } from "next/font/google";
import "./globals.css";

const montserrat = Montserrat({
  subsets: ["latin"],
  // 300/800 added alongside the existing weights so the admin CMS chrome
  // (frontend/app/admin/**) can use the reference design system's full
  // weight range (300;400;500;600;700;800) without a synthetic/fallback
  // weight — see D:\NEW_SITES\REACT_SITE\SAWO_CMS_DESIGN\01_DESIGN_TOKENS\TYPOGRAPHY.md.
  weight: ["300", "400", "500", "600", "700", "800"],
  variable: "--font-montserrat",
});

export const metadata: Metadata = {
  title: "SAWO Helpdesk Assistant",
  description: "AI-powered helpdesk chat",
};

// Runs before first paint so the chosen theme never flashes.
// Falls back to the OS preference when the user hasn't picked one yet.
const themeInitScript = `
(function () {
  try {
    var stored = localStorage.getItem("sawo-theme");
    var theme =
      stored === "light" || stored === "dark"
        ? stored
        : window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light";
    if (theme === "dark") document.documentElement.classList.add("dark");
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={montserrat.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
