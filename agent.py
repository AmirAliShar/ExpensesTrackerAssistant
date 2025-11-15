import asyncio
import os
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain.agents import create_agent

from langchain_mcp_adapters.client import MultiServerMCPClient

from Schema import QueryRequest

load_dotenv()


GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

llm = ChatGroq(model="openai/gpt-oss-20b")



async def run_agent(request: QueryRequest):
    client = MultiServerMCPClient(
        {
            "ExpensiveTracker": {
                "transport": "streamable_http",
                "url": "http://localhost:8001/mcp",
            }
        }
    )
    tools = await client.get_tools()
    

    agent =create_agent(
        model=llm,
        tools=tools
    )

    query = request.query
    result = await agent.ainvoke({"messages": query})

    # Extract the agent's response
    response_text = result["messages"][-1].content
    return response_text
   

if __name__ == "__main__":
    asyncio.run(run_agent())