import { create } from "zustand";
import * as api from "../lib/api";
import type { ChatMessage, Conversation, FilterSpec } from "../lib/types";

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  streamError: string | null;
  filters: FilterSpec;
  showChunks: boolean;
  allowGeneralKnowledge: boolean;
  useSubquestions: boolean;
  stopFn: (() => void) | null;

  loadConversations: () => Promise<void>;
  openConversation: (id: string) => Promise<void>;
  newConversation: () => void;
  removeConversation: (id: string) => Promise<void>;
  sendMessage: (text: string) => void;
  stopStreaming: () => void;
  setFilters: (f: FilterSpec) => void;
  setShowChunks: (v: boolean) => void;
  setAllowGeneralKnowledge: (v: boolean) => void;
  setUseSubquestions: (v: boolean) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messages: [],
  isStreaming: false,
  streamError: null,
  filters: {},
  showChunks: false,
  allowGeneralKnowledge: false,
  useSubquestions: false,
  stopFn: null,

  loadConversations: async () => {
    const conversations = await api.listConversations();
    set({ conversations });
  },

  openConversation: async (id: string) => {
    const conv = await api.getConversation(id);
    set({ activeConversationId: id, messages: conv.messages ?? [], streamError: null });
  },

  newConversation: () => {
    set({ activeConversationId: null, messages: [], streamError: null });
  },

  removeConversation: async (id: string) => {
    await api.deleteConversation(id);
    const { activeConversationId } = get();
    set((s) => ({ conversations: s.conversations.filter((c) => c.id !== id) }));
    if (activeConversationId === id) {
      set({ activeConversationId: null, messages: [] });
    }
  },

  setFilters: (f) => set({ filters: f }),
  setShowChunks: (v) => set({ showChunks: v }),
  setAllowGeneralKnowledge: (v) => set({ allowGeneralKnowledge: v }),
  setUseSubquestions: (v) => set({ useSubquestions: v }),

  stopStreaming: () => {
    const { stopFn } = get();
    stopFn?.();
    set({ isStreaming: false, stopFn: null });
  },

  sendMessage: (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const { activeConversationId, filters, showChunks, allowGeneralKnowledge, useSubquestions } = get();

    const userMsg: ChatMessage = { id: `local-${Date.now()}`, role: "user", content: trimmed };
    const assistantMsg: ChatMessage = { id: `local-${Date.now()}-a`, role: "assistant", content: "", streaming: true };
    set((s) => ({ messages: [...s.messages, userMsg, assistantMsg], isStreaming: true, streamError: null }));

    const stop = api.streamChat(
      {
        conversation_id: activeConversationId,
        message: trimmed,
        filters,
        show_chunks: showChunks,
        allow_general_knowledge: allowGeneralKnowledge,
        use_subquestions: useSubquestions,
      },
      {
        onStart: (conversationId) => {
          if (!get().activeConversationId) {
            set({ activeConversationId: conversationId });
          }
        },
        onMeta: (meta) => {
          set((s) => ({
            messages: patchLastAssistant(s.messages, (m) => ({
              ...m,
              retrieved: meta.retrieved,
              lowConfidence: meta.low_confidence,
            })),
          }));
        },
        onDelta: (text) => {
          set((s) => ({
            messages: patchLastAssistant(s.messages, (m) => ({ ...m, content: m.content + text })),
          }));
        },
        onDone: (payload) => {
          set((s) => ({
            messages: patchLastAssistant(s.messages, (m) => ({
              ...m,
              citations: payload.citations,
              not_found: payload.not_found,
              used_general_knowledge: payload.used_general_knowledge,
              streaming: false,
            })),
            isStreaming: false,
            stopFn: null,
          }));
          get().loadConversations();
        },
        onError: (message) => {
          set((s) => ({
            messages: patchLastAssistant(s.messages, (m) => ({
              ...m,
              content: m.content || `Something went wrong: ${message}`,
              streaming: false,
            })),
            isStreaming: false,
            stopFn: null,
            streamError: message,
          }));
        },
      },
    );
    set({ stopFn: stop });
  },
}));

function patchLastAssistant(messages: ChatMessage[], patch: (m: ChatMessage) => ChatMessage): ChatMessage[] {
  const idx = messages.length - 1;
  if (idx < 0 || messages[idx].role !== "assistant") return messages;
  const next = messages.slice();
  next[idx] = patch(next[idx]);
  return next;
}
