import os
import uuid
import time
import shutil
import urllib.parse
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.schemas import ChatRequest
from app.services.transcriber import transcribe_video
from app.services.video_utils import burn_subtitles, remove_silence_and_fillers
from app.agent.graph import graph

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
TEMP_DIR = BASE_DIR / "temp"
PROCESSED_DIR = BASE_DIR / "processed"
SESSIONS_FILE = BASE_DIR / "sessions.json"

TEMP_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(TEMP_DIR)), name="static")

def load_sessions():
    """Loads session history from JSON file on startup."""
    if SESSIONS_FILE.exists():
        try:
            with open(SESSIONS_FILE, "r") as f:
                print("📂 Loaded previous sessions from disk.")
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to load sessions: {e}")
    return {}

def save_sessions():
    """Saves current session state to JSON file."""
    try:
        with open(SESSIONS_FILE, "w") as f:
            json.dump(SESSIONS, f, indent=4)
    except Exception as e:
        print(f"⚠️ Failed to save sessions: {e}")

SESSIONS = load_sessions()

def sanitize_filename(name: str) -> str:
    return "".join([c if c.isalnum() or c in "._-" else "_" for c in name])

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    clean_name = sanitize_filename(file.filename)
    file_path = TEMP_DIR / f"{session_id}_{clean_name}"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    print(f"Transcribing {clean_name}...")
    subtitles = transcribe_video(str(file_path))
    
    initial_state = {
        "video_path": str(file_path),
        "subtitles": subtitles,
        "visuals": [], 
        "hud_items": [],
        "text_layers": [],
        "bg_layers": [],
        "camera_moves": [],
        "style": {"font_color": "white", "font_size": 24, "position": "bottom"},
        "messages": []
    }
    
    SESSIONS[session_id] = initial_state
    save_sessions()
    
    return {
        "session_id": session_id,
        "video_url": f"http://127.0.0.1:8000/static/{file_path.name}",
        "subtitles": subtitles,
        "visuals": [],
        "hud_items": [],
        "style": initial_state["style"]
    }

@app.post("/chat")
async def chat_agent(req: ChatRequest):
    global SESSIONS
    
    if req.session_id not in SESSIONS:
        SESSIONS = load_sessions()
        if req.session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        
    current_state = SESSIONS[req.session_id]
    
    from langchain_core.messages import HumanMessage
    inputs = {
        **current_state,
        "messages": [HumanMessage(content=req.prompt)]
    }
    
    result = graph.invoke(inputs)
    
    if result.get("pending_operation") == "auto_cut":
        print("✂️ TRIGGERING MAGIC CUT...")
        
        old_path = current_state["video_path"]
        filename = Path(old_path).name
        new_filename = f"cut_{filename}"
        new_path = TEMP_DIR / new_filename
    
        success = remove_silence_and_fillers(old_path, str(new_path))
        
        if success:
            print("✅ Cut successful. Updating session...")
            SESSIONS[req.session_id]["video_path"] = str(new_path)
            print("🔄 Re-transcribing...")
            new_subs = transcribe_video(str(new_path))
            SESSIONS[req.session_id]["subtitles"] = new_subs
            
            SESSIONS[req.session_id]["visuals"] = []
            SESSIONS[req.session_id]["text_layers"] = []
            SESSIONS[req.session_id]["camera_moves"] = []
            SESSIONS[req.session_id]["hud_items"] = []
            SESSIONS[req.session_id]["bg_layers"] = []
            
            save_sessions()
            
            return {
                "reply": "I've removed the silence! The video has been shortened and subtitles re-synced.",
                "updated_subtitles": new_subs,
                "updated_visuals": [],
                "updated_text_layers": [],
                "video_url": f"http://127.0.0.1:8000/static/{new_filename}",
                "force_refresh": True 
            }
        else:
             return {
                "reply": "I tried to remove silence, but I couldn't find any significant pauses to cut.",
                "updated_style": current_state["style"]
            }
    if "style" in result: SESSIONS[req.session_id]["style"] = result["style"]
    if "subtitles" in result: SESSIONS[req.session_id]["subtitles"] = result["subtitles"]
    if "visuals" in result: SESSIONS[req.session_id]["visuals"] = result["visuals"]
    if "text_layers" in result: SESSIONS[req.session_id]["text_layers"] = result["text_layers"]
    if "bg_layers" in result: SESSIONS[req.session_id]["bg_layers"] = result["bg_layers"]
    if "hud_items" in result: SESSIONS[req.session_id]["hud_items"] = result["hud_items"]
    if "camera_moves" in result: SESSIONS[req.session_id]["camera_moves"] = result["camera_moves"]
        
    save_sessions()
    final_state = SESSIONS[req.session_id]
    
    return {
        "reply": result["messages"][-1].content,
        "updated_style": final_state["style"],
        "updated_subtitles": final_state["subtitles"],
        "updated_visuals": final_state.get("visuals", []),
        "updated_text_layers": final_state.get("text_layers", []),
        "updated_bg_layers": final_state.get("bg_layers", []),
        "updated_hud": final_state.get("hud_items", []),
        "updated_camera": final_state.get("camera_moves", [])
    }

@app.post("/export")
async def export_video(req: ChatRequest):
    global SESSIONS
    session_id = req.session_id
    
    if session_id not in SESSIONS:
        SESSIONS = load_sessions()
        if session_id not in SESSIONS:
            raise HTTPException(404, "Session not found")
        
    state = SESSIONS[session_id]
    input_path = state.get("video_path")
    
    if not input_path:
        raise HTTPException(500, "Video path missing in session")

    original_name = Path(input_path).name
    output_filename = f"burned_{original_name}"
    output_path = PROCESSED_DIR / output_filename

    
    print(f"🎬 Request to Export: {output_path}")
    
    success = burn_subtitles(input_path, state["subtitles"], state["style"], str(output_path))
    
    if not success:
        raise HTTPException(500, "Video processing failed inside FFmpeg")
        
    safe_filename = urllib.parse.quote(output_filename)
    return {"download_url": f"http://127.0.0.1:8000/download/{safe_filename}"}

@app.get("/download/{filename}")
async def download_file(filename: str):
    decoded_filename = urllib.parse.unquote(filename)
    file_path = PROCESSED_DIR / decoded_filename
    
    print(f"📂 Serving File: {file_path}")
    
    if not file_path.exists():
        print(f"❌ File Missing at: {file_path}")
        raise HTTPException(404, f"File not found on server: {decoded_filename}")
        
    return FileResponse(path=file_path, media_type="video/mp4", filename=decoded_filename)