import asyncio
import websockets
import json
import vosk
import soundfile as sf
import base64

# Load Vosk model (download from https://alphacephei.com/vosk/models)
model = vosk.Model("vosk-model-small-en-us-0.15")
rec = vosk.KaldiRecognizer(model, 8000)  # 8kHz for phone audio

async def handler(websocket, path):
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
    async with websockets.serve(handler, "0.0.0.0", 5000):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
