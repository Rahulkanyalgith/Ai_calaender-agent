import operator
import json
from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

# --- CORRECTED IMPORT STATEMENTS ---
# `ToolExecutor` is now imported from a specific submodule.
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt import ToolExecutor

# --- LangGraph State Definition ---
class AgentState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        messages: A list of messages in the conversation.
        summary: The summary of the event to be booked.
        start_time: The proposed start time of the event.
        end_time: The proposed end time of the event.
        attendees: A list of attendees for the event.
        calendar_check_result: The result from the calendar availability check.
        action_needed: A flag to indicate if a tool action is needed.
    """
    messages: Annotated[list[BaseMessage], operator.add]
    summary: str | None
    start_time: str | None
    end_time: str | None
    attendees: List[str] | None
    calendar_check_result: str | None
    action_needed: str | None

# --- Define Tools (from backend/tools.py) ---
# We need to wrap our functions with @tool decorator to make them available to the agent.
# Note: In a real application, you would import these from the tools.py file.
# We'll define them here for a self-contained example.

from backend.tools import check_calendar_availability, create_google_calendar_event, get_current_datetime

@tool
def check_availability(start_time: str, end_time: str) -> str:
    """
    Checks the user's primary Google Calendar for busy time slots within a given time range.
    Provide the start and end time in ISO 8601 format.
    """
    return check_calendar_availability(start_time, end_time)

@tool
def book_meeting(summary: str, start_time: str, end_time: str, description: str = "", attendees: list = None) -> str:
    """
    Creates a new event on the user's primary Google Calendar.
    Requires a summary, start time, and end time in ISO 8601 format.
    Optional fields include description and a list of attendee emails.
    """
    return create_google_calendar_event(summary, start_time, end_time, description, attendees)

tools = [check_availability, book_meeting, get_current_datetime]
tool_executor = ToolExecutor(tools)

# --- Define the LLM and Prompt ---
# Use a powerful model like GPT-4o or similar.
# Ensure you have your OpenAI API key set as an environment variable (OPENAI_API_KEY).
# You can also use other models, e.g., from Anthropic or Groq.
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# --- Define the agent's logic (nodes) ---

# This function determines whether the agent should call a tool or respond directly.
def should_continue(state: AgentState):
    """
    Determines whether to continue with a tool call or end the conversation.
    """
    last_message = state['messages'][-1]
    if "tool_calls" in last_message.additional_kwargs:
        # The LLM wants to call a tool, so we will call the tool node
        return "continue"
    else:
        # The LLM is ready to respond, so we end the graph
        return "end"

# This is the main agent node that runs the LLM and decides on the next action.
def call_model(state: AgentState):
    """
    This node runs the LLM to decide on the next action.
    """
    messages = state['messages']
    
    # Add tool definitions to the message history so the model knows what tools are available.
    model_with_tools = llm.bind_tools(tools)
    response = model_with_tools.invoke(messages)
    
    # If the model decides to call a tool, the response will have 'tool_calls' in additional_kwargs.
    # We update the state with the model's message.
    return {"messages": [response]}

# This node executes the tool call decided by the LLM.
def call_tool(state: AgentState):
    """
    This node executes the tool call and updates the state with the result.
    """
    last_message = state['messages'][-1]
    tool_calls = last_message.additional_kwargs.get("tool_calls", [])
    
    # Execute all tool calls in parallel.
    outputs = []
    for tool_call in tool_calls:
        tool_name = tool_call['function']['name']
        tool_args = tool_call['function']['arguments']
        
        # Execute the tool and append the result.
        result = tool_executor.invoke([tool_call])
        outputs.append(ToolMessage(tool_call_id=tool_call['id'], content=json.dumps(result)))
        
        # Update state based on tool output
        if tool_name == 'check_availability':
            state['calendar_check_result'] = result
            state['action_needed'] = 'propose_slots' if 'free' in result.lower() else 'ask_for_new_time'
        elif tool_name == 'book_meeting':
            state['action_needed'] = 'confirm_booking'

    return {"messages": outputs, "action_needed": state.get('action_needed')}

# --- Build the LangGraph workflow ---
workflow = StateGraph(AgentState)

# Add nodes to the graph
workflow.add_node("call_model", call_model)
workflow.add_node("call_tool", call_tool)

# Set the entry point
workflow.add_edge(START, "call_model")

# Define the conditional edge from the model to either tool_call or end
workflow.add_conditional_edges(
    "call_model",
    should_continue,
    {"continue": "call_tool", "end": END}
)

# After the tool is called, we always go back to the model to generate a response.
workflow.add_edge("call_tool", "call_model")

# Compile the graph
app = workflow.compile()

if __name__ == "__main__":
    # Example usage for testing the agent locally
    from langchain_core.messages import HumanMessage
    
    # First turn: User asks to schedule a call
    inputs = {"messages": [HumanMessage(content="Hey, I want to schedule a call for tomorrow morning.")], "summary": None, "start_time": None, "end_time": None, "attendees": None, "calendar_check_result": None, "action_needed": None}
    for s in app.stream(inputs):
        print(s)
    
    # Second turn: User provides details, and the agent checks the calendar
    inputs = {"messages": [HumanMessage(content="Okay, let's book it for tomorrow from 10 AM to 11 AM.")], "summary": "Call", "start_time": "2025-06-29T10:00:00+05:30", "end_time": "2025-06-29T11:00:00+05:30", "attendees": [], "calendar_check_result": None, "action_needed": None}
    for s in app.stream(inputs):
        print(s)
        
    # Third turn: User confirms, and the agent books the meeting
    inputs = {"messages": [HumanMessage(content="Looks good, please book it.")], "summary": "Call", "start_time": "2025-06-29T10:00:00+05:30", "end_time": "2025-06-29T11:00:00+05:30", "attendees": ["test@example.com"], "calendar_check_result": "The calendar is free during this time.", "action_needed": None}
    for s in app.stream(inputs):
        print(s)