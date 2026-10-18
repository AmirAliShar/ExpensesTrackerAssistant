import React, { useState, useEffect } from 'react';
import {
  api,
  User,
  AnalyticsSummary,
  Transaction,
  Budget,
  SavingsGoal,
  Memory,
  AuthResponse
} from './api';
import { ExpensePieChart } from './components/ExpensePieChart';
import { AIAssistant } from './components/AIAssistant';
import { TransactionsPage } from './components/TransactionsPage';
import { BudgetsPage } from './components/BudgetsPage';
import { SettingsPage } from './components/SettingsPage';
import { AuthModal } from './components/AuthModal';

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'transactions' | 'assistant' | 'budgets' | 'settings'>('dashboard');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Theme state with localStorage persistence and system theme detection
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  // App data state
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [currency, setCurrency] = useState('PKR');
  const [selectedMonth, setSelectedMonth] = useState('');
  const [loading, setLoading] = useState(false);

  // Apply theme to document root whenever it changes
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  // Generate selectable months dynamically from current date + recorded transactions
  const availableMonths = React.useMemo(() => {
    const monthsSet = new Set<string>();
    const now = new Date();
    for (let i = 0; i < 6; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const mStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      monthsSet.add(mStr);
    }
    transactions.forEach((t) => {
      if (t.date && t.date.length >= 7) {
        monthsSet.add(t.date.slice(0, 7));
      }
    });
    return Array.from(monthsSet).sort().reverse();
  }, [transactions]);

  const formatMonthLabel = (mStr: string) => {
    try {
      const [y, m] = mStr.split('-');
      const date = new Date(parseInt(y, 10), parseInt(m, 10) - 1, 1);
      return date.toLocaleString('default', { month: 'long', year: 'numeric' });
    } catch {
      return mStr;
    }
  };

  const loadAllData = async (monthFilter = selectedMonth) => {
    setLoading(true);
    try {
      const [analyticsData, txData, budgetData, goalsData, memData] = await Promise.allSettled([
        api.getAnalytics({ month: monthFilter || undefined }),
        api.getTransactions({ month: monthFilter || undefined, limit: 100 }),
        api.getBudgets(monthFilter || undefined),
        api.getGoals(),
        api.getMemories(),
      ]);

      if (analyticsData.status === 'fulfilled') setAnalytics(analyticsData.value);
      if (txData.status === 'fulfilled') setTransactions(txData.value);
      if (budgetData.status === 'fulfilled') setBudgets(budgetData.value);
      if (goalsData.status === 'fulfilled') setGoals(goalsData.value);
      if (memData.status === 'fulfilled') setMemories(memData.value);
    } catch (e) {
      console.error('Error fetching data:', e);
    } finally {
      setLoading(false);
    }
  };

  // Re-fetch data on tab switch
  useEffect(() => {
    loadAllData();
  }, [activeTab]);

  // Load user session on mount
  useEffect(() => {
    const token = api.getToken();
    if (token) {
      api.getMe()
        .then((u) => {
          setUser(u);
          setCurrency(u.preferred_currency || 'PKR');
        })
        .catch(() => {
          api.logout();
        })
        .finally(() => {
          loadAllData();
        });
    } else {
      loadAllData();
    }
  }, []);

  const handleAuthSuccess = (data: AuthResponse) => {
    setUser(data.user);
    setCurrency(data.user.preferred_currency || 'PKR');
    setShowAuthModal(false);
    loadAllData();
  };

  const handleLogout = () => {
    api.logout();
    setUser(null);
    loadAllData();
  };

  const handleMonthChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newMonth = e.target.value;
    setSelectedMonth(newMonth);
    loadAllData(newMonth);
  };

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'transactions', label: 'Transactions', icon: '💳' },
    { id: 'assistant', label: 'AI Assistant', icon: '⚡' },
    { id: 'budgets', label: 'Budgets & Goals', icon: '🎯' },
    { id: 'settings', label: 'Settings', icon: '⚙️' },
  ];

  return (
    <div style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', position: 'relative' }}>
      {/* Background ambient lighting */}
      <div className="ambient-glow glow-1" />
      <div className="ambient-glow glow-2" />

      {/* Sticky Top Navigation Bar */}
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 40,
          background: 'var(--bg-nav)',
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          borderBottom: '1px solid var(--border-subtle)',
          boxShadow: 'var(--shadow-sm)',
          padding: '12px clamp(14px, 3vw, 28px)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        {/* App Branding */}
        <div
          onClick={() => setActiveTab('dashboard')}
          style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}
        >
          <div
            style={{
              width: '38px',
              height: '38px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, var(--primary-blue), var(--hover-blue))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '1.2rem',
              color: '#ffffff',
              boxShadow: '0 4px 14px var(--glow-blue)',
              flexShrink: 0,
            }}
          >
            💸
          </div>
          <div>
            <h1 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-main)', letterSpacing: '-0.02em', lineHeight: 1.2 }}>
              AI Expense Tracker
            </h1>
            <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Agentic Personal Finance Assistant</p>
          </div>
        </div>

        {/* Desktop Navigation Tabs */}
        <nav
          className="desktop-only"
          style={{
            gap: '4px',
            background: 'var(--bg-hover-subtle)',
            padding: '4px',
            borderRadius: '12px',
            border: '1px solid var(--border-subtle)',
          }}
        >
          {navItems.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              style={{
                padding: '8px 14px',
                borderRadius: '8px',
                border: 'none',
                background: activeTab === tab.id ? 'var(--primary-blue)' : 'transparent',
                color: activeTab === tab.id ? '#ffffff' : 'var(--text-muted)',
                fontWeight: activeTab === tab.id ? 700 : 500,
                fontSize: '0.82rem',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                boxShadow: activeTab === tab.id ? '0 2px 8px var(--glow-blue)' : 'none',
              }}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>

        {/* Right Section: Theme Toggle, User Account & Mobile Hamburger */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Theme Toggle Button (Light/Dark mode) */}
          <button
            onClick={toggleTheme}
            className="theme-toggle-btn"
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>

          {/* Desktop User Account Controls */}
          <div className="desktop-only" style={{ alignItems: 'center', gap: '10px' }}>
            {user ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-main)' }}>{user.full_name || user.email}</div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--accent-emerald)', fontWeight: 600 }}>Authenticated</div>
                </div>
                <button onClick={handleLogout} className="btn-secondary" style={{ padding: '6px 12px', fontSize: '0.78rem', minHeight: '34px' }}>
                  Sign Out
                </button>
              </div>
            ) : (
              <button onClick={() => setShowAuthModal(true)} className="btn-primary" style={{ padding: '6px 14px', fontSize: '0.82rem', minHeight: '36px' }}>
                Sign In
              </button>
            )}
          </div>

          {/* Mobile Menu Toggle Button */}
          <button
            className="mobile-only"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            style={{
              width: '38px',
              height: '38px',
              borderRadius: '8px',
              background: 'var(--bg-hover-subtle)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-main)',
              fontSize: '1.2rem',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
            }}
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? '✕' : '☰'}
          </button>
        </div>
      </header>

      {/* Mobile Drawer Dropdown Menu */}
      {mobileMenuOpen && (
        <div
          className="mobile-only"
          style={{
            position: 'fixed',
            top: '64px',
            left: 0,
            right: 0,
            background: 'var(--bg-modal)',
            backdropFilter: 'blur(20px)',
            borderBottom: '1px solid var(--border-subtle)',
            padding: '16px',
            zIndex: 49,
            flexDirection: 'column',
            gap: '8px',
            boxShadow: 'var(--shadow-dropdown)',
          }}
        >
          {navItems.map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id as any);
                setMobileMenuOpen(false);
              }}
              style={{
                width: '100%',
                padding: '12px 16px',
                borderRadius: '10px',
                border: 'none',
                background: activeTab === tab.id ? 'var(--primary-blue)' : 'var(--bg-hover-subtle)',
                color: activeTab === tab.id ? '#ffffff' : 'var(--text-main)',
                fontWeight: activeTab === tab.id ? 700 : 500,
                fontSize: '0.95rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                minHeight: '44px',
              }}
            >
              <span style={{ fontSize: '1.1rem' }}>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}

          <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid var(--border-subtle)' }}>
            {user ? (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{user.email}</span>
                <button
                  onClick={() => {
                    handleLogout();
                    setMobileMenuOpen(false);
                  }}
                  className="btn-secondary"
                  style={{ padding: '6px 12px', fontSize: '0.8rem', minHeight: '36px' }}
                >
                  Sign Out
                </button>
              </div>
            ) : (
              <button
                onClick={() => {
                  setShowAuthModal(true);
                  setMobileMenuOpen(false);
                }}
                className="btn-primary"
                style={{ width: '100%', minHeight: '44px' }}
              >
                Sign In / Register
              </button>
            )}
          </div>
        </div>
      )}

      {/* Main Content Body */}
      <main
        style={{
          flex: 1,
          padding: 'clamp(14px, 3vw, 28px)',
          maxWidth: '1400px',
          margin: '0 auto',
          width: '100%',
          paddingBottom: 'clamp(30px, 8vh, 50px)',
          zIndex: 1,
        }}
      >
        {/* TAB 1: DASHBOARD */}
        {activeTab === 'dashboard' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
            {/* Filter Bar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <h2 style={{ fontSize: 'clamp(1.3rem, 3vw, 1.6rem)', fontWeight: 800, color: 'var(--text-main)' }}>Financial Overview</h2>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                  Live metrics, PostgreSQL data, and category-level expense distributions.
                </p>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <select
                  value={selectedMonth}
                  onChange={handleMonthChange}
                  style={{
                    padding: '8px 12px',
                    borderRadius: '8px',
                    background: 'var(--bg-input)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-main)',
                    fontSize: '0.85rem',
                    minHeight: '38px',
                  }}
                >
                  <option value="">All Time</option>
                  {availableMonths.map((m) => (
                    <option key={m} value={m}>
                      {formatMonthLabel(m)}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => loadAllData()}
                  className="btn-secondary"
                  style={{ padding: '8px 12px', fontSize: '0.82rem', minHeight: '38px' }}
                  disabled={loading}
                >
                  {loading ? '⏳ Loading...' : '🔄 Refresh'}
                </button>
              </div>
            </div>

            {/* 4 Summary Stat Metric Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))', gap: '16px' }}>
              <div className="glass-card" style={{ padding: '20px' }}>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px', fontWeight: 600 }}>
                  Total Income
                </div>
                <div style={{ fontSize: 'clamp(1.4rem, 3.5vw, 1.8rem)', fontWeight: 800, color: 'var(--accent-emerald)' }}>
                  {currency} {analytics?.total_income.toLocaleString() || '0'}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: '4px' }}>
                  Deposited & verified earnings
                </div>
              </div>

              <div className="glass-card" style={{ padding: '20px' }}>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px', fontWeight: 600 }}>
                  Total Expenses
                </div>
                <div style={{ fontSize: 'clamp(1.4rem, 3.5vw, 1.8rem)', fontWeight: 800, color: 'var(--accent-rose)' }}>
                  {currency} {analytics?.total_expenses.toLocaleString() || '0'}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: '4px' }}>
                  Categorized outflows
                </div>
              </div>

              <div className="glass-card" style={{ padding: '20px' }}>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px', fontWeight: 600 }}>
                  Available Balance
                </div>
                <div style={{ fontSize: 'clamp(1.4rem, 3.5vw, 1.8rem)', fontWeight: 800, color: 'var(--accent-blue-text)' }}>
                  {currency} {analytics?.net_savings.toLocaleString() || '0'}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: '4px' }}>
                  Net cash flow
                </div>
              </div>

              <div className="glass-card" style={{ padding: '20px' }}>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px', fontWeight: 600 }}>
                  Savings Rate
                </div>
                <div style={{ fontSize: 'clamp(1.4rem, 3.5vw, 1.8rem)', fontWeight: 800, color: 'var(--accent-blue-text)' }}>
                  {analytics?.savings_rate || 0}%
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: '4px' }}>
                  {(analytics?.savings_rate || 0) >= 20 ? '✨ Healthy financial ratio' : '📈 Opportunity to optimize'}
                </div>
              </div>
            </div>

            {/* MANDATORY FEATURE: Expense Category Breakdown Pie Chart */}
            <div className="glass-card" style={{ padding: 'clamp(16px, 3vw, 24px)', overflowX: 'hidden' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-main)' }}>
                    Expense Breakdown by Category
                  </h3>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Calculated deterministically: <code style={{ color: 'var(--accent-blue-text)' }}>Category Expenses / Total Expenses × 100</code>
                  </p>
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--accent-emerald)', background: 'var(--accent-emerald-subtle)', padding: '4px 10px', borderRadius: '6px', fontWeight: 600 }}>
                  PostgreSQL Verified
                </span>
              </div>

              <ExpensePieChart
                categories={analytics?.categories || []}
                totalExpenses={analytics?.total_expenses || 0}
                currency={currency}
              />
            </div>

            {/* Recent Transactions Activity List (Uncluttered, No Permanent Edit/Delete Icons) */}
            <div className="glass-card" style={{ padding: 'clamp(16px, 3vw, 22px)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-main)' }}>Recent Activity</h3>
                <button
                  onClick={() => setActiveTab('transactions')}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--accent-blue-text)',
                    cursor: 'pointer',
                    fontSize: '0.82rem',
                    fontWeight: 600,
                  }}
                >
                  View All →
                </button>
              </div>

              {transactions.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  No recent activity recorded yet.
                </div>
              ) : (
                transactions.slice(0, 5).map((t) => (
                  <div
                    key={t.id}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '12px 0',
                      borderBottom: '1px solid var(--border-subtle)',
                      gap: '8px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                      <div
                        style={{
                          width: '36px',
                          height: '36px',
                          borderRadius: '10px',
                          background: t.type === 'income' ? 'var(--accent-emerald-subtle)' : 'var(--accent-rose-subtle)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '1rem',
                          flexShrink: 0,
                        }}
                      >
                        {t.type === 'income' ? '📈' : '📉'}
                      </div>
                      <div style={{ minWidth: 0, overflow: 'hidden' }}>
                        <div style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '0.88rem', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                          {t.category}
                        </div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                          {t.description || t.date}
                        </div>
                      </div>
                    </div>

                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      <div style={{ fontWeight: 700, color: t.type === 'income' ? 'var(--accent-emerald)' : 'var(--text-main)', fontSize: '0.92rem' }}>
                        {t.type === 'income' ? '+' : '-'} {currency} {t.amount.toLocaleString()}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>{t.date}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* TAB 2: TRANSACTIONS */}
        {activeTab === 'transactions' && (
          <TransactionsPage
            transactions={transactions}
            onRefresh={() => loadAllData()}
            currency={currency}
          />
        )}

        {/* TAB 3: AI ASSISTANT & VOICE */}
        {activeTab === 'assistant' && (
          <AIAssistant onDataChanged={() => loadAllData()} />
        )}

        {/* TAB 4: BUDGETS & SAVINGS GOALS */}
        {activeTab === 'budgets' && (
          <BudgetsPage
            budgets={budgets}
            goals={goals}
            onRefresh={() => loadAllData()}
            currency={currency}
          />
        )}

        {/* TAB 5: SETTINGS & LONG-TERM MEMORY */}
        {activeTab === 'settings' && (
          <SettingsPage
            memories={memories}
            onRefreshMemories={() => loadAllData()}
            currency={currency}
            onCurrencyChange={(c) => setCurrency(c)}
            userEmail={user?.email || 'demo@antigravity.io'}
          />
        )}
      </main>

      {/* Auth Modal */}
      {showAuthModal && (
        <AuthModal onSuccess={handleAuthSuccess} />
      )}
    </div>
  );
}

export default App;
