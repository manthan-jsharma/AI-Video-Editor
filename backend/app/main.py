import os
import uuid
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.services.video_utils import burn_subtitles
from fastapi.responses import FileResponse
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
        "visuals": [],
        "hud_items": [],
        "camera_moves": [],
        "text_layers": [],
        "messages": []
    }
    
    SESSIONS[session_id] = initial_state
    
    return {
        "session_id": session_id,
        "video_url": f"http://127.0.0.1:8000/static/{session_id}_{file.filename}",
        "subtitles": subtitles,
        "visuals": [],
        "hud_items": [],
        "camera_moves": [],
        "text_layers": [],
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
    if "visuals" in result:
        SESSIONS[req.session_id]["visuals"] = result["visuals"]  
    if "hud_items" in result:
        SESSIONS[req.session_id]["hud_items"] = result["hud_items"]
    if "camera_moves" in result:
        SESSIONS[req.session_id]["camera_moves"] = result["camera_moves"]    
    if "text_layers" in result:
        SESSIONS[req.session_id]["text_layers"] = result["text_layers"]     
        
    final_state = SESSIONS[req.session_id]
    
    return {
        "reply": result["messages"][-1].content,
        "updated_style": final_state["style"],
        "updated_subtitles": final_state["subtitles"],
        "updated_visuals": final_state.get("visuals", []),
        "updated_hud": final_state.get("hud_items", []),
        "updated_camera": final_state.get("camera_moves", []),
        "updated_text_layers": final_state.get("text_layers", [])

    }

@app.post("/export")
async def export_video(req: ChatRequest):
    session_id = req.session_id
    if session_id not in SESSIONS:
        raise HTTPException(404, "Session not found")
        
    state = SESSIONS[session_id]
    
    input_path = state["video_path"]
    output_filename = f"burned_{os.path.basename(input_path)}"
    output_path = f"processed/{output_filename}"
    
    success = burn_subtitles(input_path, state["subtitles"], state["style"], output_path)
    
    if not success:
        raise HTTPException(500, "Video processing failed")
        
    return {"download_url": f"[http://127.0.0.1:8000/download/](http://127.0.0.1:8000/download/){output_filename}"}

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = f"processed/{filename}"
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="video/mp4", filename=filename)
    raise HTTPException(404, "File not found")