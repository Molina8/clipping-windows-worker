import json

body = {
    "job_type": "transcribe",
    "payload": {
        "video": r"C:\CODIANT\clipping\test_video.mp4",
        "language": "es",
        "options": {
            "model": "large-v3",
            "device": "cuda",
            "compute_type": "float16",
            "batch_size": 16,
            "align": True,
        },
    },
    "priority": 5,
}

with open("body.json", "w", encoding="utf-8") as f:
    json.dump(body, f, ensure_ascii=False)

print("WROTE:", open("body.json", encoding="utf-8").read())
