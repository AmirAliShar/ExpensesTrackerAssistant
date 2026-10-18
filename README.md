# FinPilot AI — Agentic Personal Finance Assistant

FinPilot AI is an enterprise-grade, multi-user, voice-enabled personal finance application powered by **LangChain**, **LangGraph**, **Groq**, **FastMCP**, **FastAPI**, **PostgreSQL**, and a modern **React + TypeScript** frontend.

---

## 🚀 Key Architectural Upgrades & Capabilities

1. **Mandatory PostgreSQL Engine & Alembic Migrations**
   - Authoritative PostgreSQL storage for all users, transactions, budgets, savings goals, and durable memories.
   - **No Silent SQLite Fallback:** The backend fails fast with clear, actionable diagnostics if PostgreSQL is unavailable or credentials fail.
   - Automated Alembic migrations manage database schema versions idempotently.
   - Exact Decimal currency arithmetic (`Numeric(12, 2)`) avoids floating-point calculation errors.

2. **Strict Multi-User Security & Tenant Isolation**
   - Cryptographic `bcrypt` password hashing and secure `JWT` authentication.
   - Every transactional, budget, goal, and memory query is strictly scoped to the authenticated user ID (`user_id`).
   - Cross-tenant access is prohibited at both the API and database levels.
   - Thread identifiers are automatically scoped to each user (`user_{user_id}_{thread_id}`).

3. **Dynamic Model Selection & Groq Fallback Chain**
   - Dynamic Groq model selection following official LangChain best practices:
     $$\text{Primary: } \texttt{llama-3.1-8b-instant} \longrightarrow \text{Fallback 1: } \texttt{llama-3.3-70b-versatile} \longrightarrow \text{Fallback 2: } \texttt{openai/gpt-oss-120b}$$
   - Bounded retries with exponential backoff and randomized jitter for retryable errors (429 Rate Limits, 503 Server Unavailable).
   - Fast-fails without retry loops on non-retryable errors (401 Unauthorized, 400 Bad Request).
   - Resilient offline rule engine fallback if credentials are unset or provider services are down.

