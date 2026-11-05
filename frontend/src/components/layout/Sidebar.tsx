import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { FileText, MessageSquarePlus, Moon, Search, Settings as SettingsIcon, Sun, Trash2 } from "lucide-react";
import { useChatStore } from "../../store/useChatStore";
import { useThemeStore } from "../../store/useThemeStore";
import * as api from "../../lib/api";
import type { Conversation } from "../../lib/types";

export default function Sidebar({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { conversations, activeConversationId, loadConversations, openConversation, newConversation, removeConversation } =
    useChatStore();
  const { theme, toggle } = useThemeStore();
  const navigate = useNavigate();
  const location = useLocation();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Conversation[] | null>(null);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    if (!query.trim()) {
      setResults(null);
      return;
    }
    const handle = setTimeout(() => {
      api.searchConversations(query).then(setResults);
    }, 200);
    return () => clearTimeout(handle);
  }, [query]);

  const list = results ?? conversations;

  const handleNewChat = () => {
    newConversation();
    navigate("/");
  };

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-white font-semibold">R</div>
        <div className="flex-1">
          <p className="text-sm font-semibold text-ink leading-tight">My Documents</p>
          <p className="text-xs text-ink-muted leading-tight">Personal RAG chatbot</p>
        </div>
      </div>

      <div className="px-3">
        <button
          onClick={handleNewChat}
          className="flex w-full items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-surface-muted cursor-pointer"
        >
          <MessageSquarePlus size={16} />
          New chat
          <kbd className="ml-auto rounded border border-border px-1.5 py-0.5 text-[10px] text-ink-muted">Ctrl N</kbd>
        </button>
      </div>

      <div className="px-3 pt-2">
        <Link
          to="/library"
          className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium cursor-pointer ${
            location.pathname === "/library" ? "bg-brand-soft text-brand" : "text-ink hover:bg-surface-muted"
          }`}
        >
          <FileText size={16} />
          Document library
        </Link>
      </div>

      <div className="px-3 pt-3">
        <div className="relative">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-2.5 text-ink-muted" />
          <input
            id="conversation-search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats..."
            className="w-full rounded-lg border border-border bg-canvas py-1.5 pl-8 pr-2 text-sm text-ink placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-brand/40"
          />
        </div>
      </div>

      <div className="mt-2 flex-1 overflow-y-auto px-2 py-2">
        {list.length === 0 && <p className="px-2 py-4 text-center text-xs text-ink-muted">No conversations yet.</p>}
        <ul className="space-y-0.5">
          {list.map((c) => (
            <li key={c.id} className="group relative">
              <button
                onClick={() => {
                  openConversation(c.id);
                  navigate("/");
                }}
                className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm cursor-pointer ${
                  activeConversationId === c.id && location.pathname === "/"
                    ? "bg-brand-soft text-brand"
                    : "text-ink hover:bg-surface-muted"
                }`}
                title={c.title}
              >
                {c.title}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm(`Delete "${c.title}"?`)) removeConversation(c.id);
                }}
                className="absolute right-1.5 top-1.5 hidden rounded-md p-1 text-ink-muted hover:bg-surface hover:text-red-600 group-hover:block cursor-pointer"
                title="Delete conversation"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex items-center justify-between border-t border-border px-3 py-3">
        <button
          onClick={toggle}
          className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-ink-muted hover:bg-surface-muted hover:text-ink cursor-pointer"
          title="Toggle dark mode"
        >
          {theme === "dark" ? <Moon size={16} /> : <Sun size={16} />}
          {theme === "dark" ? "Dark" : "Light"}
        </button>
        <button
          onClick={onOpenSettings}
          className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-ink-muted hover:bg-surface-muted hover:text-ink cursor-pointer"
          title="Settings"
        >
          <SettingsIcon size={16} />
          Settings
        </button>
      </div>
    </aside>
  );
}
