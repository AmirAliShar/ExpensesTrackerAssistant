// Centralized API Client & Types for AI Expense Tracker — Agentic Personal Finance Assistant

export interface User {
  id: number;
  email: string;
  full_name?: string;
  preferred_currency: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Transaction {
  id: number;
  user_id: number;
  date: string;
  category: string;
  amount: number;
  type: 'expense' | 'income';
  description?: string;
  created_at?: string;
}

export interface CategoryPieItem {
  category: string;
  amount: number;
  percentage: number;
  count: number;
  color?: string;
}

export interface AnalyticsSummary {
  total_income: number;
  total_expenses: number;
  net_savings: number;
  savings_rate: number;
  currency: string;
  categories: CategoryPieItem[];
  recent_transactions: Transaction[];
}

export interface Budget {
  id: number;
  user_id: number;
  category: string;
  monthly_limit: number;
  spent: number;
  utilization_percentage: number;
  status: 'safe' | 'warning' | 'danger';
  month: string;
}

export interface SavingsGoal {
  id: number;
  user_id: number;
  title: string;
  target_amount: number;
  current_amount: number;
  progress_percentage: number;
  target_date?: string;
}

export interface Memory {
  id: number;
  user_id: number;
  memory_type: string;
  content: string;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface PendingConfirmation {
  action_token: string;
  action_type: string;
  target_id?: number;
  summary: string;
  details: Record<string, any>;
  status: string;
}

export interface AgentResponse {
  response: string;
  spoken_summary?: string;
  thread_id: string;
  executed_tools: string[];
  memories_used: string[];
  pending_confirmation?: PendingConfirmation | null;
}

export interface HistoryMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  spokenSummary?: string;
  toolsUsed?: string[];
  memoriesUsed?: string[];
  pendingConfirmation?: PendingConfirmation | null;
  timestamp: string;
}

export interface AgentHistoryResponse {
  thread_id: string;
  messages: HistoryMessage[];
  pending_confirmation?: PendingConfirmation | null;
}

export interface Conversation {
  id: number;
  thread_id: string;
  title: string;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface DailyBriefingGoal {
  title: string;
  target_amount: number;
  current_amount: number;
  progress_percentage: number;
}

export interface DailyBriefing {
  date: string;
  yesterday: string;
  yesterday_spending: number;
  month: string;
  monthly_spending: number;
  remaining_monthly_budget?: number;
  budget_alerts: string[];
  savings_goals: DailyBriefingGoal[];
  summary: string;
}

export type MoneyAmount = number | string;

export interface PersonalLoan {
  id: number;
  user_id: number;
  person_name: string;
  loan_type: 'lent' | 'borrowed';
  original_amount: MoneyAmount;
  outstanding_amount: MoneyAmount;
  transaction_date: string;
  due_date?: string | null;
  description?: string | null;
  status: 'active' | 'partially_paid' | 'settled';
  created_at: string;
  updated_at: string;
}

export interface LoanRepayment {
  id: number;
  loan_id: number;
  amount: MoneyAmount;
  repayment_date: string;
  description?: string | null;
  created_at: string;
}

export interface LoanHistory {
  loan: PersonalLoan;
  repayments: LoanRepayment[];
}

export interface LoanSummary {
  total_lent: MoneyAmount;
  total_borrowed: MoneyAmount;
  outstanding_receivables: MoneyAmount;
  outstanding_liabilities: MoneyAmount;
  active_count: number;
  settled_count: number;
}

const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('token');
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
  }

  getToken(): string | null {
    return this.token;
  }

  getGoogleAuthUrl(): string {
    return `${API_BASE}/api/auth/google/start`;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorMsg = `HTTP Error ${response.status}`;
      try {
        const errJson = await response.json();
        errorMsg = errJson.detail || errJson.message || errorMsg;
      } catch {
        // ignore
      }
      throw new Error(errorMsg);
    }

