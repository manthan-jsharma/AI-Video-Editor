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
    hud_items: List[dict] 
    visuals: List[dict]
    camera_moves: List[dict]
    text_layers: List[dict] 
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
    current_cam = state.get("camera_moves", [])
    
    current_style = json.dumps(state["style"])
    sample_subs = json.dumps(state["subtitles"][:3]) 
    current_visuals = state.get("visuals", [])
    current_hud = state.get("hud_items", [])
    current_text_layers = state.get("text_layers", [])
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

     SCENARIO 1: Text Behind Person (Depth Effect).
    - User wants huge text behind them.
    - 'text_content': The text to show (e.g. "EPIC").
     - 'text_props': Styling details.
        - size: number (default 150).
        - color: hex or name (default "white").
        - font: "sans-serif", "serif", "cursive", "monospace".
        - position_y: "center", "top", "bottom".
        - animation: "zoom" (default), "fade", "slide-left", "slide-right", "bounce", "typewriter".
        - shadow: boolean (default true).
    - 'trigger_phrase': When to show it.
    - Output: {{ "action": "text_behind", "text_content": "...", "trigger_phrase": "...", "text_props": {{ "color": "red", "position_y": "top", "animation": "slide-left" }}  }}

    SCENARIO 2: Camera / Zoom (User wants movement, zoom, pan).
    - 'trigger_phrase': Exact words in transcript to sync the move to.
    - 'type': "zoom-in" (Close up), "zoom-out" (Wide), "pan-left", "pan-right", "shake".
    - 'intensity': 1.2 (Subtle) to 2.0 (Extreme). Default 1.4.
    - Output: {{ "action": "camera", "type": "zoom-in", "intensity": 1.5, "trigger_phrase": "..." }}
 
    SCENARIO 3: HUD / Augmented Intelligence (User wants facts, data, or context).
       - 'trigger_phrase': The exact words in the transcript to link this fact to.
       - 'title': Short title (e.g. "Stock Market 2008", "Bio-Data").
       - 'content': 1-2 sentences of verified fact or context about the topic.
       - 'type': "info" (Blue), "alert" (Red/Warning), "success" (Green/Verified).
       - Output: {{ "action": "hud", "title": "...", "content": "...", "type": "info", "trigger_phrase": "..." }}
    
    SCENARIO 4: 
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
    
    SCENARIO 5: User wants to change visual style (color, size, font).
    Output: {{ "action": "style", "new_style": {{ "font_color": "Yellow", "font_size": 30 }} }}
    (Only include fields that changed. Use standard CSS colors).

    SCENARIO 6: User wants to fix typos or change text.
    Output: {{ "action": "chat", "response": "I can help with that, but specific text editing is best done manually for now. Shall I change the style instead?" }}
   
    
    SCENARIO 7: General Chat.
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

        if decision.get("action") == "text_behind":
            text_content = decision.get("text_content", "TEXT")
            trigger = decision.get("trigger_phrase", "")
            props = decision.get("text_props", {})
            start, end = find_timestamp_for_phrase(state["subtitles"], trigger)
            
            if start == 0: start = 0; end = 5.0

            new_layer = {
                "id": str(len(current_text_layers) + 1),
                "start": start,
                "end": end,
                "text": text_content,
                "props": props 
            }
            
            return {
                "messages": [BaseMessage(content=f"Added Depth Text '{text_content}' at {start:.1f}s", type="ai")],
                "text_layers": current_text_layers + [new_layer]
            }

        elif decision.get("action") == "camera":
            trigger = decision.get("trigger_phrase", "")
            start, end = find_timestamp_for_phrase(state["subtitles"], trigger)
            
            if start == 0: start = 0; end = 3.0

            new_move = {
                "id": str(len(current_cam) + 1),
                "start": start,
                "end": end,
                "type": decision.get("type", "zoom-in"),
                "intensity": decision.get("intensity", 1.4)
            }
            
            return {
                "messages": [BaseMessage(content=f"Added Camera Move: {new_move['type']} at {start:.1f}s", type="ai")],
                "camera_moves": current_cam + [new_move]
            }

        elif decision.get("action") == "hud":
            trigger = decision.get("trigger_phrase", "")
            start, end = find_timestamp_for_phrase(state["subtitles"], trigger)
     
            if start == 0: 
                start = current_hud[-1]["end"] + 1 if current_hud else 0
                end = start + 4.0

            new_hud = {
                "id": str(len(current_hud) + 1),
                "start": start,
                "end": end,
                "title": decision.get("title", "Info"),
                "content": decision.get("content", ""),
                "type": decision.get("type", "info")
            }
            
            return {
                "messages": [BaseMessage(content=f"Added HUD Card: '{new_hud['title']}' at {start:.1f}s", type="ai")],
                "hud_items": current_hud + [new_hud] 
            }


        elif decision.get("action") == "visual":
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