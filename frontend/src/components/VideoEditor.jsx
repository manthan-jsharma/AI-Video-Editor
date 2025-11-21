import React, { useState, useRef } from "react";
import ReactPlayer from "react-player";
import client from "../api/client";
import { Upload, Send, Download, Clapperboard, Sparkles } from "lucide-react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

const VideoEditor = () => {
  const [sessionId, setSessionId] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);
  const [subtitles, setSubtitles] = useState([]);
  const [style, setStyle] = useState({});
  const [visuals, setVisuals] = useState([]);
  const [chatHistory, setChatHistory] = useState([]);
  const [prompt, setPrompt] = useState("");

  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [loading, setLoading] = useState(false);

  const cn = (...inputs) => twMerge(clsx(inputs));

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setLoading(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await client.post("/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setSessionId(res.data.session_id);
      setVideoUrl(res.data.video_url);
      setSubtitles(res.data.subtitles);
      setStyle(res.data.style);
      setVisuals(res.data.visuals || []);
      setChatHistory([
        {
          role: "ai",
          content:
            'Director AI Ready! Try: "Show a cyberpunk city when I say Hello"',
        },
      ]);
    } catch (err) {
      console.error(err);
      alert("Upload failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleChat = async () => {
    if (!prompt.trim()) return;
    const newMsg = { role: "user", content: prompt };
    setChatHistory((prev) => [...prev, newMsg]);
    setPrompt("");
    try {
      const res = await client.post("/chat", {
        session_id: sessionId,
        prompt: newMsg.content,
      });
      setChatHistory((prev) => [
        ...prev,
        { role: "ai", content: res.data.reply },
      ]);
      if (res.data.updated_style) setStyle(res.data.updated_style);
      if (res.data.updated_subtitles) setSubtitles(res.data.updated_subtitles);
      if (res.data.updated_visuals) setVisuals(res.data.updated_visuals);
    } catch (err) {
      console.error(err);
    }
  };

  const handleExport = async () => {
    if (!sessionId) return;
    setChatHistory((prev) => [
      ...prev,
      { role: "ai", content: "Rendering..." },
    ]);
    try {
      const res = await client.post("/export", {
        session_id: sessionId,
        prompt: "export",
      });
      const link = document.createElement("a");
      link.href = res.data.download_url;
      link.setAttribute("download", "edited.mp4");
      document.body.appendChild(link);
      link.click();
      link.remove();
      setChatHistory((prev) => [
        ...prev,
        { role: "ai", content: "Download ready!" },
      ]);
    } catch (err) {
      alert("Export failed");
    }
  };

  const activeSub = subtitles.find(
    (s) => currentTime >= s.start && currentTime <= s.end
  );
  const activeVisuals =
    visuals?.filter((v) => currentTime >= v.start && currentTime <= v.end) ||
    [];

  const currentVisual =
    activeVisuals.length > 0 ? activeVisuals[activeVisuals.length - 1] : null;

  const getVisualStyles = (visual) => {
    const props = visual.props || {};
    const pos = props.position || "center";
    const anim = props.animation || "fade";
    const blend = props.blend_mode || "normal";

    const positions = {
      center: "inset-0 m-auto max-h-[80%] max-w-[80%]",
      "full-screen": "inset-0 w-full h-full",
      "top-right": "top-4 right-4 w-48 h-32",
      "top-left": "top-4 left-4 w-48 h-32",
      "bottom-right": "bottom-4 right-4 w-48 h-32",
      "bottom-left": "bottom-4 left-4 w-48 h-32",
    };

    const animations = {
      fade: "animate-[fadeIn_0.5s_ease-in-out]",
      pop: "animate-[ping_0.3s_ease-out_reverse]",
      slide: "animate-[bounce_1s_infinite]",
    };

    return {
      className: cn(
        "absolute z-50 rounded-lg overflow-hidden transition-all duration-500 shadow-2xl border border-white/10 pointer-events-none",
        positions[pos] || positions["center"],
        animations[anim]
      ),
      style: {
        mixBlendMode: blend,
        opacity: props.opacity || 1,
      },
    };
  };

  return (
    <div className="flex h-screen bg-[#0f0f0f] text-white font-sans overflow-hidden">
      <div className="flex-1 relative flex flex-col items-center justify-center bg-black p-4">
        {!videoUrl ? (
          <div className="text-center space-y-6">
            <div className="p-8 rounded-full bg-gray-800/50 inline-block animate-pulse">
              <Clapperboard size={64} className="text-blue-500" />
            </div>
            <div>
              <h2 className="text-2xl font-bold tracking-tight">
                AI Editing Studio
              </h2>
              <p className="text-gray-400 mt-2">
                Upload footage to start Editing
              </p>
            </div>
            <label className="cursor-pointer bg-blue-600 hover:bg-blue-500 px-8 py-3 rounded-xl font-medium flex items-center gap-2 transition-all mx-auto w-fit shadow-lg shadow-blue-900/20">
              <Upload size={20} />
              {loading ? "Analyzing Footage..." : "Select Video"}
              <input
                type="file"
                onChange={handleUpload}
                className="hidden"
                accept="video/*"
              />
            </label>
          </div>
        ) : (
          <div className="relative w-full max-w-6xl aspect-video bg-black shadow-2xl overflow-hidden border border-gray-800 rounded-xl group">
            <ReactPlayer
              url={videoUrl}
              playing={playing}
              controls={true}
              width="100%"
              height="100%"
              style={{ objectFit: "contain" }}
              onProgress={(p) => setCurrentTime(p.playedSeconds)}
            />

            {currentVisual &&
              (() => {
                const styles = getVisualStyles(currentVisual);
                return (
                  <div className={styles.className} style={styles.style}>
                    <img
                      src={currentVisual.url}
                      alt={currentVisual.keyword}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute bottom-2 right-2 bg-black/70 px-2 py-0.5 text-[10px] text-gray-300 rounded backdrop-blur-sm">
                      ✨ AI Gen
                    </div>
                  </div>
                );
              })()}
            {activeSub && (
              <div
                className="absolute w-full text-center z-40 pointer-events-none transition-all duration-300"
                style={{
                  bottom: style.position === "top" ? "85%" : "10%",
                  color: style.font_color,
                  fontSize: `${style.font_size}px`,
                  fontFamily: style.font_family || "Arial",
                  textShadow: "0px 2px 4px rgba(0,0,0,0.8)",
                }}
              >
                <span className="bg-black/50 px-4 py-2 rounded-lg backdrop-blur-md">
                  {activeSub.text}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="w-[400px] border-l border-gray-800 flex flex-col bg-[#1a1a1a]">
        <div className="p-4 border-b border-gray-800 flex justify-between items-center bg-[#202020]">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-yellow-400" />
            <span className="font-bold text-sm tracking-wide">
              DIRECTOR AGENT
            </span>
          </div>
          {videoUrl && (
            <button
              onClick={handleExport}
              className="text-xs bg-gray-700 hover:bg-gray-600 px-3 py-1.5 rounded text-gray-200 flex gap-2 transition-colors"
            >
              <Download size={14} /> Export
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {chatHistory.map((msg, i) => (
            <div
              key={i}
              className={`flex ${
                msg.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`max-w-[85%] p-3.5 rounded-2xl text-sm leading-relaxed shadow-md ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white rounded-tr-none"
                    : "bg-[#2a2a2a] text-gray-200 rounded-tl-none border border-gray-700"
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
        </div>

        <div className="p-4 bg-[#1a1a1a] border-t border-gray-800">
          <div className="relative">
            <input
              className="w-full bg-[#0f0f0f] text-white rounded-xl pl-4 pr-12 py-4 focus:outline-none focus:ring-1 focus:ring-blue-500/50 border border-gray-800 placeholder-gray-600 text-sm transition-all"
              placeholder="Ask: 'Show a dragon at top-right...'"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleChat()}
              disabled={!sessionId}
            />
            <button
              onClick={handleChat}
              disabled={!sessionId}
              className="absolute right-2 top-2.5 p-2 bg-blue-600 rounded-lg hover:bg-blue-500 transition-colors shadow-lg"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VideoEditor;
