import streamlit as st
import requests

# FastAPI backend URL
API_URL = "http://localhost:8000/agent/query"
#API_URL = "https://expensestrackerassistant-2.onrender.com" # Render on deploy, but it does not work

st.title("💸 AI Expense Tracker Agent")
st.write("LangChain + MCP + Groq Powered Agent")

# Input form
with st.form(key="query_form"):
    user_query = st.text_input("Enter your expense query:")
    submit = st.form_submit_button("Submit")

if submit:
    if not user_query.strip():
        st.warning("Please enter a query.")
    else:
        with st.spinner("Processing..."):
            try:
                payload = {"query": user_query}   # Must match QueryRequest schema
                response = requests.post(API_URL, json=payload)

                if response.status_code == 200:
                    result = response.json().get("response", "")
                    st.success("Agent Response:")
                    st.write(result)

                else:
                    st.error(f"Error: {response.status_code}")
                    st.write(response.json())

            except Exception as e:
                st.error("Failed to connect to API.")
                st.write(str(e))

