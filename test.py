import asyncio
import websockets
import json
import vosk
import soundfile as sf
import base64
import os
from aiohttp import web, WSMsgType
import aiohttp_cors

# Load Vosk model (download from https://alphacephei.com/vosk/models)
model = vosk.Model("vosk-model-small-en-us-0.15")
rec = vosk.KaldiRecognizer(model, 8000)  # 8kHz for phone audio

async def voice_webhook(request):
    """HTTP endpoint for Twilio Voice webhook"""
    twiml_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Listen very carefully and note this down if possible.Viddhi is a chapri girl</Say>
    <Start>
        <Stream url="wss://calling-test-2kdd.onrender.com/stream"/>
    </Start>
    <Pause length="30"/>
</Response>'''
    
    return web.Response(text=twiml_response, content_type='text/xml')

async def health_check(request):
    """Health check endpoint"""
    return web.Response(text="Twilio Speech Recognition Server is running!")

async def websocket_handler(request):
    """WebSocket handler for Twilio Media Streams"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    print("🔗 Twilio Media Stream connected...")

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
                
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
                    
            except json.JSONDecodeError:
                print("❌ Invalid JSON received")
                
        elif msg.type == WSMsgType.ERROR:
            print(f'❌ WebSocket error: {ws.exception()}')
    
    print("🔌 WebSocket connection closed")
    return ws

async def main():
    # Get port from environment variable (Render sets this automatically)
    port = int(os.getenv("PORT", 5000))
    
    # Create aiohttp application
    app = web.Application()
    
    # Add CORS support
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    
    # Add routes
    app.router.add_get('/', health_check)
    app.router.add_post('/voice', voice_webhook)
    app.router.add_get('/stream', websocket_handler)
    
    # Add CORS to all routes
    for route in list(app.router.routes()):
        cors.add(route)
    
    print(f"🚀 Starting server on port {port}")
    print("✅ Server ready for:")
    print(f"   � Voice webhook: https://calling-test-2kdd.onrender.com/voice")
    print(f"   🎤 Media Stream: wss://calling-test-2kdd.onrender.com/stream")
    
    # Start the server
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    # Keep running
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
