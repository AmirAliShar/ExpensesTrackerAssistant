import React, { useState } from 'react';
import { Memory, api } from '../api';

interface SettingsPageProps {
  memories: Memory[];
  onRefreshMemories: () => void;
  currency: string;
  onCurrencyChange: (c: string) => void;
  userEmail: string;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({
  memories,
  onRefreshMemories,
  currency,
  onCurrencyChange,
  userEmail,
}) => {
  const [newMemory, setNewMemory] = useState('');
  const [memoryType, setMemoryType] = useState('preference');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAddMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMemory.trim()) return;

    setIsSubmitting(true);
    try {
      await api.createMemory({
        memory_type: memoryType,
        content: newMemory.trim(),
      });
      setNewMemory('');
      onRefreshMemories();
    } catch (err: any) {
      alert(err.message || 'Error saving memory');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteMemory = async (id: number) => {
    if (window.confirm('Delete this long-term memory? The assistant will forget it.')) {
      try {
        await api.deleteMemory(id);
        onRefreshMemories();
      } catch (err: any) {
        alert(err.message || 'Error deleting memory');
      }
    }
  };

  const handleClearAll = async () => {
    if (window.confirm('Clear all long-term memories for this account? This cannot be undone.')) {
      try {
        await api.clearMemories();
        onRefreshMemories();
      } catch (err: any) {
        alert(err.message || 'Error clearing memories');
      }
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
      {/* Account & Currency Preferences */}
      <div className="glass-card" style={{ padding: '24px' }}>
        <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)', marginBottom: '6px' }}>
          Account & App Preferences
        </h3>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '20px' }}>
          Logged in as: <strong style={{ color: 'var(--text-main)' }}>{userEmail}</strong>
        </p>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '20px', alignItems: 'center' }}>
          <div>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px', fontWeight: 600 }}>
              Default Currency
            </label>
            <select
              value={currency}
              onChange={(e) => onCurrencyChange(e.target.value)}
              style={{
                padding: '10px 16px',
                borderRadius: '8px',
                background: 'var(--bg-input)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-main)',
                fontSize: '0.9rem',
              }}
            >
              <option value="PKR">PKR (Pakistani Rupee - Rs.)</option>
              <option value="USD">USD ($)</option>
              <option value="EUR">EUR (€)</option>
              <option value="GBP">GBP (£)</option>
              <option value="AED">AED (Dirham)</option>
              <option value="SAR">SAR (Riyal)</option>
            </select>
          </div>
        </div>
      </div>

      {/* PostgreSQL Long-Term Memory Management */}
      <div className="glass-card" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '1.25rem' }}>🧠</span>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)' }}>
                PostgreSQL Long-Term AI Memory Store
              </h3>
            </div>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              These persistent facts survive server restarts and cross-session threads. They are injected into every LangGraph reasoning cycle.
            </p>
          </div>

          {memories.length > 0 && (
            <button
              onClick={handleClearAll}
              style={{
                padding: '6px 14px',
                borderRadius: '8px',
                background: 'var(--accent-rose-subtle)',
                color: 'var(--accent-rose)',
                border: 'none',
                fontSize: '0.78rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Clear All Memories
            </button>
          )}
        </div>

        {/* Add Memory Form */}
        <form onSubmit={handleAddMemory} style={{ display: 'flex', gap: '10px', marginBottom: '24px', flexWrap: 'wrap' }}>
          <select
            value={memoryType}
            onChange={(e) => setMemoryType(e.target.value)}
            style={{
              padding: '10px 12px',
              borderRadius: '8px',
              background: 'var(--bg-input)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-main)',
              fontSize: '0.85rem',
              flex: '0 0 130px',
            }}
          >
            <option value="preference">Preference</option>
            <option value="goal">Goal</option>
            <option value="fact">Fact</option>
            <option value="habit">Habit</option>
          </select>

          <input
            type="text"
            required
            placeholder="Teach the agent a new preference or fact (e.g. 'I do not buy fast food on weekdays')..."
            value={newMemory}
            onChange={(e) => setNewMemory(e.target.value)}
            style={{
              flex: '1 1 240px',
              padding: '10px 14px',
              borderRadius: '8px',
              background: 'var(--bg-input)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-main)',
              outline: 'none',
              fontSize: '0.9rem',
            }}
          />

          <button type="submit" disabled={isSubmitting} className="btn-primary" style={{ padding: '10px 18px', fontSize: '0.85rem' }}>
            {isSubmitting ? 'Saving...' : 'Add Memory'}
          </button>
        </form>

        {/* Existing Memories List */}
        {memories.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
            No persistent memories stored yet. You can speak to the assistant or add one above.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {memories.map((m) => (
              <div
                key={m.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 16px',
                  borderRadius: '10px',
                  background: 'var(--bg-hover-subtle)',
                  border: '1px solid var(--border-subtle)',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      textTransform: 'uppercase',
                      background: 'var(--accent-blue-subtle)',
                      color: 'var(--accent-blue-text)',
                      fontWeight: 600,
                      flexShrink: 0,
                    }}
                  >
                    {m.memory_type}
                  </span>
                  <span style={{ fontSize: '0.9rem', color: 'var(--text-main)', wordBreak: 'break-word' }}>{m.content}</span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0 }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Source: {m.source}
                  </span>
                  <button
                    onClick={() => handleDeleteMemory(m.id)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--accent-rose)',
                      cursor: 'pointer',
                      fontSize: '0.85rem',
                      padding: '4px',
                    }}
                    title="Delete Memory"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
