import os
import sys
import json
import asyncio
import websockets
import logging
import multiprocessing
import uuid
import sounddevice as sd
import queue  # For thread-safe queue
from google.cloud import speech
from google.oauth2 import service_account

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Audio recording parameters
RATE = 16000  # Sampling rate in Hertz
CHUNK = int(RATE / 10)  # Size of each audio chunk (100ms)

# Read the path to the Google Cloud service account key file from key.txt
with open('key.txt', 'r') as file:
    google_key_path = file.read().strip()

# Set up Google Cloud credentials
credentials = service_account.Credentials.from_service_account_file('key.txt')

def first_char_before_m(s):
    """
    Returns True if the first character of the string `s` comes before 'm' alphabetically.
    Case-insensitive comparison.
    """
    if not s:
        return False
    first_char = s[0].lower()
    if not first_char.isalpha():
        return False
    return first_char < 'm'

def receive_process(shared_queue, shared_uuid, user_uuid):
    """Process that records audio and sends transcriptions to the shared queue."""
    import queue  # Thread-safe queue

    # Initialize Google Speech client with credentials
    client = speech.SpeechClient(credentials=credentials)

    # Configure recognition settings
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,  # Raw 16-bit signed LE samples
        sample_rate_hertz=RATE,
        language_code="en-US",
    )

    streaming_config = speech.StreamingRecognitionConfig(
        config=config,
        interim_results=True  # Receive interim results as they become available
    )

    audio_queue = queue.Queue()

    # Define the callback for sounddevice
    def sd_callback(indata, frames, time, status):
        if status:
            logger.warning(f"Sounddevice status: {status}")
        # Put the audio data into the queue
        audio_queue.put(bytes(indata))

    # Open the sounddevice stream
    with sd.RawInputStream(samplerate=RATE, blocksize=CHUNK, dtype='int16',
                           channels=1, callback=sd_callback):
        logger.info("Microphone stream started")

        # Create a generator that reads from the queue
        def generator():
            while True:
                data = audio_queue.get()
                if data is None:
                    break
                yield speech.StreamingRecognizeRequest(audio_content=data)

        # Start the streaming recognition
        requests = generator()
        responses = client.streaming_recognize(streaming_config, requests)

        # Process the responses
        try:
            for response in responses:
                if not response.results:
                    continue
                result = response.results[0]
                if not result.alternatives:
                    continue
                transcript = result.alternatives[0].transcript

                if result.is_final:
                    # Final transcription result
                    logger.info(f"Recognized: {transcript}")

                    recognized_msg = {
                        "userId": user_uuid.value,
                        "type": 1,  # Type 1 for final results
                        "deviceId": "cuke" if first_char_before_m(shared_uuid.value) else "carrot",
                        "msg": transcript,
                        "uuid": shared_uuid.value,
                        "lang": "en"
                    }
                    shared_queue.put(json.dumps(recognized_msg))

                    # Update UUID for the next message
                    new_uuid = str(uuid.uuid4())
                    shared_uuid.value = new_uuid
                else:
                    # Interim transcription result
                    logger.info(f"Partial: {transcript}")

                    partial_msg = {
                        "userId": user_uuid.value,
                        "type": 0,  # Type 0 for interim results
                        "deviceId": "cuke" if first_char_before_m(shared_uuid.value) else "carrot",
                        "msg": transcript,
                        "uuid": shared_uuid.value,
                        "lang": "en"
                    }
                    shared_queue.put(json.dumps(partial_msg))
        except Exception as e:
            logger.error(f"Exception in receive_process: {e}")

def publish_process(shared_queue):
    """Process that sends messages from the shared queue over a WebSocket."""
    async def publish_messages(websocket, path):
        while True:
            if not shared_queue.empty():
                message = shared_queue.get()
                await websocket.send(message)
                logger.info(f"Published message: {message}")
            else:
                await asyncio.sleep(0.1)  # Sleep briefly to prevent busy waiting

    # Start the WebSocket server
    start_server = websockets.serve(publish_messages, "0.0.0.0", 8766)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
    # Manager for shared resources between processes
    manager = multiprocessing.Manager()
    shared_queue = manager.Queue()
    shared_uuid = manager.Value('c', str(uuid.uuid4()))  # Shared UUID
    user_uuid = manager.Value('c', str(uuid.uuid4()))  # User UUID

    # Create and start the receive and publish processes
    receive_p = multiprocessing.Process(
        target=receive_process, args=(shared_queue, shared_uuid, user_uuid)
    )
    publish_p = multiprocessing.Process(
        target=publish_process, args=(shared_queue,)
    )

    receive_p.start()
    publish_p.start()

    receive_p.join()
    publish_p.join()
