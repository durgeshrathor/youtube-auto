import os, json, random, subprocess, asyncio, pathlib, glob
import requests, edge_tts

NICHE = os.getenv("NICHE", "amazing facts")
CONTENT_LANG = os.getenv("CONTENT_LANG", "Hindi")
VOICE = os.getenv("VOICE", "hi-IN-MadhurNeural")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
FONT = os.getenv("FONT", "Noto Sans Devanagari")
PRIVACY = os.getenv("PRIVACY", "public")
CATEGORY = os.getenv("CATEGORY", "27")  # 27 = Education, 24 = Entertainment
SYNTHETIC = os.getenv("SYNTHETIC", "false").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
PIXABAY = os.getenv("PIXABAY_API_KEY")
PEXELS = os.getenv("PEXELS_API_KEY")

WORK = pathlib.Path("work")
WORK.mkdir(exist_ok=True)


def run(cmd):
    subprocess.run(cmd, check=True, cwd=WORK)


# ---------- 1. Script (Gemini) ----------
def gemini_script(history):
    prompt = f"""You are a top YouTube Shorts scriptwriter for a channel about: {NICHE}.
Narration language: {CONTENT_LANG}.
Write ONE new video. Do NOT repeat these earlier topics: {history}

Rules:
- First sentence is a strong curiosity hook (under 10 words).
- Short, simple, spoken sentences. One single idea.
- Total narration 110-130 words (about 45 seconds).
- 6 to 8 scenes.
- Only true, verifiable facts. No made-up numbers.
- Last scene ends with a question to make people comment.

Return ONLY JSON in this exact shape:
{{"title": "catchy title in {CONTENT_LANG}, under 80 chars",
 "description": "2-3 lines in {CONTENT_LANG} with keywords",
 "tags": ["tag1", "tag2", "... 8 to 12 tags"],
 "scenes": [{{"narration": "text in {CONTENT_LANG}",
              "keyword": "1-3 ENGLISH words for a concrete stock-video visual, e.g. 'ocean waves'"}}]}}"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    last = None
    for _ in range(3):
        try:
            r = requests.post(
                url, params={"key": GEMINI_KEY}, timeout=120,
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0}})
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(text)
            assert data["scenes"] and data["title"]
            return data
        except Exception as e:
            last = e
            print("Gemini retry:", e)
    raise RuntimeError(f"Gemini failed: {last}")


# ---------- 2. Voice (edge-tts) ----------
async def tts_scene(text, path):
    try:
        comm = edge_tts.Communicate(text, VOICE, rate="+5%", boundary="WordBoundary")
    except TypeError:
        comm = edge_tts.Communicate(text, VOICE, rate="+5%")
    words = []
    with open(path, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
    return words


def duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)])
    return float(out)


# ---------- 3. Stock clips ----------
def search_clips(keyword):
    urls = []
    if PIXABAY:
        try:
            r = requests.get("https://pixabay.com/api/videos/", timeout=30,
                             params={"key": PIXABAY, "q": keyword, "per_page": 20, "safesearch": "true"})
            for h in r.json().get("hits", []):
                v = h["videos"]
                pick = v.get("medium") or v.get("small")
                if pick and pick.get("url"):
                    urls.append(pick["url"])
        except Exception as e:
            print("Pixabay error:", e)
    if PEXELS and not urls:
        try:
            r = requests.get("https://api.pexels.com/videos/search", timeout=30,
                             headers={"Authorization": PEXELS},
                             params={"query": keyword, "orientation": "portrait", "per_page": 15})
            for v in r.json().get("videos", []):
                files = [f for f in v["video_files"] if f.get("width", 0) <= 1080]
                if files:
                    urls.append(max(files, key=lambda f: f["width"])["link"])
        except Exception as e:
            print("Pexels error:", e)
    return urls


def get_clip(keyword, i, used):
    for q in [keyword, keyword.split()[0], "nature"]:
        urls = [u for u in search_clips(q) if u not in used]
        if urls:
            url = random.choice(urls[:8])
            used.add(url)
            path = WORK / f"clip{i}.mp4"
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            return path.name
    return None


def build_scene(i, clip, dur):
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"
    enc = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
    if clip:
        src = ["-stream_loop", "-1", "-i", clip]
    else:
        src = ["-f", "lavfi", "-i", "color=c=0x101820:s=1080x1920:r=30"]
    run(["ffmpeg", "-y", "-loglevel", "error", *src, "-t", f"{dur:.3f}", "-vf", vf, *enc, f"scene{i}.mp4"])


# ---------- 4. Captions (ASS) ----------
HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},84,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,2,2,60,60,520,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ass_time(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def make_ass(scene_words, durs):
    lines, t0 = [], 0.0
    for words, dur in zip(scene_words, durs):
        for k in range(0, len(words), 3):
            g = words[k:k + 3]
            start = t0 + g[0][0]
            nxt = words[k + 3][0] if k + 3 < len(words) else dur
            end = max(t0 + nxt, start + 0.25)
            text = " ".join(w[2] for w in g).replace("{", "").replace("}", "")
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}")
        t0 += dur
    return HEADER + "\n".join(lines) + "\n"


# ---------- 5. Upload ----------
def upload(path, data):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials(
        None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    yt = build("youtube", "v3", credentials=creds)
    tags, total = [], 0
    for t in data.get("tags", []):
        total += len(t) + 1
        if total < 450:
            tags.append(t)
    body = {
        "snippet": {"title": data["title"][:95],
                    "description": data.get("description", "") + "\n\n#Shorts",
                    "tags": tags, "categoryId": CATEGORY},
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": SYNTHETIC},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(path), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]


# ---------- main ----------
def main():
    hist_file = pathlib.Path("topics.json")
    history = json.loads(hist_file.read_text()) if hist_file.exists() else []

    data = gemini_script(history[-60:])
    scenes = data["scenes"][:8]
    print("Title:", data["title"])

    scene_words, durs, used = [], [], set()
    for i, sc in enumerate(scenes):
        apath = WORK / f"voice{i}.mp3"
        words = asyncio.run(tts_scene(sc["narration"], apath))
        dur = duration(apath)
        if not words:  # fallback: words evenly spread
            ws = sc["narration"].split()
            step = dur / max(len(ws), 1)
            words = [(j * step, step, w) for j, w in enumerate(ws)]
        scene_words.append(words)
        durs.append(dur)
        clip = get_clip(sc.get("keyword", "nature"), i, used)
        build_scene(i, clip, dur)
        print(f"Scene {i}: {dur:.1f}s clip={clip}")

    (WORK / "list_v.txt").write_text("".join(f"file 'scene{i}.mp4'\n" for i in range(len(scenes))))
    (WORK / "list_a.txt").write_text("".join(f"file 'voice{i}.mp3'\n" for i in range(len(scenes))))
    (WORK / "subs.ass").write_text(make_ass(scene_words, durs), encoding="utf-8")

    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list_v.txt", "-c", "copy", "video_raw.mp4"])
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list_a.txt", "-c:a", "aac", "-b:a", "192k", "voice.m4a"])
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", "video_raw.mp4", "-vf", "ass=subs.ass",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "video_sub.mp4"])

    music = glob.glob("music/*.mp3")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", "video_sub.mp4", "-i", "voice.m4a"]
    if music:
        m = str(pathlib.Path(random.choice(music)).resolve())
        cmd += ["-stream_loop", "-1", "-i", m, "-filter_complex",
                "[2:a]volume=0.10[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "final.mp4"]
    run(cmd)
    print("Video ready: work/final.mp4")

    if DRY_RUN:
        print("DRY_RUN: upload skipped")
        return
    vid = upload(WORK / "final.mp4", data)
    print("Uploaded: https://youtube.com/shorts/" + vid)
    history.append(data["title"])
    hist_file.write_text(json.dumps(history, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
