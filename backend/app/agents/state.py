from typing import TypedDict, List, Optional, Dict, Any, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class FinPilotAgentState(TypedDict):
    """
    Typed state for FinPilot AI multi-agent orchestration and LangGraph checkpointing.
    Persisted directly in PostgreSQL via PostgresSaver.
    """
    messages: Annotated[List[BaseMessage], add_messages]
    user_id: int
    user_currency: str
    thread_id: str
    current_intent: Optional[str]
    specialist: Optional[str]
    executed_tools: List[str]
    memories_used: List[str]
    data: Dict[str, Any]
    pending_action: Optional[Dict[str, Any]]
    pending_confirmation: Optional[Dict[str, Any]]
    final_response: Optional[str]
    spoken_summary: Optional[str]
