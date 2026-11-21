from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
# python -m backend.tools.mcp_tools                                    # MCP server, :8002
# python -m backend.main                                               # API, :8000 (with reload)
#   -- not `python -m uvicorn backend.main:app`: uvicorn creates the event loop
#      before importing this module, which leaves psycopg on a proactor loop.
#      Add --reload only if you must use the uvicorn CLI directly.
# cd frontend/web && npm run dev                                       # dashboard, :3000
