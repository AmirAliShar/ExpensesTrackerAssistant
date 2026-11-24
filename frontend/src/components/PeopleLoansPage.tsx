import React, { useEffect, useMemo, useState } from 'react';
import { api, LoanHistory, LoanSummary, PersonalLoan } from '../api';

interface PeopleLoansPageProps {
  currency: string;
}

const amountValue = (value: string | number) => Number(value);
const localDate = () => new Date().toISOString().slice(0, 10);

export const PeopleLoansPage: React.FC<PeopleLoansPageProps> = ({ currency }) => {
  const [summary, setSummary] = useState<LoanSummary | null>(null);
  const [loans, setLoans] = useState<PersonalLoan[]>([]);
  const [filter, setFilter] = useState<'all' | 'outstanding' | 'settled'>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [personName, setPersonName] = useState('');
  const [loanType, setLoanType] = useState<'lent' | 'borrowed'>('lent');
  const [loanAmount, setLoanAmount] = useState('');
  const [loanDate, setLoanDate] = useState(localDate());
  const [dueDate, setDueDate] = useState('');
  const [loanDescription, setLoanDescription] = useState('');
  const [repaymentAmounts, setRepaymentAmounts] = useState<Record<number, string>>({});
  const [repaymentKeys, setRepaymentKeys] = useState<Record<number, string>>({});
  const [history, setHistory] = useState<LoanHistory | null>(null);

  const refresh = async () => {
    try {
      const [summaryData, loanData] = await Promise.all([api.getLoanSummary(), api.getLoans({ limit: 500 })]);
      setSummary(summaryData);
      setLoans(loanData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load people and loan records.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const visibleLoans = useMemo(() => loans.filter((loan) => {
    if (filter === 'outstanding') return loan.status !== 'settled';
    if (filter === 'settled') return loan.status === 'settled';
    return true;
  }), [filter, loans]);

  const formatMoney = (value: string | number) => (
    `${currency} ${amountValue(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  );

  const handleCreateLoan = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    const parsedAmount = Number(loanAmount);
    if (!personName.trim() || !Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setError('Enter a person name and a valid positive amount.');
      return;
    }
    const confirmation = `${loanType === 'lent' ? 'Lend to' : 'Borrow from'} ${personName.trim()} ${formatMoney(loanAmount)}?`;
    if (!window.confirm(`Confirm loan record\n\n${confirmation}\n\nThis will not be recorded as income or an expense.`)) return;

    try {
      await api.createLoan({
        person_name: personName.trim(),
        loan_type: loanType,
        original_amount: loanAmount,
        transaction_date: loanDate,
        due_date: dueDate || undefined,
        description: loanDescription.trim() || undefined,
      });
      setPersonName('');
      setLoanAmount('');
      setDueDate('');
      setLoanDescription('');
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to record the loan.');
    }
  };

  const handleRepayment = async (loan: PersonalLoan) => {
    setError('');
    const amount = (repaymentAmounts[loan.id] || '').trim();
    const parsedAmount = Number(amount);
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setError('Enter a valid positive repayment amount.');
      return;
    }
    if (!window.confirm(`Confirm repayment of ${formatMoney(amount)} for ${loan.person_name} (loan #${loan.id})?`)) return;
    const storageKey = `pending-loan-repayment:${loan.id}`;
    const key = repaymentKeys[loan.id] || sessionStorage.getItem(storageKey) || crypto.randomUUID();
    setRepaymentKeys((current) => ({ ...current, [loan.id]: key }));
    sessionStorage.setItem(storageKey, key);
    try {
      await api.recordLoanRepayment(loan.id, {
        amount,
        repayment_date: localDate(),
        description: 'Recorded from People & Loans',
        idempotency_key: key,
      });
      setRepaymentAmounts((current) => ({ ...current, [loan.id]: '' }));
      setRepaymentKeys((current) => {
        const next = { ...current };
        delete next[loan.id];
        return next;
      });
      sessionStorage.removeItem(storageKey);
      await refresh();
      if (history?.loan.id === loan.id) setHistory(await api.getLoanHistory(loan.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to record the repayment.');
    }
  };

  const showHistory = async (loan: PersonalLoan) => {
    setError('');
    try {
      setHistory(await api.getLoanHistory(loan.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load repayment history.');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
      <div>
        <h2 style={{ color: 'var(--text-main)', fontSize: '1.5rem', fontWeight: 800 }}>People &amp; Loans</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          Track personal receivables and repayments separately from income and expenses.
        </p>
      </div>

      {error && (
        <div role="alert" className="glass-card" style={{ padding: '12px 16px', color: 'var(--accent-rose)' }}>
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '14px' }}>
        {[
          ['Total money lent', summary?.total_lent],
          ['Total money borrowed', summary?.total_borrowed],
          ['Outstanding receivables', summary?.outstanding_receivables],
          ['Outstanding liabilities', summary?.outstanding_liabilities],
        ].map(([label, amount]) => (
          <div key={String(label)} className="glass-card" style={{ padding: '18px' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '6px' }}>{label}</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-main)' }}>
              {amount === undefined ? '—' : formatMoney(amount as string | number)}
            </div>
          </div>
        ))}
      </div>

      <form className="glass-card" onSubmit={handleCreateLoan} style={{ padding: '20px', display: 'grid', gap: '12px' }}>
        <h3 style={{ color: 'var(--text-main)', fontWeight: 700 }}>Record a loan</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px' }}>
          <label style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
            Direction
            <select value={loanType} onChange={(event) => setLoanType(event.target.value as 'lent' | 'borrowed')} style={inputStyle}>
              <option value="lent">I lent money</option>
              <option value="borrowed">I borrowed money</option>
            </select>
          </label>
          <label style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
            Person
            <input required value={personName} onChange={(event) => setPersonName(event.target.value)} maxLength={255} style={inputStyle} />
          </label>
          <label style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
            Amount
            <input required type="number" min="0.01" step="0.01" value={loanAmount} onChange={(event) => setLoanAmount(event.target.value)} style={inputStyle} />
          </label>
          <label style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
            Date
            <input required type="date" value={loanDate} onChange={(event) => setLoanDate(event.target.value)} style={inputStyle} />
          </label>
          <label style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
            Due date (optional)
            <input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} style={inputStyle} />
          </label>
        </div>
        <label style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
          Description
          <input value={loanDescription} onChange={(event) => setLoanDescription(event.target.value)} maxLength={2000} style={inputStyle} />
        </label>
        <div>
          <button type="submit" className="btn-primary" style={{ padding: '9px 16px' }}>Review &amp; record</button>
        </div>
      </form>

      <section className="glass-card" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '14px' }}>
          <div>
            <h3 style={{ color: 'var(--text-main)', fontWeight: 700 }}>People-wise loan history</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
              {summary?.active_count ?? 0} pending · {summary?.settled_count ?? 0} settled
            </p>
          </div>
          <select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)} style={{ ...inputStyle, width: 'auto', marginTop: 0 }}>
            <option value="all">All loans</option>
            <option value="outstanding">Pending</option>
            <option value="settled">Settled</option>
          </select>
        </div>

        {loading ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading loans…</p>
        ) : visibleLoans.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', padding: '12px 0' }}>No loans match this view.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '780px' }}>
              <thead>
                <tr style={{ textAlign: 'left', color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                  {['Person / ID', 'Direction', 'Original', 'Outstanding', 'Status', 'Date', 'Repayment'].map((heading) => (
                    <th key={heading} style={{ padding: '10px 8px', borderBottom: '1px solid var(--border-subtle)' }}>{heading}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleLoans.map((loan) => (
                  <tr key={loan.id} style={{ color: 'var(--text-main)', borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={cellStyle}>
                      <button onClick={() => void showHistory(loan)} style={linkStyle}>
                        {loan.person_name} · #{loan.id}
                      </button>
                    </td>
                    <td style={cellStyle}>{loan.loan_type === 'lent' ? 'Money lent' : 'Money borrowed'}</td>
                    <td style={cellStyle}>{formatMoney(loan.original_amount)}</td>
                    <td style={cellStyle}>{formatMoney(loan.outstanding_amount)}</td>
                    <td style={cellStyle}>{loan.status.replace('_', ' ')}</td>
                    <td style={cellStyle}>{loan.transaction_date}</td>
                    <td style={cellStyle}>
                      {loan.status !== 'settled' ? (
                        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                          <input
                            aria-label={`Repayment amount for loan ${loan.id}`}
                            type="number"
                            min="0.01"
                            max={String(loan.outstanding_amount)}
                            step="0.01"
                            value={repaymentAmounts[loan.id] || ''}
                            onChange={(event) => setRepaymentAmounts((current) => ({ ...current, [loan.id]: event.target.value }))}
                            style={{ ...inputStyle, width: '110px', marginTop: 0, padding: '7px' }}
                          />
                          <button onClick={() => void handleRepayment(loan)} className="btn-secondary" style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>
                            Record
                          </button>
                        </div>
                      ) : <span style={{ color: 'var(--accent-emerald)' }}>Settled</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {history && (
        <section className="glass-card" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px' }}>
            <h3 style={{ color: 'var(--text-main)', fontWeight: 700 }}>
              Repayments · {history.loan.person_name} · Loan #{history.loan.id}
            </h3>
            <button onClick={() => setHistory(null)} className="btn-secondary" style={{ padding: '6px 10px' }}>Close</button>
          </div>
          {history.repayments.length ? (
            <ul style={{ marginTop: '12px', paddingLeft: '20px', color: 'var(--text-secondary)' }}>
              {history.repayments.map((repayment) => (
                <li key={repayment.id} style={{ padding: '4px 0' }}>
                  {repayment.repayment_date} · {formatMoney(repayment.amount)}
                  {repayment.description ? ` — ${repayment.description}` : ''}
                </li>
              ))}
            </ul>
          ) : <p style={{ color: 'var(--text-muted)', marginTop: '12px' }}>No repayments recorded yet.</p>}
        </section>
      )}
    </div>
  );
};

const inputStyle: React.CSSProperties = {
  display: 'block',
  width: '100%',
  marginTop: '5px',
  padding: '9px 10px',
  borderRadius: '8px',
  background: 'var(--bg-input)',
  border: '1px solid var(--border-subtle)',
  color: 'var(--text-main)',
};

const cellStyle: React.CSSProperties = { padding: '11px 8px', fontSize: '0.82rem', whiteSpace: 'nowrap' };
const linkStyle: React.CSSProperties = { padding: 0, border: 0, background: 'none', color: 'var(--accent-blue-text)', cursor: 'pointer', font: 'inherit' };
