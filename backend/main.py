from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
import json

# --- Start: Fix for ModuleNotFoundError ---
# The original import `from backend.agent import app as langgraph_app` is failing.
# This is because Python cannot find a 'backend/agent.py' file.
# To make this script runnable, the import is commented out and a placeholder
# langgraph_app is created below.
#
# TODO: To fix this properly:
# 1. Create a directory named 'backend'.
# 2. Inside 'backend', create an empty file named '__init__.py'.
# 3. Inside 'backend', create a file named 'agent.py' with your LangGraph logic.
# 4. Once that is done, you can remove this placeholder and uncomment the original import.
# from backend.agent import app as langgraph_app

# Placeholder for langgraph_app so the API can run without the actual agent file.
# This placeholder simulates the expected structure of a compiled LangGraph application.
class MessagesState(BaseModel):
    messages: List[BaseMessage]

def placeholder_agent_logic(state: MessagesState):
    # Simulate a simple echo agent
    last_message = state['messages'][-1]
    response = AIMessage(content=f"This is a placeholder response to: '{last_message.content}'")
    return {"messages": [response]}

# Define a simple graph for the placeholder
workflow = StateGraph(MessagesState)
workflow.add_node("agent", placeholder_agent_logic)
workflow.set_entry_point("agent")
workflow.set_finish_point("agent")

# Compile the placeholder graph
langgraph_app = workflow.compile(checkpointer=SqliteSaver.from_conn_string(":memory:"))

# --- End: Fix ---


# Set up memory/persistence for the conversation
# This is crucial for maintaining state across turns in the conversation.
memory = SqliteSaver.from_conn_string(":memory:")

app = FastAPI(
    title="Google Calendar Booking Agent API",
    description="A FastAPI backend for a conversational AI agent that books appointments on Google Calendar.",
)

# Configure CORS to allow the Streamlit frontend to communicate with the backend
origins = [
    "http://localhost:8501",  # Default Streamlit port
    "http://127.0.0.1:8501",
    "https://your-deployed-streamlit-app.streamlit.app"  # Replace with your deployed URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    user_id: str
    message: str

class ChatResponse(BaseModel):
    response: str
    thread_id: str
    tool_calls: List[Dict[str, Any]] | None = None

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Receives user messages and interacts with the LangGraph agent.
    Maintains conversation history using a checkpoint.
    """
    user_id = request.user_id
    message = request.message

    # Get the thread ID for this user. You can use user_id directly or a mapping.
    thread_id = user_id

    config = {"configurable": {"thread_id": thread_id}}

    # Create the initial state with the user's message
    input_message = HumanMessage(content=message)

    try:
        # Invoke the LangGraph agent with the user's message
        # Use .stream for streaming UI, or .invoke for the final state.
        final_state = None
        # The placeholder app uses a slightly different state structure,
        # so we invoke it directly with the dictionary.
        async for event in langgraph_app.astream_events(
            {"messages": [input_message]},
            config=config,
            version="v2"
        ):
            if event["event"] == "on_chain_end":
                final_state = event["data"]["output"]


        # The final state is a dictionary, we want the messages from it.
        ai_response_message = None
        if final_state and final_state.get('messages'):
            for msg in reversed(final_state['messages']):
                if isinstance(msg, AIMessage):
                    ai_response_message = msg
                    break

        if ai_response_message:
            response_content = ai_response_message.content
            tool_calls = ai_response_message.tool_calls or ai_response_message.additional_kwargs.get("tool_calls")

            return ChatResponse(
                response=response_content,
                thread_id=thread_id,
                tool_calls=tool_calls
            )
        else:
            # If the agent's response is a tool call, we might not get an AIMessage.
            # In a more advanced setup, you'd handle this. For now, we'll respond.
            return ChatResponse(
                response="The agent did not return a direct message. This might be a tool call.",
                thread_id=thread_id
            )

    except Exception as e:
        # Handle potential errors, e.g., from the API or agent logic
        print(f"Error invoking LangGraph agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Google Calendar Booking Agent API is running."}