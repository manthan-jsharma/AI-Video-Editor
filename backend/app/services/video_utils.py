import ffmpeg
import os

def generate_srt(subtitles, output_path):
    """
    Converts our JSON subtitle list into a formatted .srt file string
    """
    def format_time(seconds):
        """Converts seconds (12.5) to SRT time format (00:00:12,500)"""
        millis = int((seconds % 1) * 1000)
        seconds = int(seconds)
        mins, secs = divmod(seconds, 60)
        hrs, mins = divmod(mins, 60)
        return f"{hrs:02}:{mins:02}:{secs:02},{millis:03}"

    with open(output_path, 'w', encoding='utf-8') as f:
        for i, sub in enumerate(subtitles):
            start = format_time(sub['start'])
            end = format_time(sub['end'])
            text = sub['text']
            
            f.write(f"{i+1}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n\n")

def burn_subtitles(video_path, subtitles, style, output_path):
   
    srt_path = video_path.replace(".mp4", ".srt")
    generate_srt(subtitles, srt_path)
    
    font_size = style.get('font_size', 24)
    color_map = {
        "white": "&HFFFFFF",
        "yellow": "&H00FFFF",
        "red": "&H0000FF",
        "black": "&H000000"
    }
    font_color = color_map.get(style.get('font_color', 'white').lower(), "&HFFFFFF")

    style_str = f"FontSize={font_size},PrimaryColour={font_color},BorderStyle=1,Outline=1,Shadow=0"
    
    try:
        stream = ffmpeg.input(video_path)
        stream = ffmpeg.output(stream, output_path, vf=f"subtitles={srt_path}:force_style='{style_str}'")
        ffmpeg.run(stream, overwrite_output=True)
        return True
    except ffmpeg.Error as e:
        print("FFmpeg Error:", e.stderr)
        return False