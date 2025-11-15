from fastapi import FastAPI

from fastapi.responses import JSONResponse

from agent import run_agent

from Schema import QueryRequest

app = FastAPI(
    title="AI Expense Tracker Agent API",
    description="LangChain + MCP + Groq powered expense tracker agent backend",
    version="1.0.0",
)

@app.post("/agent/query")
async def handle_query(request: QueryRequest):
    """POST endpoint to run the AI agent"""
    try:
        agent_result = await run_agent(request)
        return JSONResponse({"response": agent_result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    

