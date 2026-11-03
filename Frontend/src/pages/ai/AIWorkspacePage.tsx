/**
 * AIWorkspacePage — Engineering Agent chat & repository comprehension interface.
 *
 * Left panel  : conversation list (filterable by repository) + new conversation
 * Right panel : chat view with markdown code blocks + quick prompt suggestions
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PageLayout } from '@/components/layout/PageLayout';
import { aiApi } from '@/api/ai';
import { repositoryApi } from '@/api/repository';
import { MarkdownRenderer } from '@/components/ui/MarkdownRenderer';
import type {
  Conversation,
  ConversationMessage,
  Repository,
} from '@/types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch {
    return '';
  }
}

const PROMPT_SUGGESTIONS = [
  'Explain the overall project architecture and primary modules.',
  'Where is user authentication and session validation implemented?',
  'What external APIs or databases does this service interact with?',
  'Trace what happens when an event or request is processed end-to-end.',
];

// ── New Conversation Modal ─────────────────────────────────────────────────────

interface NewConvModalProps {
  repos: Repository[];
  onClose: () => void;
  onCreated: (conv: Conversation) => void;
  orgId: number;
}

function NewConvModal({ repos, onClose, onCreated, orgId }: NewConvModalProps) {
  const [repoId, setRepoId] = useState('');
  const [title, setTitle] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const readyRepos = repos.filter(r => r.status === 'ready');

  async function handleCreate() {
    if (!repoId || !title.trim()) {
      setError('Please select a repository and enter a title.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await aiApi.createConversation(orgId, {
        repository_id: repoId,
        title: title.trim(),
      });
      onCreated(res.data);
    } catch {
      setError('Failed to create conversation. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in">
      <div className="bg-surface-850 border border-white/10 rounded-2xl shadow-2xl w-full max-w-md p-6 animate-slide-up">
        <h2 className="text-base font-bold text-white mb-4">New Repository Conversation</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-surface-300 mb-1.5">
              Select Repository <span className="text-red-400">*</span>
            </label>
            {readyRepos.length === 0 ? (
              <p className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-xl px-3 py-2.5">
                No indexed repositories found. Please connect and sync a repository first.
              </p>
            ) : (
              <select
                value={repoId}
                onChange={e => setRepoId(e.target.value)}
                className="w-full bg-surface-900 border border-white/10 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-forge-500/40"
              >
                <option value="">Choose an indexed repository…</option>
                {readyRepos.map(r => (
                  <option key={r.id} value={String(r.id)} className="bg-surface-900 text-white">
                    {r.full_name}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-surface-300 mb-1.5">
              Investigation Topic / Title <span className="text-red-400">*</span>
            </label>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="e.g. Authentication flow & token lifecycle"
              className="w-full bg-surface-900 border border-white/10 rounded-xl px-3 py-2.5 text-xs text-white placeholder-surface-500 focus:outline-none focus:ring-2 focus:ring-forge-500/40"
            />
          </div>

          {error && (
            <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2">
              {error}
            </p>
          )}
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl border border-white/10 text-surface-400 text-xs hover:bg-white/5 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={loading || readyRepos.length === 0}
            className="flex-1 px-4 py-2.5 rounded-xl bg-gradient-to-r from-forge-600 to-forge-700 hover:from-forge-500 hover:to-forge-600 text-white text-xs font-semibold shadow-md transition-all disabled:opacity-50"
          >
            {loading ? 'Creating…' : 'Start Conversation'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Message Bubble ─────────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: ConversationMessage & { streaming?: boolean } }) {
  const isUser = msg.role === 'user';

  return (
    <div className={`flex gap-3.5 ${isUser ? 'flex-row-reverse' : ''} group`}>
      {/* Avatar */}
      <div
        className={`w-7 h-7 rounded-xl flex-shrink-0 flex items-center justify-center text-xs font-bold shadow-md
          ${isUser
            ? 'bg-gradient-to-br from-forge-500 to-purple-600 text-white'
            : 'bg-gradient-to-br from-emerald-500 to-cyan-500 text-white'
          }`}
      >
        {isUser ? 'U' : 'AI'}
      </div>

      {/* Bubble Content */}
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-xs leading-relaxed
          ${isUser
            ? 'bg-forge-600/25 border border-forge-500/30 text-white rounded-tr-sm'
            : 'bg-surface-800/90 border border-white/8 text-surface-200 rounded-tl-sm shadow-xl'
          }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{msg.content}</p>
        ) : (
          <div>
            <MarkdownRenderer content={msg.content} />
            {msg.streaming && (
              <span className="inline-block w-2 h-4 bg-emerald-400 rounded-sm ml-1 animate-pulse" />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function AIWorkspacePage() {
  const { orgId: orgIdStr } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const orgId = Number(orgIdStr);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConv, setActiveConv]       = useState<Conversation | null>(null);
  const [messages, setMessages]           = useState<(ConversationMessage & { streaming?: boolean })[]>([]);
  const [repos, setRepos]                 = useState<Repository[]>([]);
  const [loadingConvs, setLoadingConvs]   = useState(true);
  const [loadingMsgs, setLoadingMsgs]     = useState(false);
  const [showNewModal, setShowNewModal]   = useState(false);
  const [input, setInput]                 = useState('');
  const [streaming, setStreaming]         = useState(false);
  const [selectedRepoFilter, setSelectedRepoFilter] = useState<string>('all');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamCtrlRef  = useRef<AbortController | null>(null);
  const textareaRef    = useRef<HTMLTextAreaElement>(null);

  // Load conversations + repos
  useEffect(() => {
    if (!orgId) return;
    setLoadingConvs(true);
    Promise.all([
      aiApi.listConversations(orgId),
      repositoryApi.listRepos(orgId),
    ])
      .then(([convRes, repoRes]) => {
        setConversations(convRes.data.conversations || []);
        setRepos(repoRes.data.repositories || []);
        if (convRes.data.conversations?.length > 0) {
          setActiveConv(prev => prev ?? convRes.data.conversations[0]);
        }
      })
      .catch(console.error)
      .finally(() => setLoadingConvs(false));
  }, [orgId]);

  // Load messages when active conversation changes
  useEffect(() => {
    if (!activeConv) return;
    setLoadingMsgs(true);
    aiApi.getConversation(activeConv.id)
      .then(res => setMessages(res.data.messages || []))
      .catch(console.error)
      .finally(() => setLoadingMsgs(false));
  }, [activeConv]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSelectConv = useCallback((conv: Conversation) => {
    streamCtrlRef.current?.abort();
    setActiveConv(conv);
    setMessages([]);
  }, []);

  const handleNewConv = useCallback((conv: Conversation) => {
    setConversations(prev => [conv, ...prev]);
    setActiveConv(conv);
    setMessages([]);
    setShowNewModal(false);
  }, []);

  const handleDeleteConv = useCallback(async (convId: string) => {
    if (!confirm('Delete this conversation?')) return;
    try {
      await aiApi.deleteConversation(convId);
      setConversations(prev => prev.filter(c => c.id !== convId));
      if (activeConv?.id === convId) {
        setActiveConv(null);
        setMessages([]);
      }
    } catch (err) {
      console.error('Failed to delete conversation', err);
    }
  }, [activeConv]);

  const handleSend = useCallback((textToSend?: string) => {
    const text = (textToSend ?? input).trim();
    if (!text || !activeConv || streaming) return;

    // Optimistically add user message and AI placeholder
    const userMsg: ConversationMessage = {
      id: `tmp-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    const aiPlaceholder: ConversationMessage & { streaming: boolean } = {
      id: `tmp-ai-${Date.now()}`,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      streaming: true,
    };

    setMessages(prev => [...prev, userMsg, aiPlaceholder]);
    setInput('');
    setStreaming(true);

    streamCtrlRef.current = aiApi.streamMessage(
      activeConv.id,
      text,
      (token) => {
        setMessages(prev =>
          prev.map(m =>
            m.id === aiPlaceholder.id
              ? { ...m, content: m.content + token }
              : m,
          ),
        );
      },
      (fullText) => {
        setMessages(prev =>
          prev.map(m =>
            m.id === aiPlaceholder.id
              ? { ...m, content: fullText, streaming: false }
              : m,
          ),
        );
        setStreaming(false);
        setConversations(prev =>
          prev.map(c =>
            c.id === activeConv.id
              ? { ...c, updated_at: new Date().toISOString() }
              : c,
          ),
        );
      },
      (errMsg) => {
        setMessages(prev =>
          prev.map(m =>
            m.id === aiPlaceholder.id
              ? { ...m, content: `⚠️ ${errMsg}`, streaming: false }
              : m,
          ),
        );
        setStreaming(false);
      },
    );
  }, [input, activeConv, streaming]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 160) + 'px';
    }
  };

  const getRepoName = (repoId: string | null) => {
    if (!repoId) return null;
    return repos.find(r => String(r.id) === repoId)?.full_name ?? repoId;
  };

  const filteredConversations = conversations.filter(c => {
    if (selectedRepoFilter === 'all') return true;
    return c.repository_id === selectedRepoFilter;
  });

  return (
    <PageLayout fullBleed>
      <div className="flex h-screen min-h-0 overflow-hidden bg-surface-950">
        {/* ── Left Sidebar: Conversations ────────────────────────────────────── */}
        <aside className="w-80 flex-shrink-0 flex flex-col border-r border-white/6 bg-surface-900/60 backdrop-blur-sm">
          {/* Header */}
          <div className="p-4 border-b border-white/6 flex items-center justify-between">
            <div>
              <h2 className="text-xs font-bold text-white uppercase tracking-wider">Conversations</h2>
              <p className="text-[11px] text-surface-500">Repository Intelligence</p>
            </div>
            <button
              onClick={() => setShowNewModal(true)}
              title="New Conversation"
              className="px-2.5 py-1.5 rounded-xl bg-gradient-to-r from-forge-600 to-forge-700 hover:from-forge-500 hover:to-forge-600 text-white text-xs font-semibold flex items-center gap-1 shadow-md transition-all"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>New</span>
            </button>
          </div>

          {/* Repo Filter */}
          {repos.length > 1 && (
            <div className="px-3 pt-3">
              <select
                value={selectedRepoFilter}
                onChange={e => setSelectedRepoFilter(e.target.value)}
                className="w-full bg-surface-800 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-surface-300 focus:outline-none"
              >
                <option value="all">All Repositories ({conversations.length})</option>
                {repos.map(r => (
                  <option key={r.id} value={String(r.id)}>
                    {r.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Conversations List */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loadingConvs ? (
              <div className="flex items-center justify-center py-12">
                <div className="w-5 h-5 border-2 border-forge-400/30 border-t-forge-400 rounded-full animate-spin" />
              </div>
            ) : filteredConversations.length === 0 ? (
              <div className="text-center py-12 px-4 space-y-2">
                <p className="text-surface-500 text-xs">No conversations found.</p>
                <button
                  onClick={() => setShowNewModal(true)}
                  className="text-xs text-forge-400 hover:text-forge-300 font-medium"
                >
                  Start an investigation →
                </button>
              </div>
            ) : (
              filteredConversations.map(conv => {
                const isActive = activeConv?.id === conv.id;
                return (
                  <div
                    key={conv.id}
                    onClick={() => handleSelectConv(conv)}
                    className={`group w-full text-left rounded-xl px-3 py-2.5 transition-all cursor-pointer relative border ${
                      isActive
                        ? 'bg-forge-600/15 border-forge-500/40 shadow-sm'
                        : 'border-transparent hover:bg-white/5 hover:border-white/5'
                    }`}
                  >
                    <p className="text-xs font-semibold text-white truncate pr-6">{conv.title}</p>
                    {conv.repository_id && (
                      <p className="text-[11px] text-surface-400 truncate mt-0.5 font-mono">
                        {getRepoName(conv.repository_id)}
                      </p>
                    )}
                    <span className="text-[10px] text-surface-600 mt-1 block font-mono">
                      {formatDate(conv.updated_at)}
                    </span>

                    <button
                      onClick={e => {
                        e.stopPropagation();
                        handleDeleteConv(conv.id);
                      }}
                      title="Delete conversation"
                      className="absolute right-2 top-2.5 opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center text-surface-400 hover:text-red-400 transition-all"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </aside>

        {/* ── Right Panel: Chat Stream & Reasoning ────────────────────────────── */}
        <main className="flex-1 flex flex-col min-w-0 bg-surface-950">
          {!activeConv ? (
            <div className="flex flex-col items-center justify-center h-full text-center px-8">
              <div className="w-16 h-16 rounded-2xl bg-surface-850 border border-white/10 flex items-center justify-center mb-4 text-forge-400 shadow-xl">
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <h3 className="text-base font-bold text-white mb-1">Select or start a conversation</h3>
              <p className="text-surface-400 text-xs max-w-sm mb-6">
                Query repository structure, APIs, logic flow, and dependencies powered by vector semantic search.
              </p>
              <button
                onClick={() => setShowNewModal(true)}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-forge-600 to-forge-700 text-white text-xs font-semibold shadow-lg hover:from-forge-500 hover:to-forge-600 transition-all"
              >
                New Conversation
              </button>
            </div>
          ) : (
            <>
              {/* Chat Header */}
              <div className="px-6 py-3.5 border-b border-white/6 flex items-center justify-between flex-shrink-0 bg-surface-900/40">
                <div className="flex items-center gap-3">
                  <div>
                    <h3 className="text-xs font-bold text-white leading-tight">{activeConv.title}</h3>
                    {activeConv.repository_id && (
                      <span className="text-[11px] text-surface-400 font-mono">
                        Repository: {getRepoName(activeConv.repository_id)}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {streaming && (
                    <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-mono">
                      <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
                      Streaming Response…
                    </span>
                  )}
                  <button
                    onClick={() => navigate(`/organizations/${orgId}/tests`)}
                    className="text-[11px] font-medium text-cyan-400 hover:text-cyan-300 border border-cyan-500/30 px-2.5 py-1 rounded-lg transition-colors"
                  >
                    Test Assistant →
                  </button>
                </div>
              </div>

              {/* Messages Area */}
              <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
                {loadingMsgs ? (
                  <div className="flex items-center justify-center py-20">
                    <div className="w-6 h-6 border-2 border-forge-400/30 border-t-forge-400 rounded-full animate-spin" />
                  </div>
                ) : messages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-center max-w-lg mx-auto space-y-4">
                    <p className="text-surface-400 text-xs">
                      Ask any question about this codebase. ForgeAI retrieves the most relevant chunks before generating answers.
                    </p>
                    <div className="w-full space-y-2 text-left">
                      <p className="text-[11px] uppercase tracking-wider text-surface-500 font-semibold px-1">
                        Suggested Inquiries
                      </p>
                      {PROMPT_SUGGESTIONS.map((suggestion) => (
                        <button
                          key={suggestion}
                          onClick={() => handleSend(suggestion)}
                          className="w-full text-left p-3 rounded-xl bg-surface-900 border border-white/6 hover:border-forge-500/40 text-xs text-surface-300 hover:text-white transition-all"
                        >
                          "{suggestion}"
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  messages.map(msg => (
                    <div key={msg.id} className="space-y-1">
                      <MessageBubble msg={msg} />
                      <p className={`text-[10px] text-surface-600 font-mono ${msg.role === 'user' ? 'text-right' : 'ml-10'}`}>
                        {formatTime(msg.created_at)}
                      </p>
                    </div>
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Input Area */}
              <div className="p-4 border-t border-white/6 flex-shrink-0 bg-surface-900/30">
                <div className="flex gap-3 items-end bg-surface-900/90 border border-white/10 rounded-2xl px-4 py-3 focus-within:border-forge-500/60 focus-within:ring-2 focus-within:ring-forge-500/20 transition-all">
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={handleInputChange}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask about architecture, functions, files, or flow… (Enter to send, Shift+Enter for newline)"
                    rows={1}
                    disabled={streaming}
                    className="flex-1 bg-transparent text-xs text-white placeholder-surface-500 resize-none outline-none leading-relaxed min-h-[22px] max-h-40 disabled:opacity-50"
                  />
                  <button
                    onClick={() => handleSend()}
                    disabled={!input.trim() || streaming}
                    title="Send message"
                    className="flex-shrink-0 w-8 h-8 rounded-xl bg-gradient-to-r from-forge-600 to-forge-700 hover:from-forge-500 hover:to-forge-600 disabled:opacity-30 disabled:cursor-not-allowed text-white flex items-center justify-center transition-all shadow-md"
                  >
                    {streaming ? (
                      <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : (
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            </>
          )}
        </main>
      </div>

      {showNewModal && (
        <NewConvModal
          repos={repos}
          orgId={orgId}
          onClose={() => setShowNewModal(false)}
          onCreated={handleNewConv}
        />
      )}
    </PageLayout>
  );
}
