import os
import uuid
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.schemas import ChatRequest
from app.services.transcriber import transcribe_video
from app.agent.graph import graph

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


SESSIONS = {} 

os.makedirs("temp", exist_ok=True)
os.makedirs("processed", exist_ok=True)


app.mount("/static", StaticFiles(directory="temp"), name="static")

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    file_path = f"temp/{session_id}_{file.filename}"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    print(f"Transcribing {file.filename}...")
    subtitles = transcribe_video(file_path)
    
    initial_state = {
        "video_path": file_path,
        "subtitles": subtitles,
        "style": {"font_color": "white", "font_size": 24, "position": "bottom"},
        "messages": []
    }
    
    SESSIONS[session_id] = initial_state
    
    return {
        "session_id": session_id,
        "video_url": f"http://127.0.0.1:8000/static/{session_id}_{file.filename}",
        "subtitles": subtitles,
        "style": initial_state["style"]
    }

@app.post("/chat")
async def chat_agent(req: ChatRequest):
    if req.session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
        
    current_state = SESSIONS[req.session_id]
    
    from langchain_core.messages import HumanMessage
    inputs = {
        **current_state,
        "messages": [HumanMessage(content=req.prompt)]
    }
    
    result = graph.invoke(inputs)
    
    if "style" in result:
        SESSIONS[req.session_id]["style"] = result["style"]
    if "subtitles" in result:
        SESSIONS[req.session_id]["subtitles"] = result["subtitles"]
        
    final_state = SESSIONS[req.session_id]
    
    return {
        "reply": result["messages"][-1].content,
        "updated_style": final_state["style"],
        "updated_subtitles": final_state["subtitles"]
    }