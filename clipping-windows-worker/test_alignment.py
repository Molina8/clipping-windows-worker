import whisperx

video = r"C:\CODIANT\clipping\test_video.mp4"

print("Loading audio...")
audio = whisperx.load_audio(video)

print("Loading model...")
model = whisperx.load_model(
    "small",
    device="cuda",
    compute_type="float16"
)

print("Transcribing...")
result = model.transcribe(audio, batch_size=16)

print("Loading alignment model...")
model_a, metadata = whisperx.load_align_model(
    language_code=result["language"],
    device="cuda"
)

print("Aligning words...")
aligned = whisperx.align(
    result["segments"],
    model_a,
    metadata,
    audio,
    "cuda",
    return_char_alignments=False
)

print("\n--- FIRST WORDS WITH TIMESTAMPS ---")

words = [
    w
    for segment in aligned["segments"]
    for w in segment.get("words", [])
]

for w in words[:80]:
    print(
        f"{w.get('start', 0):7.2f}s -> "
        f"{w.get('end', 0):7.2f}s | "
        f"{w.get('word', '')}"
    )

print(f"\nAligned words: {len(words)}")
