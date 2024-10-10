import os
import queue
import sys
import sounddevice as sd
import vosk
import json

def list_models(base_path):
    """List available models in the base path."""
    try:
        return [folder for folder in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, folder))]
    except FileNotFoundError:
        print(f"Directory {base_path} not found.")
        sys.exit(1)

def select_model(base_path):
    """CLI-like selection of the model."""
    models = list_models(base_path)
    if not models:
        print("No models found in the specified directory.")
        sys.exit(1)
    
    print("Available models:")
    for idx, model_name in enumerate(models):
        print(f"{idx + 1}. {model_name}")
    
    choice = input("Select the model by number: ")
    try:
        model_idx = int(choice) - 1
        if model_idx not in range(len(models)):
            raise ValueError
        return models[model_idx]
    except ValueError:
        print("Invalid selection.")
        sys.exit(1)

# Base path to the models
model_base_path = "../lang/models/"

# Select model dynamically
model_folder = select_model(model_base_path)
model_path = os.path.join(model_base_path, model_folder)

if not os.path.exists(model_path):
    print("Model not found at", model_path)
    sys.exit(1)

# Load the Vosk model
model = vosk.Model(model_path)

# Define a queue to hold audio data
audio_queue = queue.Queue()

def callback(indata, frames, time, status):
    """Callback function to read the audio buffer."""
    if status:
        print(status, file=sys.stderr)
    audio_queue.put(bytes(indata))

def main():
    # Define audio stream parameters
    device_info = sd.query_devices(None, 'input')
    print(device_info)
    sample_rate = int(device_info['default_samplerate'])

    # Open an audio stream
    with sd.RawInputStream(samplerate=sample_rate, blocksize=16000, dtype='int16',
                           channels=1, callback=callback):
        print("Listening...")
        rec = vosk.KaldiRecognizer(model, sample_rate)
        while True:
            data = audio_queue.get()
            if rec.AcceptWaveform(data):
                result = rec.Result()
                text = json.loads(result)['text']
                print(f"Recognized: {text}")
            else:
                partial_result = rec.PartialResult()
                print(f"Partial: {json.loads(partial_result)['partial']}")

if __name__ == "__main__":
    main()
