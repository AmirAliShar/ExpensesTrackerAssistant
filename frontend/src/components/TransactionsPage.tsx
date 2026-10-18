import React, { useState, useEffect, useRef } from 'react';
import { Transaction, api } from '../api';

interface TransactionsPageProps {
  transactions: Transaction[];
  onRefresh: () => void;
  currency?: string;
}

const EXPENSE_CATEGORIES = [
  'Food',
  'Travel',
  'Education',
  'Medicine',
  'Rent',
  'Utilities',
  'Shopping',
  'Fruit',
  'Friends',
  'Entertainment',
  'Other',
];

const INCOME_CATEGORIES = [
  'Salary',
  'Freelance',
  'Business',
  'Investment',
  'Bonus',
  'Gift',
  'Other',
];

export const TransactionsPage: React.FC<TransactionsPageProps> = ({
  transactions,
  onRefresh,
  currency = 'PKR',
}) => {
  const [filterCategory, setFilterCategory] = useState('All');
  const [filterType, setFilterType] = useState('all');
  const [search, setSearch] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);

  // Contextual action menu state (stores transaction id currently open)
  const [activeMenuTxId, setActiveMenuTxId] = useState<number | null>(null);
  const menuContainerRef = useRef<HTMLDivElement>(null);

  // Form states
  const [formDate, setFormDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [formCategory, setFormCategory] = useState(EXPENSE_CATEGORIES[0]);
  const [formAmount, setFormAmount] = useState('');
  const [formType, setFormType] = useState<'expense' | 'income'>('expense');
  const [formDescription, setFormDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Close contextual menu on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuContainerRef.current && !menuContainerRef.current.contains(e.target as Node)) {
        setActiveMenuTxId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleTypeChange = (newType: 'expense' | 'income') => {
    setFormType(newType);
    if (newType === 'income') {
      if (!INCOME_CATEGORIES.includes(formCategory)) {
        setFormCategory(INCOME_CATEGORIES[0]);
      }
    } else {
      if (!EXPENSE_CATEGORIES.includes(formCategory)) {
        setFormCategory(EXPENSE_CATEGORIES[0]);
      }
    }
  };

  const filteredTransactions = transactions.filter((t) => {
    if (filterCategory !== 'All' && t.category.toLowerCase() !== filterCategory.toLowerCase()) return false;
    if (filterType !== 'all' && t.type !== filterType) return false;
    if (search && !t.description?.toLowerCase().includes(search.toLowerCase()) && !t.category.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const handleOpenAdd = (type: 'expense' | 'income' = 'expense') => {
    setEditingTx(null);
    setFormDate(new Date().toISOString().split('T')[0]);
    setFormType(type);
    setFormCategory(type === 'income' ? INCOME_CATEGORIES[0] : EXPENSE_CATEGORIES[0]);
    setFormAmount('');
    setFormDescription('');
    setShowModal(true);
  };

  const handleOpenEdit = (tx: Transaction) => {
    setEditingTx(tx);
    setFormDate(tx.date);
    setFormCategory(tx.category);
    setFormAmount(String(tx.amount));
    setFormType(tx.type);
    setFormDescription(tx.description || '');
    setShowModal(true);
    setActiveMenuTxId(null);
  };

  const handleDelete = async (id: number) => {
    setActiveMenuTxId(null);
    if (window.confirm(`Are you sure you want to delete transaction #${id}?`)) {
      try {
        await api.deleteTransaction(id);
        onRefresh();
      } catch (err: any) {
        alert(err.message || 'Error deleting transaction');
      }
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const amountVal = parseFloat(formAmount);
    if (isNaN(amountVal) || amountVal <= 0) {
      alert('Please enter a valid positive amount.');
      return;
    }

    setIsSubmitting(true);
    try {
      if (editingTx) {
        await api.updateTransaction(editingTx.id, {
          category: formCategory,
          amount: amountVal,
          type: formType,
          date: formDate,
          description: formDescription,
        });
      } else {
        await api.createTransaction({
          category: formCategory,
          amount: amountVal,
          type: formType,
          date: formDate,
          description: formDescription,
        });
      }
      setShowModal(false);
      onRefresh();
    } catch (err: any) {
      alert(err.message || 'Error saving transaction');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Helper for category indicator icon
  const getCategoryIcon = (category: string, type: 'expense' | 'income') => {
    if (type === 'income') return '💰';
    switch (category.toLowerCase()) {
      case 'food':
      case 'fruit':
        return '🍔';
      case 'travel':
        return '✈️';
      case 'education':
        return '📚';
      case 'medicine':
        return '💊';
      case 'rent':
      case 'utilities':
        return '🏠';
      case 'shopping':
        return '🛍️';
      case 'friends':
      case 'entertainment':
        return '🎉';
      default:
        return '💳';
    }
  };

  return (
    <div ref={menuContainerRef} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Page Title & Quick Action Buttons */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px' }}>
        <div>
          <h2 style={{ fontSize: 'clamp(1.3rem, 3vw, 1.6rem)', fontWeight: 800, color: 'var(--text-main)' }}>
            Transactions Ledger
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Authoritative transactional history backed by PostgreSQL.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            onClick={() => handleOpenAdd('income')}
            style={{
              background: 'var(--accent-emerald-subtle)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              color: 'var(--accent-emerald)',
              padding: '8px 16px',
              borderRadius: '10px',
              fontWeight: 600,
              fontSize: '0.85rem',
              cursor: 'pointer',
              minHeight: '40px',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.2s ease',
            }}
          >
            <span>+</span> Add Income
          </button>
          <button
            onClick={() => handleOpenAdd('expense')}
            className="btn-primary"
            style={{ padding: '8px 16px', fontSize: '0.85rem', minHeight: '40px' }}
          >
            <span>+</span> Add Expense
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div
        className="glass-card"
        style={{
          padding: '14px 18px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', flex: 1 }}>
          <input
            type="text"
            placeholder="Search description or category..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              padding: '9px 14px',
              borderRadius: '8px',
              background: 'var(--bg-input)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-main)',
              fontSize: '0.85rem',
              minWidth: 'min(100%, 220px)',
              flex: '1 1 200px',
            }}
          />

          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            style={{
              padding: '9px 12px',
              borderRadius: '8px',
              background: 'var(--bg-input)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-main)',
              fontSize: '0.85rem',
              flex: '1 1 150px',
            }}
          >
            <option value="All">All Categories</option>
            {filterType === 'expense' &&
              EXPENSE_CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            {filterType === 'income' &&
              INCOME_CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            {filterType === 'all' && (
              <>
                <optgroup label="Income Categories">
                  {INCOME_CATEGORIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </optgroup>
                <optgroup label="Expense Categories">
                  {EXPENSE_CATEGORIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </optgroup>
              </>
            )}
          </select>

          <select
            value={filterType}
            onChange={(e) => {
              const newType = e.target.value;
              setFilterType(newType);
              if (newType === 'expense' && !EXPENSE_CATEGORIES.includes(filterCategory)) {
                setFilterCategory('All');
              } else if (newType === 'income' && !INCOME_CATEGORIES.includes(filterCategory)) {
                setFilterCategory('All');
              }
            }}
            style={{
              padding: '9px 12px',
              borderRadius: '8px',
              background: 'var(--bg-input)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-main)',
              fontSize: '0.85rem',
              flex: '1 1 130px',
            }}
          >
            <option value="all">All Types</option>
            <option value="expense">Expenses Only</option>
            <option value="income">Income Only</option>
          </select>
        </div>

        <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
          Showing <strong>{filteredTransactions.length}</strong> record{filteredTransactions.length === 1 ? '' : 's'}
        </div>
      </div>

      {/* Transactions Container: Desktop Table + Mobile Cards */}
      <div className="glass-card" style={{ padding: 'clamp(14px, 2.5vw, 20px)', overflowX: 'auto' }}>
        {filteredTransactions.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '48px 20px', color: 'var(--text-muted)' }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '10px' }}>💳</div>
            <h4 style={{ color: 'var(--text-main)', fontSize: '1.05rem', marginBottom: '4px' }}>No Transactions Found</h4>
            <p style={{ fontSize: '0.85rem' }}>Try clearing filters or add a new transaction above.</p>
          </div>
        ) : (
          <>
            {/* Desktop Table View */}
            <table className="table-desktop-view" style={{ borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                  <th style={{ padding: '12px 14px', fontWeight: 600 }}>Date</th>
                  <th style={{ padding: '12px 14px', fontWeight: 600 }}>Category</th>
                  <th style={{ padding: '12px 14px', fontWeight: 600 }}>Description</th>
                  <th style={{ padding: '12px 14px', fontWeight: 600 }}>Type</th>
                  <th style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 600 }}>Amount ({currency})</th>
                  <th style={{ padding: '12px 14px', textAlign: 'center', width: '60px' }}></th>
                </tr>
              </thead>
              <tbody>
                {filteredTransactions.map((tx) => (
                  <tr
                    key={tx.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      transition: 'background 0.15s ease',
                    }}
                  >
                    <td style={{ padding: '14px 14px', color: 'var(--text-muted)', fontSize: '0.83rem', whiteSpace: 'nowrap' }}>
                      {tx.date}
                    </td>
                    <td style={{ padding: '14px 14px', fontWeight: 600, color: 'var(--text-main)' }}>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '1rem' }}>{getCategoryIcon(tx.category, tx.type)}</span>
                        <span>{tx.category}</span>
                      </div>
                    </td>
                    <td style={{ padding: '14px 14px', color: 'var(--text-secondary)' }}>
                      {tx.description || <span style={{ color: 'var(--text-dim)' }}>—</span>}
                    </td>
                    <td style={{ padding: '14px 14px' }}>
                      <span
                        style={{
                          padding: '3px 8px',
                          borderRadius: '6px',
                          fontSize: '0.73rem',
                          fontWeight: 600,
                          background: tx.type === 'income' ? 'var(--accent-emerald-subtle)' : 'var(--accent-rose-subtle)',
                          color: tx.type === 'income' ? 'var(--accent-emerald)' : 'var(--accent-rose)',
                          textTransform: 'uppercase',
                          letterSpacing: '0.04em',
                        }}
                      >
                        {tx.type}
                      </span>
                    </td>
                    <td
                      style={{
                        padding: '14px 14px',
                        textAlign: 'right',
                        fontWeight: 700,
                        fontSize: '0.92rem',
                        color: tx.type === 'income' ? 'var(--accent-emerald)' : 'var(--text-main)',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {tx.type === 'income' ? '+' : '-'} {tx.amount.toLocaleString()}
                    </td>
                    <td style={{ padding: '14px 14px', textAlign: 'center' }}>
                      {/* Unobtrusive Contextual Menu Trigger (replaces permanent pencil and trash icons) */}
                      <div className="context-menu-wrapper">
                        <button
                          type="button"
                          className={`context-menu-trigger ${activeMenuTxId === tx.id ? 'active' : ''}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setActiveMenuTxId(activeMenuTxId === tx.id ? null : tx.id);
                          }}
                          aria-label={`Options for transaction #${tx.id}`}
                          title="More options"
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <circle cx="12" cy="12" r="1.5" />
                            <circle cx="12" cy="5" r="1.5" />
                            <circle cx="12" cy="19" r="1.5" />
                          </svg>
                        </button>

                        {activeMenuTxId === tx.id && (
                          <div className="context-menu-dropdown">
                            <button
                              type="button"
                              className="context-menu-item"
                              onClick={() => handleOpenEdit(tx)}
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M12 20h9" />
                                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                              </svg>
                              Edit
                            </button>
                            <button
                              type="button"
                              className="context-menu-item danger"
                              onClick={() => handleDelete(tx.id)}
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <polyline points="3 6 5 6 21 6" />
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                              </svg>
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Mobile Cards View */}
            <div className="cards-mobile-view">
              {filteredTransactions.map((tx) => (
                <div
                  key={tx.id}
                  style={{
                    background: 'var(--bg-hover-subtle)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '12px',
                    padding: '14px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '10px',
                    position: 'relative',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span
                        style={{
                          width: '36px',
                          height: '36px',
                          borderRadius: '10px',
                          background: tx.type === 'income' ? 'var(--accent-emerald-subtle)' : 'var(--accent-rose-subtle)',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '1.1rem',
                        }}
                      >
                        {getCategoryIcon(tx.category, tx.type)}
                      </span>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-main)' }}>
                          {tx.category}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {tx.date}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div style={{ textAlign: 'right' }}>
                        <div
                          style={{
                            fontWeight: 800,
                            fontSize: '1.05rem',
                            color: tx.type === 'income' ? 'var(--accent-emerald)' : 'var(--text-main)',
                          }}
                        >
                          {tx.type === 'income' ? '+' : '-'} {currency} {tx.amount.toLocaleString()}
                        </div>
                        <span
                          style={{
                            fontSize: '0.7rem',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            background: tx.type === 'income' ? 'var(--accent-emerald-subtle)' : 'var(--accent-rose-subtle)',
                            color: tx.type === 'income' ? 'var(--accent-emerald)' : 'var(--accent-rose)',
                            textTransform: 'uppercase',
                            fontWeight: 600,
                          }}
                        >
                          {tx.type}
                        </span>
                      </div>

                      {/* Contextual menu for mobile */}
                      <div className="context-menu-wrapper">
                        <button
                          type="button"
                          className={`context-menu-trigger ${activeMenuTxId === tx.id ? 'active' : ''}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setActiveMenuTxId(activeMenuTxId === tx.id ? null : tx.id);
                          }}
                          aria-label={`Options for transaction #${tx.id}`}
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <circle cx="12" cy="12" r="1.5" />
                            <circle cx="12" cy="5" r="1.5" />
                            <circle cx="12" cy="19" r="1.5" />
                          </svg>
                        </button>

                        {activeMenuTxId === tx.id && (
                          <div className="context-menu-dropdown">
                            <button
                              type="button"
                              className="context-menu-item"
                              onClick={() => handleOpenEdit(tx)}
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M12 20h9" />
                                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                              </svg>
                              Edit
                            </button>
                            <button
                              type="button"
                              className="context-menu-item danger"
                              onClick={() => handleDelete(tx.id)}
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <polyline points="3 6 5 6 21 6" />
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                              </svg>
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {tx.description && (
                    <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', paddingLeft: '46px' }}>
                      {tx.description}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Modal for Add / Edit Transaction */}
      {showModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(5, 8, 16, 0.65)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
          onClick={() => setShowModal(false)}
        >
          <div
            className="glass-card responsive-modal-content"
            style={{
              width: '100%',
              maxWidth: '480px',
              padding: '28px',
              background: 'var(--bg-modal)',
              border: '1px solid var(--border-medium)',
              boxShadow: 'var(--shadow-lg)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)' }}>
                {editingTx ? 'Edit Transaction' : formType === 'income' ? 'Record Income' : 'Record Expense'}
              </h3>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  fontSize: '1.2rem',
                  lineHeight: 1,
                }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Type Switcher */}
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Transaction Type
                </label>
                <div style={{ display: 'flex', gap: '8px', background: 'var(--bg-hover-subtle)', padding: '4px', borderRadius: '10px' }}>
                  <button
                    type="button"
                    onClick={() => handleTypeChange('expense')}
                    style={{
                      flex: 1,
                      padding: '8px',
                      borderRadius: '8px',
                      border: 'none',
                      background: formType === 'expense' ? 'var(--primary-blue)' : 'transparent',
                      color: formType === 'expense' ? '#ffffff' : 'var(--text-muted)',
                      fontWeight: 600,
                      fontSize: '0.85rem',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                  >
                    Expense
                  </button>
                  <button
                    type="button"
                    onClick={() => handleTypeChange('income')}
                    style={{
                      flex: 1,
                      padding: '8px',
                      borderRadius: '8px',
                      border: 'none',
                      background: formType === 'income' ? 'var(--primary-blue)' : 'transparent',
                      color: formType === 'income' ? '#ffffff' : 'var(--text-muted)',
                      fontWeight: 600,
                      fontSize: '0.85rem',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                  >
                    Income
                  </button>
                </div>
              </div>

              {/* Amount */}
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Amount ({currency}) *
                </label>
                <input
                  type="number"
                  step="0.01"
                  required
                  placeholder="0.00"
                  value={formAmount}
                  onChange={(e) => setFormAmount(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    fontSize: '1.1rem',
                    fontWeight: 700,
                  }}
                />
              </div>

              {/* Category */}
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Category *
                </label>
                <select
                  value={formCategory}
                  onChange={(e) => setFormCategory(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    fontSize: '0.9rem',
                  }}
                >
                  {formType === 'income'
                    ? INCOME_CATEGORIES.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))
                    : EXPENSE_CATEGORIES.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                </select>
              </div>

              {/* Date */}
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Date *
                </label>
                <input
                  type="date"
                  required
                  value={formDate}
                  onChange={(e) => setFormDate(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    fontSize: '0.9rem',
                  }}
                />
              </div>

              {/* Description */}
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Description / Note
                </label>
                <input
                  type="text"
                  placeholder="e.g. Dinner with clients, grocery run..."
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    fontSize: '0.9rem',
                  }}
                />
              </div>

              {/* Submit Buttons */}
              <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="btn-secondary"
                  style={{ flex: 1 }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="btn-primary"
                  style={{ flex: 1 }}
                >
                  {isSubmitting ? 'Saving...' : editingTx ? 'Save Changes' : 'Record Transaction'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
