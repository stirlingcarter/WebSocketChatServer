import asyncio
import websockets
import sounddevice as sd

# WebSocket server URL
WS_URL = "ws://18.144.94.245:8765"  # Replace with your EC2 instance IP

# Configure audio stream parameters
SAMPLE_RATE = 16000  # Ensure this matches the recognizer's expectation
CHANNELS = 1
BLOCKSIZE = 8000  # Adjust depending on desired chunk size and performance

async def send_audio_chunk(websocket, data):
    """Send audio chunk to the WebSocket."""
    await websocket.send(data)

def callback(indata, frames, time, status, websocket, loop):
    """Callback function to send audio chunks via WebSocket."""
    if status:
        print(f"Audio status: {status}")

    # Correctly convert the CFFI buffer to bytes
    data = bytes(indata)

    # Schedule the coroutine to send data using run_coroutine_threadsafe
    asyncio.run_coroutine_threadsafe(send_audio_chunk(websocket, data), loop)


async def send_audio(websocket):
    """Stream audio from the microphone and send it to the WebSocket server."""
    
    loop = asyncio.get_event_loop()  # Get the current event loop

    async def receive_messages():
        """Receive messages from the websocket to process ping/pong frames."""
        try:
            async for message in websocket:
                # Process messages if necessary
                pass
        except websockets.exceptions.ConnectionClosed:
            pass

    # Start the receive_messages task
    receive_task = asyncio.create_task(receive_messages())

    # Open an audio stream
    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCKSIZE, dtype='int16',
                           channels=CHANNELS, callback=lambda indata, frames, time, status: callback(indata, frames, time, status, websocket, loop)):
        print("Streaming audio...")
        try:
            await asyncio.Future()  # Keep the stream open until interrupted
        except asyncio.CancelledError:
            pass

    # When done, cancel the receive task
    receive_task.cancel()


async def connect_to_server():
    """Connect to the WebSocket server and initiate audio streaming."""
    async with websockets.connect(WS_URL) as websocket:
        print(f"Connected to WebSocket server at {WS_URL}")
        await send_audio(websocket)

if __name__ == "__main__":
    try:
        asyncio.run(connect_to_server())
    except KeyboardInterrupt:
        print("Connection closed.")
