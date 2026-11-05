import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Sidebar from "./components/layout/Sidebar";
import ChatPage from "./pages/ChatPage";
import LibraryPage from "./pages/LibraryPage";
import DocumentViewerModal from "./components/viewer/DocumentViewerModal";
import SettingsModal from "./components/settings/SettingsModal";

export default function App() {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <BrowserRouter>
      <div className="flex h-screen w-screen overflow-hidden bg-canvas text-ink">
        <Sidebar onOpenSettings={() => setSettingsOpen(true)} />
        <main className="flex flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/library" element={<LibraryPage />} />
          </Routes>
        </main>
      </div>
      <DocumentViewerModal />
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </BrowserRouter>
  );
}
