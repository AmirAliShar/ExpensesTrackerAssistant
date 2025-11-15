import streamlit as st
import requests


BACKEND_URL = "http://127.0.0.1:8000/agent/query"


st.set_page_config(page_title="💰 AI Expense Tracker", page_icon="🤖", layout="centered")

st.title("💰 AI Expense Tracker Agent")
st.caption("LangChain + MCP + Groq + FastAPI + Streamlit")

# Persistent chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# Display previous chat messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


if prompt := st.chat_input("Ask me about your expenses..."):
    # Add user message to chat
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Display AI typing placeholder
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("_Thinking..._")

        try:
            # Send to FastAPI backend
            response = requests.post(
                BACKEND_URL,
                json={"query": prompt},
                timeout=60
            )

            if response.status_code == 200:
                result = response.json().get("response", "No response.")
            else:
                result = f"❌ Error: {response.text}"

        except requests.exceptions.RequestException as e:
            result = f"⚠️ Connection error: {str(e)}"

        # Update message display
        message_placeholder.markdown(result)
        st.session_state.messages.append({"role": "assistant", "content": result})
