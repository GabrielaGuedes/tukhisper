import os
import threading
import sounddevice as sd
import soundfile as sf
from pynput import keyboard
import numpy as np
import whisper
import pyperclip

AUDIO_OUTPUT = os.path.expanduser('~/recorded.wav')

recording = []
recording_thread = None
is_recording = False
samplerate = 44100
channels = 1

ctrl_pressed = False
alt_pressed = False
k_pressed = False

model = whisper.load_model('base')

def record_audio():
    global recording, is_recording
    recording = []
    def callback(indata, frames, time, status):
        if is_recording:
            recording.append(indata.copy())
    with sd.InputStream(samplerate=samplerate, channels=channels, callback=callback):
        while is_recording:
            sd.sleep(100)

def start_recording():
    global is_recording, recording_thread
    if not is_recording:
        is_recording = True
        recording_thread = threading.Thread(target=record_audio, daemon=True)
        recording_thread.start()
        print('Recording...')

def transcribe_and_copy():
    if os.path.exists(AUDIO_OUTPUT):
        print('Transcribing...')
        result = model.transcribe(AUDIO_OUTPUT)
        text = result["text"]
        print('Transcription:', text)
        pyperclip.copy(text)
        print('Transcription copied to clipboard.')
    else:
        print('No audio file found to transcribe.')

def stop_recording():
    global is_recording, recording_thread
    if is_recording:
        is_recording = False
        if recording_thread:
            recording_thread.join()
        if recording:
            audio_np = np.concatenate(recording, axis=0)
            sf.write(AUDIO_OUTPUT, audio_np, samplerate)
            print(f'Recording saved to {AUDIO_OUTPUT}')
            transcribe_and_copy()
        else:
            print('No audio recorded.')

def check_and_start():
    if ctrl_pressed and alt_pressed and k_pressed:
        start_recording()

def check_and_stop():
    if not (ctrl_pressed and alt_pressed and k_pressed):
        stop_recording()

def on_press(key):
    global ctrl_pressed, alt_pressed, k_pressed
    if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        ctrl_pressed = True
    if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
        alt_pressed = True
    if key == keyboard.KeyCode.from_char('k'):
        k_pressed = True
    check_and_start()

def on_release(key):
    global ctrl_pressed, alt_pressed, k_pressed
    if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        ctrl_pressed = False
    if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
        alt_pressed = False
    if key == keyboard.KeyCode.from_char('k'):
        k_pressed = False
    check_and_stop()

keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)

print('Hold Ctrl + Alt + K to record. Release any to stop. Transcription will be copied to clipboard.')
keyboard_listener.start()
keyboard_listener.join() 