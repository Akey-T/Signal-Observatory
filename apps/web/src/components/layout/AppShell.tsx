import { Outlet } from "react-router-dom";

import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";
import { ScrollToTop } from "./ScrollToTop";

export function AppShell() {
  return (
    <div className="app-shell">
      <ScrollToTop />
      <SiteHeader />
      <main id="main-content">
        <Outlet />
      </main>
      <SiteFooter />
    </div>
  );
}
