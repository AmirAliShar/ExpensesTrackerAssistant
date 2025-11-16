# AI Expense Tracker Agent (FastMCP + LangGraph + FastAPI + Streamlit)

An AI-powered expense tracker agent that performs CRUD operations using natural language, backed by LangGraph reasoning, FastMCP tool calling, and a FastAPI backend, with a Streamlit frontend for user interaction.

This project demonstrates how modern agentic systems can use context-driven reasoning, tool execution, and external API/data access to automate financial operations.

# 🚀 Features

LangGraph-based reasoning loop for structured agent decisions

FastMCP used to call tools and fetch external data

FastAPI backend exposing /agent/query endpoint

Streamlit frontend for user interface

Natural-language CRUD on expenses (Create, Read, Update, Delete)

Public deployment on Render + optional Streamlit Cloud

Context-aware reasoning using the MCP runtime

# 🧠 Architecture Overview

## User → Streamlit UI → FastAPI Backend → LangGraph Agent → FastMCP Tools → DB / APIs

# Components

| Layer      | Technology            | Responsibility                              |
| ---------- | --------------------- | ------------------------------------------- |
| UI         | Streamlit             | Collect user query, display agent output    |
| Backend    | FastAPI               | Receives queries, runs LangGraph agent      |
| Agent      | LangChain + LangGraph | Reasoning, planning, tool selection         |
| Tool Layer | FastMCP               | Executes CRUD tools, external API, file ops |
| Schema     | Pydantic              | Validates user input                        |
| Deployment | Render                | Public backend hosting                      |

# 🛠️ Tech Stack

LangGraph / LangChain

FastAPI

FastMCP

Streamlit

Pydantic

Python 3.10+


<img width="1919" height="890" alt="image" src="https://github.com/user-attachments/assets/fefc449e-1d94-4b16-be6b-59b3edc979b1" />
<img width="1919" height="846" alt="image" src="https://github.com/user-attachments/assets/53bf2d49-fd40-4259-ab0b-d9c85ba7464b" />



# Video
https://github.com/user-attachments/assets/e3d2080e-373e-46e5-895f-e9063c28a11d


