import os
import asyncio
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from Schema import QueryRequest

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# Initialize the LLM once
llm = ChatGroq(model="openai/gpt-oss-20b")


async def run_agent(request: QueryRequest):
    # Connect to MCP server
    client = MultiServerMCPClient(
        {
            "ExpensiveTracker": {
                "transport": "streamable_http",
                "url": "http://localhost:8001/mcp",
            }
        }
    )
    # Fetch tools from MCP
    tools = await client.get_tools()

    # Create agent with tools
    agent = create_agent(model=llm, tools=tools)

    # Prepare the query for the agent
    query = request.query
    result = await agent.ainvoke({"messages": [{"role": "user", "content": query}]})

    # Safely extract the response text
    response_text = result.get("output_text") or str(result)
    return response_text
