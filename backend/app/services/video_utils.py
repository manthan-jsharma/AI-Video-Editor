import ffmpeg
import os
import sys
import re
import subprocess

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


def remove_silence_and_fillers(input_path, output_path, filler_intervals=[], db_threshold=-30, min_duration=0.5):
  
    input_path = os.path.abspath(input_path)
    output_path = os.path.abspath(output_path)

    print("Detecting silence...")
    try:
        cmd = [
            "ffmpeg", "-i", input_path, 
            "-af", f"silencedetect=noise={db_threshold}dB:d={min_duration}", 
            "-f", "null", "-"
        ]
        result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        log = result.stderr
    except Exception as e:
        print(f"Detection failed: {e}")
        return False

    silence_starts = [float(x) for x in re.findall(r'silence_start: ([\d\.]+)', log)]
    silence_ends = [float(x) for x in re.findall(r'silence_end: ([\d\.]+)', log)]
    
    remove_list = []
    count = min(len(silence_starts), len(silence_ends))
    for i in range(count):
        remove_list.append((silence_starts[i], silence_ends[i]))
        
    if filler_intervals:
        print(f"➕ Adding {len(filler_intervals)} filler word cuts...")
        remove_list.extend(filler_intervals)

    if not remove_list:
        print("⚠️ No silence or fillers found to remove.")
        return False

    remove_list.sort(key=lambda x: x[0])
    
    merged_removals = []
    if remove_list:
        curr_start, curr_end = remove_list[0]
        for next_start, next_end in remove_list[1:]:
            if next_start < curr_end: 
                curr_end = max(curr_end, next_end)
            else:
                merged_removals.append((curr_start, curr_end))
                curr_start, curr_end = next_start, next_end
        merged_removals.append((curr_start, curr_end))

    duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", log)
    if not duration_match: return False
    h, m, s = map(float, duration_match.groups())
    total_duration = h * 3600 + m * 60 + s

    keep_segments = []
    current_time = 0.0
    
    for start, end in merged_removals:
        if start > current_time:
            keep_segments.append((current_time, start))
        current_time = end
        
    if current_time < total_duration:
        keep_segments.append((current_time, total_duration))

    print(f"✂️ Stitching {len(keep_segments)} clean segments...")

    input_stream = ffmpeg.input(input_path)
    streams = []
    
    for i, (start, end) in enumerate(keep_segments):
        v = input_stream.video.trim(start=start, end=end).setpts('PTS-STARTPTS')
        a = input_stream.audio.filter_('atrim', start=start, end=end).filter_('asetpts', 'PTS-STARTPTS')
        streams.extend([v, a])

    try:
        joined = ffmpeg.concat(*streams, v=1, a=1).node
        out = ffmpeg.output(joined[0], joined[1], output_path)
        out.run(overwrite_output=True, capture_stderr=True)
        print("Magic Cut Complete!")
        return True
    except ffmpeg.Error as e:
        print("Stitching Error:", e.stderr.decode('utf-8'))
        return False