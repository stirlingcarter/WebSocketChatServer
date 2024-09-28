import os
import sys
import json
import asyncio
import websockets
import logging
import multiprocessing
from vosk import Model, KaldiRecognizer
from openai import OpenAI
import uuid

# Read the API key from key.txt
with open('key.txt', 'r') as file:
    api_key = file.read().strip()

client = OpenAI(api_key=api_key)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Vosk Model
def load_model(base_path):
    try:
        model_folder = next(folder for folder in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, folder)))
        return Model(os.path.join(base_path, model_folder))
    except StopIteration:
        logger.error(f"No model found in {base_path}")
        sys.exit(1)

# Get recognized completion from OpenAI
async def get_recognized_completion(text):
    prompt = (
        "This is an STT result of a word or sentence(s).\n"
        "1. If you see something obvious (e.g., 'miss steak' instead of 'mistake'), please correct it.\n"
        "2. Show corrections inline with bold or strikethough, or other inline means.\n"
        "3. That's it, feel free not to touch it if it looks good.\n\n"
        f"STT result: {text}"
    )

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content

# Shared Queue to communicate between processes
async def receive_messages(websocket, rec, shared_queue, shared_uuid):
    async for message in websocket:
        if isinstance(message, bytes):
            if rec.AcceptWaveform(message):
                result = json.loads(rec.Result())['text']
                if result:
                    logger.info(f"Recognized: {result}")
                    
                    # Create JSON message for recognized text
                    recognized_msg = {
                        "msg": f"{result}",
                        "uuid": shared_uuid.value
                    }

                    shared_queue.put(json.dumps(recognized_msg))

                    completion_msg = {
                        "uuid": shared_uuid.value  # Same UUID as recognized
                    }
                    new_uuid = str(uuid.uuid4())
                    shared_uuid.value = new_uuid  # Update the shared UUID

                    # Run the completion in a separate coroutine
                    completion = await get_recognized_completion(result)
                    
                    logger.info(f"Completion: {completion}")
                    completion_msg["msg"] = f"{completion}"
                    shared_queue.put(json.dumps(completion_msg))
            else:
                partial_result = json.loads(rec.PartialResult())['partial']
                if partial_result:
                    logger.info(f"Partial: {partial_result}")
                    
                    # Use the current UUID for partial messages
                    partial_msg = {
                        "msg": f"{partial_result}",
                        "uuid": shared_uuid.value
                    }
                    shared_queue.put(json.dumps(partial_msg))
        else:
            logger.warning(f"Received non-bytes message: {message}")

async def publish_messages(websocket, shared_queue):
    while True:
        if not shared_queue.empty():
            message = shared_queue.get()
            await websocket.send(message)
            logger.info(f"Published message: {message}")
        else:
            await asyncio.sleep(0.1)  # Prevent busy waiting

def receive_process(shared_queue, shared_uuid, model):
    async def handler(websocket, path):
        rec = KaldiRecognizer(model, 16000)
        await receive_messages(websocket, rec, shared_queue, shared_uuid)

    start_server = websockets.serve(handler, "0.0.0.0", 8765)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

def publish_process(shared_queue):
    async def handler(websocket, path):
        await publish_messages(websocket, shared_queue)

    start_server = websockets.serve(handler, "0.0.0.0", 8766)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
    manager = multiprocessing.Manager()
    shared_queue = manager.Queue()
    shared_uuid = manager.Value('c', str(uuid.uuid4()))  # Initialize with a random UUID

    model = load_model("../lang/models/")

    # Create and start processes
    receive_p = multiprocessing.Process(target=receive_process, args=(shared_queue, shared_uuid, model))
    publish_p = multiprocessing.Process(target=publish_process, args=(shared_queue,))

    receive_p.start()
    publish_p.start()

    receive_p.join()
    publish_p.join()
