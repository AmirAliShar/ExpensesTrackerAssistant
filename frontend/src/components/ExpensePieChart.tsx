import React, { useState } from 'react';
import { CategoryPieItem } from '../api';

interface PieChartProps {
  categories: CategoryPieItem[];
  totalExpenses: number;
  currency?: string;
  selectedMonth?: string;
  onFilterChange?: (month: string) => void;
}

export const ExpensePieChart: React.FC<PieChartProps> = ({
  categories,
  totalExpenses,
  currency = 'PKR',
}) => {
  const [hoveredCategory, setHoveredCategory] = useState<CategoryPieItem | null>(null);

  // SVG dimensions
  const size = 300;
  const center = size / 2;
  const radius = 100;
  const strokeWidth = 36;
  const circumference = 2 * Math.PI * radius;

  // If no expenses exist yet
  if (!categories || categories.length === 0 || totalExpenses === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
        <div style={{ fontSize: '3rem', marginBottom: '12px' }}>📊</div>
        <h4 style={{ color: 'var(--text-main)', marginBottom: '6px' }}>No Expense Data in This Range</h4>
        <p style={{ fontSize: '0.875rem' }}>Add or log expenses to see your dynamic category breakdown & percentages.</p>
      </div>
    );
  }

  // Calculate cumulative stroke offsets for SVG donut slices
  let accumulatedOffset = 0;
  const slices = categories.map((cat) => {
    // Exact percentage calculation: (Category Expenses / Total Expenses) * 100
    const fraction = cat.amount / totalExpenses;
    const strokeDasharray = `${fraction * circumference} ${circumference}`;
    const strokeDashoffset = -accumulatedOffset;
    accumulatedOffset += fraction * circumference;

    return {
      ...cat,
      strokeDasharray,
      strokeDashoffset,
    };
  });

  const displayCategory = hoveredCategory || categories[0];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Chart and Center Stats */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center', gap: '32px' }}>
        <div style={{ position: 'relative', width: size, height: size }}>
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
            {/* Background circle track */}
            <circle
              cx={center}
              cy={center}
              r={radius}
              fill="transparent"
              stroke="var(--border-subtle)"
              strokeWidth={strokeWidth}
            />

            {/* Slices */}
            {slices.map((slice) => (
              <circle
                key={slice.category}
                cx={center}
                cy={center}
                r={radius}
                fill="transparent"
                stroke={slice.color || '#2563EB'}
                strokeWidth={hoveredCategory?.category === slice.category ? strokeWidth + 6 : strokeWidth}
                strokeDasharray={slice.strokeDasharray}
                strokeDashoffset={slice.strokeDashoffset}
                strokeLinecap="round"
                style={{
                  transition: 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
                  cursor: 'pointer',
                  filter: hoveredCategory?.category === slice.category ? `drop-shadow(0 0 8px ${slice.color || '#2563EB'})` : 'none',
                }}
                onMouseEnter={() => setHoveredCategory(slice)}
                onMouseLeave={() => setHoveredCategory(null)}
              />
            ))}
          </svg>

          {/* Centered Donut Value */}
          <div
            style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              textAlign: 'center',
              pointerEvents: 'none',
              maxWidth: '160px',
            }}
          >
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {displayCategory.category}
            </div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-main)', margin: '4px 0' }}>
              {displayCategory.percentage.toFixed(1)}%
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--accent-emerald)', fontWeight: 600 }}>
              {currency} {displayCategory.amount.toLocaleString()}
            </div>
          </div>
        </div>

        {/* Legend with exact amounts & percentages */}
        <div style={{ flex: '1', minWidth: '220px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>
            Categories ({categories.length})
          </div>
          <div style={{ maxHeight: '240px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px', paddingRight: '6px' }}>
            {categories.map((cat) => {
              const isHovered = hoveredCategory?.category === cat.category;
              return (
                <div
                  key={cat.category}
                  onMouseEnter={() => setHoveredCategory(cat)}
                  onMouseLeave={() => setHoveredCategory(null)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    background: isHovered ? 'var(--bg-hover-subtle)' : 'transparent',
                    border: `1px solid ${isHovered ? cat.color || '#2563EB' : 'var(--border-subtle)'}`,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span
                      style={{
                        width: '12px',
                        height: '12px',
                        borderRadius: '3px',
                        backgroundColor: cat.color || '#2563EB',
                        boxShadow: `0 0 6px ${cat.color || '#2563EB'}88`,
                      }}
                    />
                    <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)' }}>
                      {cat.category}
                    </span>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-main)' }}>
                      {cat.percentage.toFixed(1)}%
                    </span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '8px' }}>
                      ({currency} {cat.amount.toLocaleString()})
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Breakdown Detailed Table */}
      <div style={{ marginTop: '8px', overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem', textAlign: 'left' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
              <th style={{ padding: '8px 12px', fontWeight: 600 }}>Category</th>
              <th style={{ padding: '8px 12px', fontWeight: 600 }}>Transactions</th>
              <th style={{ padding: '8px 12px', fontWeight: 600 }}>Amount ({currency})</th>
              <th style={{ padding: '8px 12px', fontWeight: 600 }}>Share</th>
              <th style={{ padding: '8px 12px', fontWeight: 600 }}>Visual Share</th>
            </tr>
          </thead>
          <tbody>
            {categories.map((cat) => (
              <tr key={cat.category} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <td style={{ padding: '10px 12px', fontWeight: 600, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: cat.color || '#2563EB' }} />
                  {cat.category}
                </td>
                <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>{cat.count} txs</td>
                <td style={{ padding: '10px 12px', fontWeight: 600, color: 'var(--text-main)' }}>{cat.amount.toLocaleString()}</td>
                <td style={{ padding: '10px 12px', fontWeight: 700, color: 'var(--accent-blue-text)' }}>{cat.percentage.toFixed(1)}%</td>
                <td style={{ padding: '10px 12px', width: '25%' }}>
                  <div style={{ width: '100%', height: '6px', background: 'var(--border-subtle)', borderRadius: '3px', overflow: 'hidden' }}>
                    <div
                      style={{
                        width: `${cat.percentage}%`,
                        height: '100%',
                        backgroundColor: cat.color || '#2563EB',
                        borderRadius: '3px',
                      }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
