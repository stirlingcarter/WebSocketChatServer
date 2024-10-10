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
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Device name
DEVICE_NAME = "cuke"  # Define your device name here

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

def receive_process(shared_queue, shared_data):
    """Process that records audio and sends transcriptions to the shared queue."""
    import queue  # Thread-safe queue

    while True:
        current_language = shared_data['language']
        current_uuid = shared_data['uuid']
        user_uuid = shared_data['user_uuid']

        # Initialize Google Speech client with credentials
        client = speech.SpeechClient(credentials=credentials)

        # Configure recognition settings
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,  # Raw 16-bit signed LE samples
            sample_rate_hertz=RATE,
            language_code=current_language,
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
            logger.info(f"Microphone stream started with language: {current_language}")

            # Create a generator that reads from the queue
            def generator():
                while True:
                    data = audio_queue.get()
                    if data is None:
                        break
                    yield speech.StreamingRecognizeRequest(audio_content=data)
                    # Check if language has changed
                    if shared_data['language'] != current_language:
                        logger.info(f"Language changed to {shared_data['language']}, restarting recognition.")
                        break

            # Start the streaming recognition
            requests = generator()
            responses = client.streaming_recognize(streaming_config, requests)
            previous_health_check_ts = time.time()
            health_msg = {
                "type": 3,
                "id": "health",
                "userId": user_uuid,
                "uuid": "123",
                "lang": "en",
                "isHealthCheck": True,
                "msg": " ",
                "deviceId": DEVICE_NAME
            }
            # Process the responses
            try:
                for response in responses:
                    # send health
                    if (time.time() - previous_health_check_ts > 9):
                        shared_queue.put(json.dumps(health_msg))
                        previous_health_check_ts = time.time()
                        print(json.dumps(health_msg))
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
                            "userId": user_uuid,
                            "type": 1,  # Type 1 for final results
                            "deviceId": DEVICE_NAME if first_char_before_m(shared_data['uuid']) else "carrot",
                            "msg": transcript,
                            "uuid": shared_data['uuid'],
                            "lang": current_language
                        }
                        shared_queue.put(json.dumps(recognized_msg))

                        # Update UUID for the next message
                        new_uuid = str(uuid.uuid4())
                        shared_data['uuid'] = new_uuid
                    else:
                        # Interim transcription result
                        logger.info(f"Partial: {transcript}")

                        partial_msg = {
                            "userId": user_uuid,
                            "type": 0,  # Type 0 for interim results
                            "deviceId": DEVICE_NAME if first_char_before_m(shared_data['uuid']) else "carrot",
                            "msg": transcript,
                            "uuid": shared_data['uuid'],
                            "lang": current_language
                        }
                        shared_queue.put(json.dumps(partial_msg))

                    # Check if language has changed
                    if shared_data['language'] != current_language:
                        logger.info(f"Language changed to {shared_data['language']}, restarting recognition.")
                        break

            except Exception as e:
                logger.error(f"Exception in receive_process: {e}")
            # At this point, the outer while loop restarts

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

def language_receiver_process(shared_data):
    """Process that listens for language change commands over a separate WebSocket."""
    valid_languages = {'en', 'fr', 'es', 'de', 'it', 'pt', 'zh', 'ja', 'ko'}  # Define valid languages

    async def receive_language_commands(websocket, path):
        async for message in websocket:
            try:
                data = json.loads(message)
                for device_id, lang_code in data.items():
                    if device_id == DEVICE_NAME:
                        # Check if lang_code is valid
                        if lang_code in valid_languages:
                            shared_data['language'] = lang_code
                            logger.info(f"Language for {DEVICE_NAME} changed to {lang_code}")
                        else:
                            logger.warning(f"Received invalid language code: {lang_code}")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {message}")
            except Exception as e:
                logger.error(f"Exception in receive_language_commands: {e}")

    # Start the WebSocket server on a different port (e.g., 8767)
    start_server = websockets.serve(receive_language_commands, "0.0.0.0", 8767)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
    # Manager for shared resources between processes
    manager = multiprocessing.Manager()
    shared_queue = manager.Queue()
    shared_data = manager.dict()
    shared_data['uuid'] = str(uuid.uuid4())  # Shared UUID
    shared_data['user_uuid'] = str(uuid.uuid4())  # User UUID
    shared_data['language'] = 'en'  # Default language is 'en'

    # Create and start the receive, publish, and language receiver processes
    receive_p = multiprocessing.Process(
        target=receive_process, args=(shared_queue, shared_data)
    )
    publish_p = multiprocessing.Process(
        target=publish_process, args=(shared_queue,)
    )
    language_receiver_p = multiprocessing.Process(
        target=language_receiver_process, args=(shared_data,)
    )

    receive_p.start()
    publish_p.start()
    language_receiver_p.start()

    receive_p.join()
    publish_p.join()
    language_receiver_p.join()
