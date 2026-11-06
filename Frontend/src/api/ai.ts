/**
 * aiApi — all calls to the AI Service (port 8002).
 */
import apiClient from './client';
import type {
  Conversation,
  ConversationListResponse,
  ConversationMessage,
  CreateConversationPayload,
  SendMessageResponse,
  TestAssistanceRequest,
} from '@/types';

export const aiApi = {
  // ── Conversations ───────────────────────────────────────────────────────────

  /** Create a new conversation tied to a repository. */
  createConversation: (orgId: number, payload: CreateConversationPayload) =>
    apiClient.post<Conversation>(
      `/api/v1/organizations/${orgId}/conversations`,
      payload,
    ),

  /** List the caller's conversations in an organization. */
  listConversations: (orgId: number, repositoryId?: number) =>
    apiClient.get<ConversationListResponse>(
      `/api/v1/organizations/${orgId}/conversations`,
      repositoryId ? { params: { repository_id: String(repositoryId) } } : undefined,
    ),

  /** Get a conversation with all its messages. */
  getConversation: (conversationId: string) =>
    apiClient.get<Conversation & { messages: ConversationMessage[] }>(
      `/api/v1/conversations/${conversationId}`,
    ),

  /** Delete a conversation. */
  deleteConversation: (conversationId: string) =>
    apiClient.delete(`/api/v1/conversations/${conversationId}`),

  // ── Messages ────────────────────────────────────────────────────────────────

  /** Send a message and receive the full AI response (synchronous). */
  sendMessage: (conversationId: string, content: string) =>
    apiClient.post<SendMessageResponse>(
      `/api/v1/conversations/${conversationId}/messages`,
      { content },
    ),

  /** Ask the Testing Agent for missing tests for a file or PR. */
  testAssistance: (conversationId: string, payload: TestAssistanceRequest) =>
    apiClient.post<SendMessageResponse>(
      `/api/v1/conversations/${conversationId}/test-assistance`,
      payload,
    ),

  /** Inspect an agent run metadata. */
  getAgentRun: (agentRunId: string) =>
    apiClient.get<{
      id: string;
      conversation_id: string;
      type: string;
      status: string;
      total_tokens: number | null;
      started_at: string;
      completed_at: string | null;
      error_message: string | null;
    }>(`/api/v1/agent-runs/${agentRunId}`),

  /**
   * Send a message and stream the AI response token-by-token via SSE.
   *
   * @param conversationId  Target conversation
   * @param content         The user's message
   * @param onToken         Called for each streamed token string
   * @param onDone          Called when the stream ends (with full assembled text)
   * @param onError         Called on network or server errors
   * @returns AbortController so the caller can cancel the stream
   */
  streamMessage: (
    conversationId: string,
    content: string,
    onToken: (token: string) => void,
    onDone: (fullText: string) => void,
    onError: (err: string) => void,
  ): AbortController => {
    const ctrl = new AbortController();
    const token = localStorage.getItem('access_token');

    const url =
      `/api/v1/conversations/${conversationId}/messages/stream` +
      `?content=${encodeURIComponent(content)}`;

    (async () => {
      try {
        const res = await fetch(url, {
          signal: ctrl.signal,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });

        if (!res.ok) {
          onError(`Server error: ${res.status}`);
          return;
        }

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        const parts: string[] = [];
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const raw = line.slice(6).trim();
            if (raw === '[DONE]') {
              onDone(parts.join(''));
              return;
            }
            try {
              const parsed = JSON.parse(raw);
              if (typeof parsed === 'string') {
                parts.push(parsed);
                onToken(parsed);
              } else if (parsed?.error) {
                onError(parsed.error);
                return;
              }
            } catch {
              // ignore malformed lines
            }
          }
        }
        onDone(parts.join(''));
      } catch (err: unknown) {
        if ((err as Error)?.name !== 'AbortError') {
          onError((err as Error)?.message ?? 'Unknown error');
        }
      }
    })();

    return ctrl;
  },
};
