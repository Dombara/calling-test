import asyncio
import json
import vosk
import base64
import os
from aiohttp import web, WSMsgType, BasicAuth
import aiohttp_cors
import aiohttp
from datetime import datetime

# EnableX API Configuration
ENABLEX_APP_ID = os.getenv("ENABLEX_APP_ID", "your_enablex_app_id")
ENABLEX_APP_KEY = os.getenv("ENABLEX_APP_KEY", "your_enablex_app_key")
ENABLEX_API_URL = os.getenv("ENABLEX_API_URL", "https://api.enablex.io/voice/v1")

# Load Vosk model
model = vosk.Model("vosk-model-small-en-us-0.15")
rec = vosk.KaldiRecognizer(model, 8000)

print("EnableX API configured")
print(f"App ID: {ENABLEX_APP_ID}")
print(f"App Key: {ENABLEX_APP_KEY[:10]}..." if len(ENABLEX_APP_KEY) > 10 else "Not configured")

async def voice_webhook(request):
    """HTTP endpoint for EnableX Voice webhook"""
    try:
        data = await request.json()
    except:
        data = await request.post()
    
    call_id = data.get('call_id', data.get('uuid', 'Unknown'))
    caller_number = data.get('from', data.get('caller_id', 'Unknown'))
    called_number = data.get('to', data.get('called_id', 'Unknown'))
    event = data.get('event', 'incoming')
    
    print(f"\nEnableX Event: {event}")
    print(f"Call from {caller_number} to {called_number} (Call ID: {call_id})")
    
    # EnableX uses JSON responses with actions
    enablex_response = {
        "action": [
            {
                "type": "play",
                "text": "Hello! Your call is being recorded and will be transcribed.",
                "voice": "female",
                "language": "en-US"
            },
            {
                "type": "record",
                "max_duration": 3600,
                "timeout": 10,
                "trim_silence": True,
                "format": "wav",
                "recording_url": "https://calling-test-2kdd.onrender.com/recording"
            },
            {
                "type": "play",
                "text": "Thank you for your call. Goodbye.",
                "voice": "female",
                "language": "en-US"
            },
            {
                "type": "hangup"
            }
        ]
    }
    
    return web.json_response(enablex_response)

async def recording_webhook(request):
    """Handle recording completion from EnableX"""
    try:
        data = await request.json()
    except:
        data = await request.post()
    
    call_id = data.get('call_id', data.get('uuid', 'Unknown'))
    recording_url = data.get('recording_url', data.get('url', ''))
    recording_duration = data.get('duration', data.get('recording_duration', '0'))
    
    print(f"\nEnableX recording completed for Call ID: {call_id}")
    print(f"Duration: {recording_duration} seconds")
    print(f"Recording URL: {recording_url}")
    
    if recording_url:
        asyncio.create_task(process_recording(recording_url, call_id))
    
    return web.json_response({"status": "ok", "message": "Recording received"})

async def process_recording(recording_url, call_sid):
    """Download and process the recorded audio file"""
    print(f"Processing recording for Call ID: {call_sid}")
    
    try:
        # EnableX authentication using App ID and App Key
        headers = {
            "Authorization": f"Basic {base64.b64encode(f'{ENABLEX_APP_ID}:{ENABLEX_APP_KEY}'.encode()).decode()}"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(recording_url, headers=headers) as response:
                if response.status == 200:
                    audio_data = await response.read()
                    print(f"Downloaded {len(audio_data)} bytes")
                    
                    temp_file = f"recording_{call_sid}.wav"
                    with open(temp_file, 'wb') as f:
                        f.write(audio_data)
                    
                    await transcribe_audio_file(temp_file, call_sid)
                    
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                else:
                    print(f"Failed to download. Status: {response.status}")
                    
    except Exception as e:
        print(f"Error processing recording: {e}")

async def transcribe_audio_file(audio_file_path, call_sid):
    """Transcribe an audio file using Vosk"""
    try:
        import wave
        
        print(f"Starting transcription for Call ID: {call_sid}")
        
        wf = wave.open(audio_file_path, 'rb')
        rec_file = vosk.KaldiRecognizer(model, wf.getframerate())
        
        results = []
        
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
                
            if rec_file.AcceptWaveform(data):
                result = json.loads(rec_file.Result())
                if result.get("text"):
                    results.append(result["text"])
                    print(f"Transcription: {result['text']}")
        
        final_result = json.loads(rec_file.FinalResult())
        if final_result.get("text"):
            results.append(final_result["text"])
        
        wf.close()
        
        full_transcription = " ".join(results)
        print(f"Full transcription for {call_sid}: {full_transcription}")
        
        filename = f"transcription_{call_sid}.txt"
        with open(filename, 'w') as f:
            f.write(f"Call ID: {call_sid}\n")
            f.write(f"Transcription: {full_transcription}\n")
        print(f"Transcription saved to: {filename}")
        
    except Exception as e:
        print(f"Error transcribing: {e}")

async def health_check(request):
    """Health check endpoint"""
    return web.json_response({
        "status": "running", 
        "service": "EnableX Speech Recognition Server",
        "vosk_model": "vosk-model-small-en-us-0.15",
        "enablex_configured": bool(ENABLEX_APP_ID and ENABLEX_APP_KEY)
    })

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
    app.router.add_post('/webhook', voice_webhook)
    app.router.add_post('/event', voice_webhook)
    app.router.add_post('/recording', recording_webhook)
    app.router.add_get('/stream', websocket_handler)
    
    # Add CORS to all routes
    for route in list(app.router.routes()):
        cors.add(route)
    
    print("EnableX Speech Recognition Server Starting")
    print(f"Port: {port}")
    print(f"Main webhook: https://calling-test-2kdd.onrender.com/webhook")
    print(f"Voice webhook: https://calling-test-2kdd.onrender.com/voice")
    print(f"Event webhook: https://calling-test-2kdd.onrender.com/event")
    print(f"Recording webhook: https://calling-test-2kdd.onrender.com/recording")
    print("Server ready!")
    
    # Start the server
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    # Keep running
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
