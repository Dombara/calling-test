import asyncio
import json
import vosk
import base64
import os
from aiohttp import web, WSMsgType, BasicAuth
import aiohttp_cors
import aiohttp
from datetime import datetime

# Exotel API Configuration
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY", "e7786f65cb027a24d88347d91e41f01670e012c7348f1d41")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN", "71f7e40edcc6cdaf89fa780b445bcdaae89217d3670993b3b")
EXOTEL_SID = os.getenv("EXOTEL_SID", "cbc161")
EXOTEL_SUBDOMAIN = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")

# Load Vosk model
model = vosk.Model("vosk-model-small-en-us-0.15")
rec = vosk.KaldiRecognizer(model, 8000)

print("Exotel API configured")
print(f"Account SID: {EXOTEL_SID}")
print(f"API Key: {EXOTEL_API_KEY[:10]}...")
print(f"API Token: {EXOTEL_API_TOKEN[:10]}...")

async def voice_webhook(request):
    """HTTP endpoint for Exotel Voice webhook"""
    try:
        data = await request.post()
    except:
        data = await request.json()
    
    call_sid = data.get('CallSid', 'Unknown')
    caller_number = data.get('From', 'Unknown')
    called_number = data.get('To', 'Unknown')
    call_status = data.get('CallStatus', 'in-progress')
    
    print(f"\nExotel Call Status: {call_status}")
    print(f"Call from {caller_number} to {called_number} (CallSid: {call_sid})")
    
    # Exotel uses XML responses
    exotel_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Hello! Your call is being recorded and will be transcribed.</Say>
    <Record action="https://calling-test-2kdd.onrender.com/recording" 
            method="POST" 
            maxLength="3600" 
            finishOnKey="#"
            recordSession="true">
    </Record>
    <Say>Thank you for your call. Goodbye!</Say>
</Response>'''
    
    return web.Response(text=exotel_response, content_type='text/xml')

async def recording_webhook(request):
    """Handle recording completion from Exotel"""
    try:
        data = await request.post()
    except:
        data = await request.json()
    
    call_sid = data.get('CallSid', 'Unknown')
    recording_url = data.get('RecordingUrl', '')
    recording_duration = data.get('RecordingDuration', '0')
    
    print(f"\nExotel recording completed for CallSid: {call_sid}")
    print(f"Duration: {recording_duration} seconds")
    print(f"Recording URL: {recording_url}")
    
    if recording_url:
        asyncio.create_task(process_recording(recording_url, call_sid))
    
    return web.Response(text='<?xml version="1.0" encoding="UTF-8"?><Response></Response>', content_type='text/xml')

async def process_recording(recording_url, call_sid):
    """Download and process the recorded audio file"""
    print(f"Processing recording for CallSid: {call_sid}")
    
    try:
        # Exotel authentication using API Key and Token
        auth = BasicAuth(EXOTEL_API_KEY, EXOTEL_API_TOKEN)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(recording_url, auth=auth) as response:
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
        "service": "Exotel Speech Recognition Server",
        "account_sid": EXOTEL_SID,
        "vosk_model": "vosk-model-small-en-us-0.15",
        "exotel_configured": bool(EXOTEL_API_KEY and EXOTEL_API_TOKEN)
    })

async def websocket_handler(request):
    """WebSocket handler for Exotel Media Streams"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    print("🔗 Exotel Media Stream connected...")

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
                
                # Only care about audio packets
                if data["event"] == "media":
                    # Exotel sends base64 audio (mulaw PCM, 8kHz)
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
    
    print("Exotel Speech Recognition Server Starting")
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
