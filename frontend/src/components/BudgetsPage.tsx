import React, { useState } from 'react';
import { Budget, SavingsGoal, api } from '../api';

interface BudgetsPageProps {
  budgets: Budget[];
  goals: SavingsGoal[];
  onRefresh: () => void;
  currency?: string;
}

export const BudgetsPage: React.FC<BudgetsPageProps> = ({
  budgets,
  goals,
  onRefresh,
  currency = 'PKR',
}) => {
  const [showBudgetModal, setShowBudgetModal] = useState(false);
  const [showGoalModal, setShowGoalModal] = useState(false);

  // Budget form
  const [bCategory, setBCategory] = useState('Food');
  const [bLimit, setBLimit] = useState('');

  // Goal form
  const [gTitle, setGTitle] = useState('');
  const [gTarget, setGTarget] = useState('');
  const [gCurrent, setGCurrent] = useState('');

  const currentMonth = new Date().toISOString().slice(0, 7);

  const handleCreateBudget = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bLimit || isNaN(Number(bLimit))) return;

    try {
      await api.createBudget({
        category: bCategory,
        monthly_limit: Number(bLimit),
        month: currentMonth,
      });
      setShowBudgetModal(false);
      setBLimit('');
      onRefresh();
    } catch (err: any) {
      alert(err.message || 'Error creating budget');
    }
  };

  const handleDeleteBudget = async (id: number) => {
    if (window.confirm('Delete this budget limit?')) {
      try {
        await api.deleteBudget(id);
        onRefresh();
      } catch (err: any) {
        alert(err.message || 'Error deleting budget');
      }
    }
  };

  const handleCreateGoal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!gTitle || !gTarget || isNaN(Number(gTarget))) return;

    try {
      await api.createGoal({
        title: gTitle,
        target_amount: Number(gTarget),
        current_amount: gCurrent ? Number(gCurrent) : 0,
      });
      setShowGoalModal(false);
      setGTitle('');
      setGTarget('');
      setGCurrent('');
      onRefresh();
    } catch (err: any) {
      alert(err.message || 'Error creating savings goal');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      {/* Monthly Budgets Section */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)' }}>Monthly Budgets ({currentMonth})</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Set category limits with automated visual alerts at 80% and 100% capacity.</p>
          </div>
          <button onClick={() => setShowBudgetModal(true)} className="btn-primary" style={{ padding: '8px 16px', fontSize: '0.85rem' }}>
            + Set Budget
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' }}>
          {budgets.map((b) => {
            const isDanger = b.status === 'danger' || b.utilization_percentage >= 100;
            const isWarning = b.status === 'warning' || (b.utilization_percentage >= 80 && !isDanger);
            const statusColor = isDanger ? 'var(--accent-rose)' : isWarning ? 'var(--accent-amber)' : 'var(--accent-emerald)';

            return (
              <div key={b.id} className="glass-card" style={{ padding: '20px', position: 'relative' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                  <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-main)' }}>{b.category}</div>
                  <button
                    onClick={() => handleDeleteBudget(b.id)}
                    style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: '0.9rem' }}
                    title="Remove budget"
                  >
                    ✕
                  </button>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '10px' }}>
                  <span>Spent: {currency} {b.spent.toLocaleString()}</span>
                  <span>Limit: {currency} {b.monthly_limit.toLocaleString()}</span>
                </div>

                {/* Progress bar */}
                <div style={{ height: '8px', background: 'var(--border-subtle)', borderRadius: '4px', overflow: 'hidden', marginBottom: '10px' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${Math.min(b.utilization_percentage, 100)}%`,
                      backgroundColor: statusColor,
                      transition: 'width 0.4s ease',
                    }}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 700, color: statusColor }}>
                    {b.utilization_percentage.toFixed(1)}% Used
                  </span>
                  {isDanger && (
                    <span style={{ fontSize: '0.75rem', color: 'var(--accent-rose)', background: 'var(--accent-rose-subtle)', padding: '2px 8px', borderRadius: '4px', fontWeight: 600 }}>
                      ⚠️ Budget Exceeded
                    </span>
                  )}
                  {isWarning && (
                    <span style={{ fontSize: '0.75rem', color: 'var(--accent-amber)', background: 'var(--accent-amber-subtle)', padding: '2px 8px', borderRadius: '4px', fontWeight: 600 }}>
                      ⚡ 80% Warning
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Savings Goals Section */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)' }}>Savings Goals</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Track long-term milestones and personal financial targets.</p>
          </div>
          <button onClick={() => setShowGoalModal(true)} className="btn-secondary" style={{ padding: '8px 16px', fontSize: '0.85rem' }}>
            + New Goal
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' }}>
          {goals.map((g) => (
            <div key={g.id} className="glass-card" style={{ padding: '20px' }}>
              <div style={{ fontWeight: 700, fontSize: '1.05rem', color: 'var(--text-main)', marginBottom: '8px' }}>
                🎯 {g.title}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '10px' }}>
                <span>Saved: {currency} {g.current_amount.toLocaleString()}</span>
                <span>Target: {currency} {g.target_amount.toLocaleString()}</span>
              </div>

              {/* Progress bar */}
              <div style={{ height: '8px', background: 'var(--border-subtle)', borderRadius: '4px', overflow: 'hidden', marginBottom: '10px' }}>
                <div
                  style={{
                    height: '100%',
                    width: `${Math.min(g.progress_percentage, 100)}%`,
                    background: 'linear-gradient(90deg, var(--primary-blue), var(--accent-emerald))',
                    transition: 'width 0.4s ease',
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--accent-emerald)' }}>
                  {g.progress_percentage.toFixed(1)}% Achieved
                </span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Remaining: {currency} {(g.target_amount - g.current_amount).toLocaleString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Create Budget Modal */}
      {showBudgetModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div className="glass-card responsive-modal-content" style={{ width: '100%', maxWidth: '400px', padding: '28px', background: 'var(--bg-modal)', border: '1px solid var(--border-medium)', boxShadow: 'var(--shadow-lg)' }}>
            <h3 style={{ marginBottom: '16px', color: 'var(--text-main)', fontSize: '1.2rem', fontWeight: 700 }}>Set Monthly Category Budget</h3>
            <form onSubmit={handleCreateBudget} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>Category</label>
                <select
                  value={bCategory}
                  onChange={(e) => setBCategory(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', background: 'var(--bg-input)', border: '1px solid var(--border-subtle)', color: 'var(--text-main)' }}
                >
                  <option value="Overall">Overall Spending</option>
                  <option value="Food">Food & Dining</option>
                  <option value="Travel">Travel & Commute</option>
                  <option value="Education">Education</option>
                  <option value="Medicine">Medicine & Health</option>
                  <option value="Fruit">Fruit & Groceries</option>
                  <option value="Friends">Friends & Social</option>
                  <option value="Rent">Rent & Housing</option>
                  <option value="Utilities">Utilities & Bills</option>
                  <option value="Shopping">Shopping</option>
                  <option value="Entertainment">Entertainment</option>
                  <option value="Other">Other Expenses</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>Monthly Limit ({currency})</label>
                <input
                  type="number"
                  required
                  placeholder="e.g. 20000"
                  value={bLimit}
                  onChange={(e) => setBLimit(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', background: 'var(--bg-input)', border: '1px solid var(--border-subtle)', color: 'var(--text-main)' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
                <button type="button" onClick={() => setShowBudgetModal(false)} className="btn-secondary" style={{ flex: 1 }}>Cancel</button>
                <button type="submit" className="btn-primary" style={{ flex: 1 }}>Save Budget</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Goal Modal */}
      {showGoalModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div className="glass-card responsive-modal-content" style={{ width: '100%', maxWidth: '400px', padding: '28px', background: 'var(--bg-modal)', border: '1px solid var(--border-medium)', boxShadow: 'var(--shadow-lg)' }}>
            <h3 style={{ marginBottom: '16px', color: 'var(--text-main)', fontSize: '1.2rem', fontWeight: 700 }}>Create Savings Goal</h3>
            <form onSubmit={handleCreateGoal} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>Goal Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. New Laptop or Emergency Fund"
                  value={gTitle}
                  onChange={(e) => setGTitle(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', background: 'var(--bg-input)', border: '1px solid var(--border-subtle)', color: 'var(--text-main)' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>Target Amount ({currency})</label>
                <input
                  type="number"
                  required
                  placeholder="e.g. 80000"
                  value={gTarget}
                  onChange={(e) => setGTarget(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', background: 'var(--bg-input)', border: '1px solid var(--border-subtle)', color: 'var(--text-main)' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>Current Saved ({currency})</label>
                <input
                  type="number"
                  placeholder="e.g. 15000"
                  value={gCurrent}
                  onChange={(e) => setGCurrent(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', background: 'var(--bg-input)', border: '1px solid var(--border-subtle)', color: 'var(--text-main)' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
                <button type="button" onClick={() => setShowGoalModal(false)} className="btn-secondary" style={{ flex: 1 }}>Cancel</button>
                <button type="submit" className="btn-primary" style={{ flex: 1 }}>Create Goal</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
