import os
import json
from typing import TypedDict, List, Annotated
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("⚠️ WARNING: GOOGLE_API_KEY is missing in .env")

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    subtitles: List[dict] 
    style: dict         

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    temperature=0,
    google_api_key=api_key
)

def editor_agent(state: AgentState):
    messages = state["messages"]
    last_user_msg = messages[-1].content
    
    current_style = json.dumps(state["style"])
    sample_subs = json.dumps(state["subtitles"][:3]) 
    
    system_prompt = f"""
    You are an expert Video Editor AI. You manage subtitles and styling.
    
    CURRENT STATE:
    Style: {current_style}
    Sample Subs: {sample_subs}... (truncated)
    
    USER REQUEST: "{last_user_msg}"
    
    INSTRUCTIONS:
    Analyze the request and output valid JSON ONLY.
    
    SCENARIO 1: User wants to change visual style (color, size, font).
    Output: {{ "action": "style", "new_style": {{ "font_color": "Yellow", "font_size": 30 }} }}
    (Only include fields that changed. Use standard CSS colors).

    SCENARIO 2: User wants to fix typos or change text.
    Output: {{ "action": "chat", "response": "I can help with that, but specific text editing is best done manually for now. Shall I change the style instead?" }}
   
    
    SCENARIO 3: General Chat.
    Output: {{ "action": "chat", "response": "Your reply here." }}
    """

    ai_msg = llm.invoke([SystemMessage(content=system_prompt)]+ messages)
    
    content = ai_msg.content.replace("```json", "").replace("```", "").strip()
    
    try:
        decision = json.loads(content)
        
        if decision.get("action") == "style":
            updated_style = {**state["style"], **decision["new_style"]}
            
            return {
                "messages": [BaseMessage(content=f"Updated style to: {decision['new_style']}", type="ai")],
                "style": updated_style
            }
            
        elif decision.get("action") == "chat":
            return {"messages": [BaseMessage(content=decision["response"], type="ai")]}
            
    except Exception as e:
        return {"messages": [BaseMessage(content="Sorry, I didn't catch that. Try 'Make font red'.", type="ai")]}

    return {"messages": [ai_msg]}

builder = StateGraph(AgentState)
builder.add_node("editor", editor_agent)
builder.set_entry_point("editor")
builder.add_edge("editor", END)

graph = builder.compile()