import asyncio
import websockets
import json
import vosk
import soundfile as sf
import base64
import os

# Load Vosk model (download from https://alphacephei.com/vosk/models)
model = vosk.Model("vosk-model-small-en-us-0.15")
rec = vosk.KaldiRecognizer(model, 8000)  # 8kHz for phone audio

async def handler(websocket, path):
    # Simple health check endpoint
    if path == "/health":
        await websocket.send("OK")
        return
        
    print("🔗 Twilio connected, streaming audio...")

    async for message in websocket:
        data = json.loads(message)

        # Only care about audio packets
        if data["event"] == "media":
            # Twilio sends base64 audio (mulaw PCM, 8kHz)
            audio_chunk = base64.b64decode(data["media"]["payload"])
            
            if rec.AcceptWaveform(audio_chunk):
                result = json.loads(rec.Result())
                if result.get("text"):
                    print("🗣 Caller:", result["text"])
            else:
                partial = json.loads(rec.PartialResult())
                if partial.get("partial"):
                    print("…", partial["partial"])

        elif data["event"] == "start":
            print("📞 Call started")
        elif data["event"] == "stop":
            print("❌ Call ended")

async def main():
    # Get port from environment variable (Render sets this automatically)
    port = int(os.getenv("PORT", 5000))
    host = "0.0.0.0"
    
    print(f"🚀 Starting WebSocket server on {host}:{port}")
    async with websockets.serve(handler, host, port):
        print("✅ Server is ready for Twilio connections")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
