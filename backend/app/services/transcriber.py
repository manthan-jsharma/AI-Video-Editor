import whisper
import warnings
import torch


warnings.filterwarnings("ignore")

def transcribe_video(video_path: str):
    model = whisper.load_model("base", device="cpu")
    
    print("Whisper running with word timestamps...")
    result = model.transcribe(video_path, fp16=False, word_timestamps=True)

    
    segments = []
    for seg in result["segments"]:
        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip(),
            "words": seg.get("words", []) 
        })
        
    return segments