4. **Environment-Driven Agent System Prompts**
   - Configurable specialist system prompts loaded from environment variables (`AGENT_PROMPTS_FROM_ENV=true`):
     - `FINANCE_SUPERVISOR_PROMPT`: Intent classification and coordination.
     - `EXPENSE_AGENT_PROMPT`: Precision categorization and transaction proposals.
     - `BUDGET_AGENT_PROMPT`: Spending limit velocity and proactive alerts.
     - `ANALYTICS_AGENT_PROMPT`: Category breakdown and deterministic metrics.
     - `MEMORY_AGENT_PROMPT`: Durable preference extraction without credentials leakage.
     - `VOICE_AGENT_PROMPT`: Concise natural language synthesis.
   - Safe, version-controlled defaults maintained in [`backend/app/agents/prompts/`](file:///e:/Algorithm/AgenticAI/ExpensesTrackerAssistant/backend/app/agents/prompts/).

5. **Human-in-the-Loop (HITL) Confirmation & Interrupts**
   - Destructive financial mutations (updating a transaction, deleting a transaction, modifying spending limits) pause for explicit user confirmation.
   - Returns a structured confirmation proposal (`action_token`, summary, affected record) to the user.
   - Resumed through `/api/agent/confirm` inside a PostgreSQL transaction with idempotency protection against duplicate execution.

6. **Voice Interface: Whisper STT & Neural TTS**
   - Speech-to-Text (STT) powered by Groq-hosted `whisper-large-v3-turbo`.
   - Text-to-Speech (TTS) synthesis powered by `edge-tts` (or local fallback).
   - Full microphone permission handling, audio recording, and visual confirmation in the frontend.

7. **Durable PostgreSQL Memory & LangGraph Checkpoints**
   - State checkpoints stored across server restarts.
   - Permanent user preferences (e.g. target savings rate, preferred currency) stored in the `user_memories` PostgreSQL table with complete user inspection and deletion controls.

---

## 🧠 System Architecture

```mermaid
graph TD
    User([User Voice / Text]) --> ReactApp[React 19 + TypeScript Frontend]
    ReactApp -->|Bearer JWT / REST| FastAPI[FastAPI Backend - Port 8000]
    
    subgraph Multi-User Security & Persistence
        FastAPI --> Auth[Bcrypt + JWT Authentication]
        FastAPI --> DB[(PostgreSQL Database - Port 5432)]
        DB --> Tables[Users • Transactions • Budgets • Goals • Memories]
        DB --> Checkpoints[LangGraph Checkpoint Schema]
    end
    
    subgraph Agentic Orchestration Layer
        FastAPI --> Supervisor[Finance Supervisor Agent]
        Supervisor --> ExpenseAgent[Expense Specialist]
        Supervisor --> BudgetAgent[Budget Specialist]
        Supervisor --> AnalyticsAgent[Analytics Specialist]
        Supervisor --> MemoryAgent[Memory Specialist]
    end

    subgraph Resilient Model Layer
        Supervisor --> ModelFactory[Centralized Model Factory]
        ModelFactory -->|Primary| Groq1[Groq llama-3.1-8b-instant]
        ModelFactory -->|Fallback 1| Groq2[Groq llama-3.3-70b-versatile]
        ModelFactory -->|Fallback 2| Groq3[Groq openai/gpt-oss-120b]
    end

    subgraph Human-in-the-Loop Safeguards
        ExpenseAgent -->|Destructive Action| HITL[Confirmation Proposal]
        HITL -->|Requires Explicit User Confirmation| ReactApp
    end

    subgraph Voice Services
        FastAPI --> WhisperSTT[Groq Whisper Large v3 Turbo]
        FastAPI --> NeuralTTS[Neural Edge-TTS / Audio Stream]
    end
```

---

## 📋 Prerequisites

- **Python:** Version `>= 3.11`
- **Node.js:** Version `>= 18.x`
- **PostgreSQL:** Version `>= 14.x` running on port 5432

---

## ⚙️ Configuration & Environment Setup

Copy `.env.example` to `.env` in the `backend/` directory (or root):

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` with your PostgreSQL credentials and Groq API key:

```env
# Mandatory PostgreSQL Configuration
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/LangGraph
PGHOST=localhost
PGPORT=5432
PGDATABASE=LangGraph
PGUSER=postgres
PGPASSWORD=YOUR_PASSWORD

# Groq LLM & Dynamic Fallback
GROQ_API_KEY=gsk_your_groq_api_key_here
PRIMARY_CHAT_PROVIDER=groq
PRIMARY_CHAT_MODEL=llama-3.1-8b-instant
GROQ_FALLBACK_MODELS=llama-3.3-70b-versatile,openai/gpt-oss-120b

# Voice
GROQ_STT_MODEL=whisper-large-v3-turbo
TTS_PROVIDER=edge-tts
TTS_MODEL=en-US-ChristopherNeural

# Security
JWT_SECRET_KEY=antigravity_super_secret_jwt_key_2026_finance_assistant
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

---

## 🗄️ Database Initialization & Migrations

### 1. Create the PostgreSQL Database
If the database does not already exist on your PostgreSQL server, run in `psql` or pgAdmin:

```sql
CREATE DATABASE "LangGraph";
```

### 2. Run Database Migrations (Alembic)
Execute the initial schema migration from the `backend/` directory:

```bash
cd backend
alembic upgrade head
```

The database schema will be initialized idempotently.

---

## 🚀 Running the Application

### 1. Start the Backend API Server
```bash
cd backend
python main.py
```
*The FastAPI application will start on `http://localhost:8000`.*
*Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.*

### 2. Start the FastMCP Server (Optional)
```bash
cd backend
python -m app.mcp.server
```
*Listens on `http://localhost:8001/mcp`.*

### 3. Start the Frontend Development Server
```bash
cd frontend
npm install
npm run dev
```
*The React + Vite frontend will be available at `http://localhost:5173`.*

---

## 👤 Initial User Account & Authentication

Upon initial startup with PostgreSQL, a default demo account is safely seeded:
- **Email:** `demo@antigravity.io`
- **Password:** `password123`

You can also register a new user anytime directly through the UI modal or the `/api/auth/register` endpoint.

---

## 🧪 Automated Testing

FinPilot AI includes a comprehensive test suite in `backend/tests/`:

```bash
cd backend
python run_tests.py
```

Or using `pytest`:

```bash
cd backend
pytest -v tests/
```

### Test Coverage Summary:
- `test_database.py`: PostgreSQL URL verification, rejection of SQLite, and Decimal column checks.
- `test_auth_isolation.py`: Email normalization, Bcrypt password hashing, JWT security, multi-tenant isolation, and thread ID scoping.
- `test_models_fallback.py`: Model candidate order, error classification (401 vs 429), fast-fail without endless looping, and fallback chaining.
- `test_prompts.py`: Role-specific default prompts and environment variable overrides.
- `test_hitl_confirmation.py`: Human-in-the-Loop proposal generation, cancellation without database side effects, and idempotency protection.
- `test_voice_and_tools.py`: Whisper audio validation and deterministic financial analytics calculations.

---

## 🛡️ Human-in-the-Loop Confirmation Flow

When a user commands a consequential financial action:
1. **User Request:** *"Delete transaction #4"*
2. **Proposal Generation:** The Expense specialist retrieves the record belonging to the authenticated user, verifies ownership, and issues a pending proposal (`action_token`).
3. **Graph Pause:** Execution halts without altering the database.
4. **UI Modal / Card:** The frontend renders an interactive card:
   ```text
   ⚠️ Confirmation Required: Delete transaction #4 (Expense Rs. 4,200 Food on 2026-10-10)
   [✓ Confirm Action]   [✕ Cancel]
   ```
5. **Resume & Idempotency:** Clicking **Confirm** triggers `/api/agent/confirm`. The transaction is removed inside a database transaction, and the proposal token is retired.
