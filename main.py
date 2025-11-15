from fastapi import FastAPI
from fastapi.responses import JSONResponse
from Schema import QueryRequest
from agent import run_agent
import asyncio

app = FastAPI(
    title="AI Expense Tracker Agent API",
    description="LangChain + MCP + Groq powered expense tracker agent backend",
    version="1.0.0",
)

@app.post("/agent/query")
async def handle_query(request: QueryRequest):
    response_text = await run_agent(request)
    return JSONResponse({"response": response_text})
