import os
import json
import re
import difflib
import urllib.parse
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
    visuals: List[dict] 
    style: dict         

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    temperature=0,
    google_api_key=api_key
)

def find_timestamp_for_phrase(subtitles, phrase):
    """
    Finds precise start time using linear interpolation.
    If phrase is halfway through text, start time is halfway through segment.
    """
    if not phrase: return 0, 5
    
    phrase = phrase.lower().strip()
    best_ratio = 0.0
    best_match = (0, 5)
    
    for sub in subtitles:
        text = sub['text'].lower()
        
        match_index = -1
        if phrase in text:
            match_index = text.find(phrase)
            score = 1.0
        else:
            matcher = difflib.SequenceMatcher(None, phrase, text)
            score = matcher.ratio()
            if score > 0.6:
                match_index = 0 
        
        if score > 0.6:
            segment_duration = sub['end'] - sub['start']
            
            progress = match_index / len(text) if len(text) > 0 else 0
            
            precise_start = sub['start'] + (segment_duration * progress)
            
            precise_end = precise_start + 3.0 
            
            if score > best_ratio:
                best_ratio = score
                best_match = (precise_start, precise_end)

    if best_ratio > 0.6:
        print(f"✅ PRECISE MATCH: '{phrase}' at {best_match[0]:.2f}s")
        return best_match
        
    return 0, 5

def editor_agent(state: AgentState):
    messages = state["messages"]
    last_user_msg = messages[-1].content
    
    current_style = json.dumps(state["style"])
    sample_subs = json.dumps(state["subtitles"][:3]) 
    current_visuals = state.get("visuals", [])
    subs_text_only = [s['text'] for s in state["subtitles"]]
    subs_context = json.dumps(subs_text_only[:50])
    system_prompt = f"""
    You are an expert Video Editor AI and AI Video Director. You manage subtitles and styling.

    
    CURRENT STATE:
    Style: {current_style}
    Sample Subs: {sample_subs}... (truncated)
    TRANSCRIPT SNIPPET: {subs_context}
    USER REQUEST: "{last_user_msg}"
    
    INSTRUCTIONS:
    Analyze the request and output valid JSON ONLY.
    1. If user wants to change style -> Action: "style"
    2. If user wants to ADD ILLUSTRATIONS/IMAGES -> Action: "visual"
       - Identify the KEYWORD they mentioned.
       - 'img_style': Artistic style keywords to append (e.g. "photorealistic", "cyberpunk", "oil painting", "sketch").
       - 'trigger_phrase': The exact words in the transcript where this should appear.
        - 'visual_props': Extract styling preferences.
            - position: "center", "top-right", "top-left", "bottom-right", "bottom-left", "full-screen".
            - animation: "fade", "pop", "slide".
            - blend_mode: "normal" (default), "screen" (for holograms/ghosts), "multiply" (for dark overlays), "overlay".
            - opacity: 0.1 to 1.0 (default 1.0).
       - Output: {{ "action": "visual", "keyword": "cyberpunk city", "img_style": "hyperrealistic 8k render", "trigger_phrase": "Bhai Mantan","visual_props": {{ "position": "center", "animation": "pop", "opacity": 0.9, "blend_mode": "screen" }} }}
    
    SCENARIO 1: User wants to change visual style (color, size, font).
    Output: {{ "action": "style", "new_style": {{ "font_color": "Yellow", "font_size": 30 }} }}
    (Only include fields that changed. Use standard CSS colors).

    SCENARIO 2: User wants to fix typos or change text.
    Output: {{ "action": "chat", "response": "I can help with that, but specific text editing is best done manually for now. Shall I change the style instead?" }}
   
    
    SCENARIO 3: General Chat.
    Output: {{ "action": "chat", "response": "Your reply here." }}
    """

    ai_msg = llm.invoke([SystemMessage(content=system_prompt)]+ messages)
    
    raw_content = ai_msg.content
    
    print(f"🤖 RAW AI OUTPUT: {raw_content}") 
    try:
    
        clean_content = raw_content.replace("```json", "").replace("```", "").strip()
        

        match = re.search(r"\{.*\}", clean_content, re.DOTALL)
        if match:
            clean_content = match.group(0)
            
        decision = json.loads(clean_content)
        print(f"✅ PARSED JSON: {decision}")

        if decision.get("action") == "visual":
            keyword = decision.get("keyword", "abstract")
            trigger = decision.get("trigger_phrase", "")
            img_style = decision.get("img_style", "")
            props = decision.get("visual_props", {})
            
            start, end = find_timestamp_for_phrase(state["subtitles"], trigger)
            print(f"🚀 FINAL VISUAL TIME: Start={start}, End={end}")
            if start == 0 and len(current_visuals) > 0:
                last_end = current_visuals[-1]["end"]
                start = last_end
                end = start + 5
             
            full_prompt = f"{keyword}, {img_style}" 
            safe_prompt = urllib.parse.quote(keyword)
            
            image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=800&height=600&nologo=true"
            
            new_visual = {
                "id": str(len(current_visuals) + 1),
                "start": start,
                "end": end,
                "keyword": keyword,
                "url": image_url,
                "props": props 
            }
            
            return {
                "messages": [BaseMessage(content=f"Generated image: {full_prompt}", type="ai")],
                "visuals": current_visuals + [new_visual] 
            }

        elif decision.get("action") == "style":
            updated_style = {**state["style"], **decision["new_style"]}
            return {
                "messages": [BaseMessage(f"Updated style to: {decision['new_style']}", type="ai")],
                "style": updated_style
            }
            
        elif decision.get("action") == "chat":
            return {"messages": [BaseMessage(content=decision["response"], type="ai")]}
            
    except Exception as e:
        print(f"❌ PARSE ERROR: {e}")
        return {"messages": [BaseMessage(content="I tried to process that, but I got confused. Please try again.", type="ai")]}

    return {"messages": [ai_msg]}


   

builder = StateGraph(AgentState)
builder.add_node("editor", editor_agent)
builder.set_entry_point("editor")
builder.add_edge("editor", END)

graph = builder.compile()