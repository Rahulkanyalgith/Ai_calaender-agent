import streamlit as st
import requests
import uuid

# --- Backend Configuration ---
# Update this URL if you deploy your FastAPI backend elsewhere.
FASTAPI_BACKEND_URL = "http://127.0.0.1:8000/"

# --- Streamlit UI Setup ---
st.set_page_config(page_title="🗓️ AI Appointment Booker", layout="wide")

st.title("🗓️ AI-Powered Appointment Booker")
st.write("I can help you check calendar availability and book meetings. Just tell me what you need!")

# Initialize session state for user ID and chat history
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4()) # Generate a unique user ID
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None

# Display chat messages from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Chat Input and Logic ---
if prompt := st.chat_input("How can I help you schedule?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)

    # Prepare data for FastAPI backend
    payload = {
        "user_id": st.session_state.user_id,
        "message": prompt
    }

    # Send message to backend and get response
    with st.spinner("Thinking..."):
        try:
            response = requests.post(f"{FASTAPI_BACKEND_URL}/chat", json=payload)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            agent_response = response.json()
            
            # Extract response content and thread_id
            bot_response = agent_response.get("response", "Sorry, I couldn't process that. Can you please rephrase?")
            st.session_state.thread_id = agent_response.get("thread_id")

            # Display assistant response in chat message container
            with st.chat_message("assistant"):
                st.markdown(bot_response)
            
            # Add assistant message to chat history
            st.session_state.messages.append({"role": "assistant", "content": bot_response})
            
        except requests.exceptions.ConnectionError:
            st.error("Could not connect to the FastAPI backend. Please ensure the backend server is running.")
            st.stop()
        except requests.exceptions.RequestException as e:
            st.error(f"An error occurred while communicating with the backend: {e}")
            st.stop()