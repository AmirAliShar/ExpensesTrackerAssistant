import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { api, AgentResponse, PendingConfirmation, Conversation } from '../api';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  spokenSummary?: string;
  toolsUsed?: string[];
  memoriesUsed?: string[];
  pendingConfirmation?: PendingConfirmation | null;
  timestamp: string;
}

const WELCOME_MESSAGE: Message = {
  id: 'welcome',
  sender: 'assistant',
  text: 'How can I help you with your finances today?',
  spokenSummary: 'How can I help you with your finances today?',
  timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
};

export const AIAssistant: React.FC<{ onDataChanged?: () => void }> = ({ onDataChanged }) => {
  // Stable chat session thread ID persisted in localStorage
  const [threadId, setThreadId] = useState<string>(() => {
    return localStorage.getItem('finpilot_chat_thread_id') || `session_${Date.now()}`;
  });

  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [recognitionError, setRecognitionError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationSearch, setConversationSearch] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [lastUserQuery, setLastUserQuery] = useState('');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Persist thread ID to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('finpilot_chat_thread_id', threadId);
  }, [threadId]);

  const refreshConversations = async (search = conversationSearch) => {
    try {
      setConversations(await api.getConversations(search));
    } catch (err) {
      console.warn('Could not load conversations:', err);
    }
  };

  useEffect(() => {
    refreshConversations();
  }, []);

  useEffect(() => {
    const timeout = window.setTimeout(() => refreshConversations(conversationSearch), 250);
    return () => window.clearTimeout(timeout);
  }, [conversationSearch]);

  // Restore conversation history from PostgreSQL checkpointer on mount or thread change
  useEffect(() => {
    let isMounted = true;
    api.getAgentHistory(threadId)
      .then((history) => {
        if (!isMounted) return;
        if (history.messages && history.messages.length > 0) {
          const restored: Message[] = history.messages.map((m, idx) => ({
            id: m.id || `restored_${idx}`,
            sender: m.sender as 'user' | 'assistant',
            text: m.text,
            spokenSummary: m.spokenSummary,
            toolsUsed: m.toolsUsed,
            memoriesUsed: m.memoriesUsed,
            pendingConfirmation: idx === history.messages.length - 1 ? history.pending_confirmation : null,
            timestamp: m.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          }));
          setMessages(restored);
        } else {
          setMessages([WELCOME_MESSAGE]);
        }
      })
      .catch((err) => {
        console.warn('Could not restore chat history:', err);
      });

    return () => {
      isMounted = false;
    };
  }, [threadId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Audio Recording with MediaRecorder for Whisper STT
  const toggleRecording = async () => {
    if (isRecording) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      setIsRecording(false);
    } else {
      setRecognitionError(null);
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mediaRecorder = new MediaRecorder(stream);
        audioChunksRef.current = [];

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            audioChunksRef.current.push(event.data);
          }
        };

        mediaRecorder.onstop = async () => {
          stream.getTracks().forEach((track) => track.stop());
          const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
          if (audioBlob.size > 500) {
            try {
              setLoading(true);
              const transcript = await api.transcribeAudio(audioBlob);
              if (transcript && transcript.trim()) {
                setInput(transcript.trim());
                handleSend(transcript.trim());
              }
            } catch (err: any) {
              setRecognitionError(`Whisper STT note: ${err.message || 'Falling back to text mode.'}`);
            } finally {
              setLoading(false);
            }
          }
        };

        mediaRecorderRef.current = mediaRecorder;
        mediaRecorder.start();
        setIsRecording(true);
      } catch (err: any) {
        console.warn('Microphone error:', err);
        setRecognitionError('Microphone permission denied or not supported in this browser.');
        setIsRecording(false);
      }
    }
  };

  const speakText = (text: string) => {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    if (!text) return;

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    window.speechSynthesis.speak(utterance);
  };

  const stopSpeaking = () => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }
  };

  const handleNewChat = async () => {
    const newSessionId = `session_${Date.now()}`;
    try {
      await api.createConversation(newSessionId);
    } catch {}
    await refreshConversations();
    setThreadId(newSessionId);
    setMessages([WELCOME_MESSAGE]);
  };

  const selectConversation = (conversation: Conversation) => {
    setThreadId(conversation.thread_id);
  };

  const renameConversation = async (conversation: Conversation) => {
    const title = window.prompt('Rename conversation', conversation.title);
    if (!title?.trim()) return;
    await api.updateConversation(conversation.id, { title: title.trim() });
    await refreshConversations();
  };

  const archiveConversation = async (conversation: Conversation) => {
    await api.updateConversation(conversation.id, { archived: true });
    await refreshConversations();
  };

  const deleteConversation = async (conversation: Conversation) => {
    if (!window.confirm(`Delete "${conversation.title}"? Financial records will not be deleted.`)) return;
    await api.deleteConversation(conversation.id);
    if (threadId === conversation.thread_id) {
      const newSessionId = `session_${Date.now()}`;
      setThreadId(newSessionId);
      setMessages([WELCOME_MESSAGE]);
    }
    await refreshConversations();
  };

  const handleSend = async (queryText?: string) => {
    const textToSend = (queryText || input).trim();
    if (!textToSend || loading) return;
    setLastUserQuery(textToSend);

    setInput('');
    const userMsg: Message = {
      id: Date.now().toString(),
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    const streamingMessageId = (Date.now() + 1).toString();
    setMessages((prev) => [
      ...prev,
      {
        id: streamingMessageId,
        sender: 'assistant',
        text: '',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);

    try {
      let streamedText = '';
      const response: AgentResponse = await api.queryAgentStream(textToSend, threadId, (chunk) => {
        streamedText += chunk;
        setMessages((prev) => prev.map((message) =>
          message.id === streamingMessageId ? { ...message, text: streamedText } : message
        ));
      });
      const assistantMsg: Message = {
        id: streamingMessageId,
        sender: 'assistant',
        text: streamedText || response.response,
        spokenSummary: response.spoken_summary,
        toolsUsed: response.executed_tools,
        memoriesUsed: response.memories_used,
        pendingConfirmation: response.pending_confirmation,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => prev.map((message) => message.id === streamingMessageId ? assistantMsg : message));

      if (voiceEnabled && response.spoken_summary) {
        speakText(response.spoken_summary);
      }

      if (response.executed_tools && response.executed_tools.length > 0 && onDataChanged) {
        onDataChanged();
      }
    } catch (err: any) {
      try {
        const fallback: AgentResponse = await api.queryAgent(textToSend, threadId, voiceEnabled);
        setMessages((prev) => prev.map((message) => message.id === streamingMessageId ? {
          id: streamingMessageId,
          sender: 'assistant',
          text: fallback.response,
          spokenSummary: fallback.spoken_summary,
          toolsUsed: fallback.executed_tools,
          memoriesUsed: fallback.memories_used,
          pendingConfirmation: fallback.pending_confirmation,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        } : message));
      } catch (fallbackError: any) {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'assistant',
        text: `⚠️ Execution Notice: ${(fallbackError as any).message || err.message || 'Server error'}. Please verify backend connection.`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => prev.map((message) => message.id === streamingMessageId ? errorMsg : message));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmationAction = async (msgId: string, actionToken: string, confirmed: boolean) => {
    setLoading(true);
    try {
      const res = await api.confirmAction(actionToken, confirmed, threadId);
      // Remove or update pending confirmation on the message
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId ? { ...m, pendingConfirmation: null } : m
        )
      );

      const confirmMsg: Message = {
        id: (Date.now() + 2).toString(),
        sender: 'assistant',
        text: res.message || (confirmed ? 'Action confirmed and executed.' : 'Action cancelled.'),
        spokenSummary: confirmed ? 'Action executed successfully.' : 'Action cancelled.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, confirmMsg]);

      if (voiceEnabled && confirmMsg.spokenSummary) {
        speakText(confirmMsg.spokenSummary);
      }

      if (onDataChanged) {
        onDataChanged();
      }
    } catch (err: any) {
      alert(`Error during confirmation: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const samplePrompts = [
    'Help me add a new expense',
    'Help me add new income',
    'Show my recent transactions',
    'Analyze my spending this month',
    'Create a monthly budget',
    'Create a savings goal',
  ];

  return (
    <div style={{ display: 'flex', height: 'min(720px, calc(100vh - 130px))', minHeight: '460px', background: 'var(--bg-card)', borderRadius: '16px', border: '1px solid var(--border-subtle)', overflow: 'hidden', boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)' }}>
      {sidebarOpen && (
        <aside style={{ width: '250px', flexShrink: 0, borderRight: '1px solid var(--border-subtle)', background: 'var(--bg-elevated)', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '12px' }}>
            <button className="btn-primary" onClick={handleNewChat} style={{ width: '100%' }}>＋ New Chat</button>
            <input
              value={conversationSearch}
              onChange={(e) => setConversationSearch(e.target.value)}
              placeholder="Search conversations"
              style={{ width: '100%', marginTop: '10px', padding: '9px 10px', borderRadius: '8px', border: '1px solid var(--border-subtle)', background: 'var(--bg-input)', color: 'var(--text-main)' }}
            />
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 12px' }}>
            {conversations.map((conversation) => (
              <div
                key={conversation.id}
                onClick={() => selectConversation(conversation)}
                style={{ cursor: 'pointer', borderRadius: '9px', padding: '9px 10px', marginBottom: '4px', background: threadId === conversation.thread_id ? 'var(--accent-blue-subtle)' : 'transparent', border: threadId === conversation.thread_id ? '1px solid var(--border-focus)' : '1px solid transparent' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px' }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.82rem', fontWeight: 600 }}>{conversation.title}</span>
                  <div style={{ display: 'flex', gap: '2px' }}>
                    <button onClick={(e) => { e.stopPropagation(); renameConversation(conversation); }} title="Rename" style={{ border: 'none', background: 'none', cursor: 'pointer' }}>✎</button>
                    <button onClick={(e) => { e.stopPropagation(); archiveConversation(conversation); }} title="Archive" style={{ border: 'none', background: 'none', cursor: 'pointer' }}>⌄</button>
                    <button onClick={(e) => { e.stopPropagation(); deleteConversation(conversation); }} title="Delete" style={{ border: 'none', background: 'none', cursor: 'pointer' }}>×</button>
                  </div>
                </div>
                <div style={{ color: 'var(--text-dim)', fontSize: '0.68rem', marginTop: '3px' }}>{new Date(conversation.updated_at).toLocaleDateString()}</div>
              </div>
            ))}
            {conversations.length === 0 && <div style={{ padding: '12px', color: 'var(--text-muted)', fontSize: '0.78rem' }}>No conversations yet.</div>}
          </div>
        </aside>
      )}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div
        style={{
          padding: '12px 18px',
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '10px',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'rgba(0,0,0,0.25)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: '200px' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, var(--primary-blue), var(--hover-blue))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '1.1rem',
              color: '#ffffff',
              boxShadow: '0 4px 12px var(--glow-blue)',
              flexShrink: 0,
            }}
          >
            ⚡
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.98rem', color: 'var(--text-main)' }}>AI Expense Tracker Assistant</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--accent-emerald)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-emerald)' }} />
              PostgreSQL Checkpointed Memory Active
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <button
            onClick={() => setSidebarOpen((open) => !open)}
            className="btn-secondary"
            style={{ padding: '6px 10px', minHeight: '36px' }}
            title={sidebarOpen ? 'Collapse conversations' : 'Expand conversations'}
          >
            {sidebarOpen ? '‹' : '›'}
          </button>
          <button
            onClick={handleNewChat}
            className="btn-secondary"
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              fontSize: '0.78rem',
              minHeight: '36px',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
            }}
            title="Start a new conversation thread"
          >
            ➕ New Chat
          </button>

          <button
            onClick={() => setVoiceEnabled(!voiceEnabled)}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: `1px solid ${voiceEnabled ? 'var(--primary-blue)' : 'var(--border-subtle)'}`,
              background: voiceEnabled ? 'var(--accent-blue-subtle)' : 'transparent',
              color: voiceEnabled ? 'var(--accent-blue-text)' : 'var(--text-muted)',
              fontSize: '0.78rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              minHeight: '36px',
            }}
          >
            {voiceEnabled ? '🔊 Voice On' : '🔇 Voice Off'}
          </button>

          {isSpeaking && (
            <button
              onClick={stopSpeaking}
              style={{
                padding: '6px 10px',
                borderRadius: '8px',
                background: 'var(--accent-rose)',
                color: '#fff',
                border: 'none',
                fontSize: '0.75rem',
                cursor: 'pointer',
                minHeight: '36px',
              }}
            >
              ⏹ Stop
            </button>
          )}
        </div>
      </div>

      {/* Messages Scroll View */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
          WebkitOverflowScrolling: 'touch',
        }}
      >
        {messages.map((m) => (
          <div
            key={m.id}
            style={{
              display: 'flex',
              justifyContent: m.sender === 'user' ? 'flex-end' : 'flex-start',
              width: '100%',
            }}
          >
            <div
              style={{
                maxWidth: 'min(90%, 650px)',
                padding: '12px 16px',
                borderRadius: m.sender === 'user' ? '14px 14px 2px 14px' : '14px 14px 14px 2px',
                background: m.sender === 'user' ? 'var(--primary-blue)' : 'var(--bg-elevated)',
                color: m.sender === 'user' ? '#ffffff' : 'var(--text-main)',
                border: m.sender === 'assistant' ? '1px solid var(--border-subtle)' : 'none',
                boxShadow: m.sender === 'user' ? '0 4px 12px var(--glow-blue)' : 'var(--shadow-sm)',
                wordBreak: 'break-word',
                overflowWrap: 'anywhere',
              }}
            >
              <div style={{ lineHeight: '1.55', fontSize: '0.9rem' }}>
                <ReactMarkdown>{m.text}</ReactMarkdown>
              </div>

              {/* Interactive Human-in-the-Loop Confirmation Card */}
              {m.pendingConfirmation && (
                <div
                  style={{
                    marginTop: '12px',
                    padding: '12px',
                    borderRadius: '10px',
                    background: 'rgba(239, 68, 68, 0.12)',
                    border: '1px solid rgba(239, 68, 68, 0.35)',
                  }}
                >
                  <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#fca5a5', marginBottom: '6px' }}>
                    🛡️ Action Confirmation Required
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#cbd5e1', marginBottom: '12px', lineHeight: '1.4' }}>
                    {m.pendingConfirmation.summary}
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <button
                      onClick={() => handleConfirmationAction(m.id, m.pendingConfirmation!.action_token, true)}
                      style={{
                        padding: '8px 16px',
                        borderRadius: '8px',
                        background: '#ef4444',
                        color: '#fff',
                        border: 'none',
                        fontSize: '0.85rem',
                        fontWeight: 700,
                        cursor: 'pointer',
                        minHeight: '42px',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      ✓ Yes, Confirm Action
                    </button>
                    <button
                      onClick={() => handleConfirmationAction(m.id, m.pendingConfirmation!.action_token, false)}
                      style={{
                        padding: '8px 14px',
                        borderRadius: '8px',
                        background: 'rgba(255, 255, 255, 0.1)',
                        color: '#cbd5e1',
                        border: '1px solid rgba(255, 255, 255, 0.2)',
                        fontSize: '0.85rem',
                        cursor: 'pointer',
                        minHeight: '42px',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      ✕ Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Tools Badges */}
              {m.toolsUsed && m.toolsUsed.length > 0 && (
                <div style={{ marginTop: '10px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {m.toolsUsed.map((tool) => (
                    <span
                      key={tool}
                      style={{
                        fontSize: '0.7rem',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        background: 'rgba(16, 185, 129, 0.15)',
                        color: '#34d399',
                        border: '1px solid rgba(16, 185, 129, 0.3)',
                      }}
                    >
                      🛠 Tool: {tool}
                    </span>
                  ))}
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px' }}>
                <span style={{ fontSize: '0.7rem', color: m.sender === 'user' ? '#c7d2fe' : '#64748b' }}>{m.timestamp}</span>
                {m.sender === 'assistant' && (
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <button
                      onClick={() => navigator.clipboard?.writeText(m.text)}
                      style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '0.78rem', padding: '2px 6px' }}
                      title="Copy response"
                    >
                      Copy
                    </button>
                    {lastUserQuery && (
                      <button
                        onClick={() => handleSend(lastUserQuery)}
                        disabled={loading}
                        style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '0.78rem', padding: '2px 6px' }}
                        title="Regenerate response"
                      >
                        Retry
                      </button>
                    )}
                    {m.spokenSummary && (
                      <button
                        onClick={() => speakText(m.spokenSummary!)}
                        style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '0.85rem', padding: '2px 6px' }}
                        title="Read summary aloud"
                      >
                        🔊
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.85rem', padding: '6px 0' }}>
            <div className="voice-wave" style={{ display: 'flex', alignItems: 'center' }}>
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>
            AI Expense Tracker reasoning with LangGraph & verifying database records...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Quick Prompt Pills */}
      <div
        style={{
          padding: '8px 16px',
          display: 'flex',
          gap: '8px',
          overflowX: 'auto',
          borderTop: '1px solid var(--border-subtle)',
          WebkitOverflowScrolling: 'touch',
          scrollbarWidth: 'none',
        }}
      >
        {samplePrompts.map((p) => (
          <button
            key={p}
            onClick={() => handleSend(p)}
            style={{
              background: 'var(--bg-hover-subtle)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-muted)',
              borderRadius: '20px',
              padding: '6px 14px',
              fontSize: '0.78rem',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              flexShrink: 0,
              transition: 'all 0.15s ease',
            }}
          >
            {p}
          </button>
        ))}
      </div>

      {/* Input Bar & Voice Mic */}
      <div
        style={{
          padding: '12px 16px',
          borderTop: '1px solid var(--border-subtle)',
          background: 'var(--bg-card)',
          display: 'flex',
          gap: '8px',
          alignItems: 'center',
        }}
      >
        <button
          onClick={toggleRecording}
          style={{
            width: '42px',
            height: '42px',
            borderRadius: '50%',
            border: 'none',
            background: isRecording ? 'var(--accent-rose)' : 'var(--bg-hover-subtle)',
            color: isRecording ? '#ffffff' : 'var(--text-main)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '1.1rem',
            transition: 'all 0.2s',
            boxShadow: isRecording ? '0 0 16px rgba(239, 68, 68, 0.6)' : 'none',
            flexShrink: 0,
          }}
          title={isRecording ? 'Stop listening (transcribe via Whisper)' : 'Start voice recognition (Groq Whisper Large v3)'}
        >
          {isRecording ? '🔴' : '🎤'}
        </button>

        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder={isRecording ? 'Listening... Speak your command now...' : 'How can I help you?'}
          style={{
            flex: 1,
            padding: '10px 14px',
            borderRadius: '10px',
            background: 'var(--bg-input)',
            border: '1px solid var(--border-subtle)',
            color: 'var(--text-main)',
            outline: 'none',
            fontSize: '0.9rem',
            minHeight: '42px',
          }}
        />

        <button
          onClick={() => handleSend()}
          disabled={loading || !input.trim()}
          className="btn-primary"
          style={{ padding: '8px 16px', minHeight: '42px', flexShrink: 0 }}
        >
          Send
        </button>
      </div>

      {recognitionError && (
        <div style={{ padding: '6px 16px', background: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', fontSize: '0.75rem' }}>
          {recognitionError}
        </div>
      )}
      </div>
    </div>
  );
};
