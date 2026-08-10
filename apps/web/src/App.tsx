import { Route, Routes } from "react-router-dom";

import { AppShell } from "./components/layout/AppShell";
import { PageNotFound } from "./components/layout/PageState";
import { RegistryProvider } from "./context/RegistryContext";
import { OverviewPage } from "./pages/OverviewPage";
import { TopicDetailPage } from "./pages/TopicDetailPage";
import { TopicsPage } from "./pages/TopicsPage";

export function App() {
  return (
    <RegistryProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="topics" element={<TopicsPage />} />
          <Route path="topics/:slug" element={<TopicDetailPage />} />
          <Route path="*" element={<PageNotFound />} />
        </Route>
      </Routes>
    </RegistryProvider>
  );
}