    return response.json();
  }

  // --- Auth API ---
  async login(email: string, password: string): Promise<AuthResponse> {
    const data = await this.request<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async register(email: string, password: string, fullName?: string, currency = 'PKR'): Promise<AuthResponse> {
    const data = await this.request<AuthResponse>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName, preferred_currency: currency }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async getMe(): Promise<User> {
    return this.request<User>('/api/auth/me');
  }

  logout() {
    this.setToken(null);
  }

  // --- Transactions API ---
  async getTransactions(params: { category?: string; month?: string; type?: string; limit?: number } = {}): Promise<Transaction[]> {
    const query = new URLSearchParams();
    if (params.category) query.append('category', params.category);
    if (params.month) query.append('month', params.month);
    if (params.type) query.append('type', params.type);
    if (params.limit) query.append('limit', String(params.limit));
    return this.request<Transaction[]>(`/api/transactions?${query.toString()}`);
  }

  async createTransaction(tx: Omit<Transaction, 'id' | 'created_at' | 'user_id'>): Promise<Transaction> {
    return this.request<Transaction>('/api/transactions', {
      method: 'POST',
      body: JSON.stringify(tx),
    });
  }

  async updateTransaction(id: number, tx: Partial<Transaction>): Promise<Transaction> {
    return this.request<Transaction>(`/api/transactions/${id}`, {
      method: 'PUT',
      body: JSON.stringify(tx),
    });
  }

  async deleteTransaction(id: number): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/api/transactions/${id}`, {
      method: 'DELETE',
    });
  }

  // --- Analytics & Pie Chart API ---
  async getAnalytics(params: { month?: string; start_date?: string; end_date?: string } = {}): Promise<AnalyticsSummary> {
    const query = new URLSearchParams();
    if (params.month) query.append('month', params.month);
    if (params.start_date) query.append('start_date', params.start_date);
    if (params.end_date) query.append('end_date', params.end_date);
    return this.request<AnalyticsSummary>(`/api/analytics/summary?${query.toString()}`);
  }

  // --- Budgets API ---
  async getBudgets(month?: string): Promise<Budget[]> {
    const query = month ? `?month=${month}` : '';
    return this.request<Budget[]>(`/api/budgets${query}`);
  }

  async createBudget(b: { category: string; monthly_limit: number; month: string }): Promise<Budget> {
    return this.request<Budget>('/api/budgets', {
      method: 'POST',
      body: JSON.stringify(b),
    });
  }

  async deleteBudget(id: number): Promise<void> {
    return this.request<void>(`/api/budgets/${id}`, { method: 'DELETE' });
  }

  // --- Savings Goals API ---
  async getGoals(): Promise<SavingsGoal[]> {
    return this.request<SavingsGoal[]>('/api/goals');
  }

  async createGoal(g: { title: string; target_amount: number; current_amount?: number }): Promise<SavingsGoal> {
    return this.request<SavingsGoal>('/api/goals', {
      method: 'POST',
      body: JSON.stringify(g),
    });
  }

  // --- Long-Term Memory API ---
  async getMemories(): Promise<Memory[]> {
    return this.request<Memory[]>('/api/memories');
  }

  async createMemory(mem: { memory_type: string; content: string }): Promise<Memory> {
    return this.request<Memory>('/api/memories', {
      method: 'POST',
      body: JSON.stringify(mem),
    });
  }

  async deleteMemory(id: number): Promise<void> {
    return this.request<void>(`/api/memories/${id}`, { method: 'DELETE' });
  }

  async clearMemories(): Promise<void> {
    return this.request<void>('/api/memories', { method: 'DELETE' });
  }

  // --- Personal Lending & Borrowing API ---
  async getLoanSummary(): Promise<LoanSummary> {
    return this.request<LoanSummary>('/api/loans/summary');
  }

  async getLoans(params: {
    loan_type?: 'lent' | 'borrowed';
    status?: 'active' | 'partially_paid' | 'settled';
    person_name?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<PersonalLoan[]> {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') query.append(key, String(value));
    });
    return this.request<PersonalLoan[]>(`/api/loans?${query.toString()}`);
  }

  async createLoan(loan: {
    person_name: string;
    loan_type: 'lent' | 'borrowed';
    original_amount: string;
    transaction_date: string;
    due_date?: string;
    description?: string;
  }): Promise<PersonalLoan> {
    return this.request<PersonalLoan>('/api/loans', {
      method: 'POST',
      body: JSON.stringify({ ...loan, confirmed: true }),
    });
  }

  async getLoanHistory(id: number): Promise<LoanHistory> {
    return this.request<LoanHistory>(`/api/loans/${id}/history`);
  }

  async recordLoanRepayment(
    id: number,
    repayment: {
      amount: string;
      repayment_date: string;
      description?: string;
      idempotency_key: string;
    },
  ): Promise<{ loan: PersonalLoan; repayment: LoanRepayment; created: boolean }> {
    return this.request(`/api/loans/${id}/repayments`, {
      method: 'POST',
      body: JSON.stringify({ ...repayment, confirmed: true }),
    });
  }

  // --- Reports & Exports API ---
  async getMonthlyReport(month?: string): Promise<any> {
    const query = month ? `?month=${month}` : '';
    return this.request<any>(`/api/reports/monthly${query}`);
  }

  async getDailyBriefing(): Promise<DailyBriefing> {
    return this.request<DailyBriefing>('/api/briefings/daily');
  }

  getCsvExportUrl(month?: string): string {
    const query = month ? `?month=${month}` : '';
    return `${API_BASE}/api/reports/csv${query}`;
  }

  // --- Agent & Voice API ---
  async queryAgent(query: string, thread_id?: string, is_voice = false): Promise<AgentResponse> {
    return this.request<AgentResponse>('/api/agent/query', {
      method: 'POST',
      body: JSON.stringify({ query, thread_id, is_voice }),
    });
  }

  async queryAgentStream(
    query: string,
    threadId: string,
    onChunk: (text: string) => void,
  ): Promise<AgentResponse> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.token) headers['Authorization'] = `Bearer ${this.token}`;
    const response = await fetch(`${API_BASE}/api/agent/query/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ query, thread_id: threadId }),
    });
    if (!response.ok) throw new Error(`Streaming HTTP Error ${response.status}`);
    if (!response.body) throw new Error('Streaming response unavailable');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalResponse: AgentResponse | null = null;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === 'chunk') onChunk(event.text);
        if (event.type === 'done') {
          finalResponse = {
            response: '',
            thread_id: event.thread_id,
            executed_tools: event.executed_tools || [],
            memories_used: event.memories_used || [],
            pending_confirmation: event.pending_confirmation || null,
            spoken_summary: undefined,
          };
        }
      }
    }
    if (!finalResponse) throw new Error('Stream ended without a final response');
    return finalResponse;
  }

  async getAgentHistory(thread_id?: string): Promise<AgentHistoryResponse> {
    const query = thread_id ? `?thread_id=${encodeURIComponent(thread_id)}` : '';
    return this.request<AgentHistoryResponse>(`/api/agent/history${query}`);
  }

  async clearAgentHistory(thread_id?: string): Promise<{ status: string; message: string }> {
    const query = thread_id ? `?thread_id=${encodeURIComponent(thread_id)}` : '';
    return this.request<{ status: string; message: string }>(`/api/agent/history${query}`, {
      method: 'DELETE',
    });
  }

  async getConversations(search = '', includeArchived = false): Promise<Conversation[]> {
    const params = new URLSearchParams();
    if (search) params.append('search', search);
    if (includeArchived) params.append('include_archived', 'true');
    return this.request<Conversation[]>(`/api/conversations?${params.toString()}`);
  }

  async createConversation(threadId: string, title = 'New conversation'): Promise<Conversation> {
    return this.request<Conversation>('/api/conversations', {
      method: 'POST',
      body: JSON.stringify({ thread_id: threadId, title }),
    });
  }

  async updateConversation(id: number, update: { title?: string; archived?: boolean }): Promise<Conversation> {
    return this.request<Conversation>(`/api/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(update),
    });
  }

  async deleteConversation(id: number): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/api/conversations/${id}`, {
      method: 'DELETE',
    });
  }

  async confirmAction(action_token: string, confirmed = true, thread_id?: string): Promise<any> {
    return this.request('/api/agent/confirm', {
      method: 'POST',
      body: JSON.stringify({ action_token, confirmed, thread_id }),
    });
  }

  async transcribeAudio(audioBlob: Blob): Promise<string> {
    const formData = new FormData();
    formData.append('file', audioBlob, 'audio.wav');
    const headers: Record<string, string> = {};
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    const response = await fetch(`${API_BASE}/api/voice/transcribe`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!response.ok) {
      let errText = `HTTP Error ${response.status}`;
      try {
        const errJson = await response.json();
        errText = errJson.detail || errText;
      } catch {}
      throw new Error(errText);
    }
    const data = await response.json();
    return data.transcript;
  }
}

export const api = new ApiClient();
