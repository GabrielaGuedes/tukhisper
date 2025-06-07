import sys
import os
import threading
import sounddevice as sd
import soundfile as sf
import numpy as np
import whisper
import pyperclip
from pynput import keyboard
from PyQt5 import QtWidgets, QtGui, QtCore

# Set APP_DIR to the project root (one level up from src/)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_OUTPUT = os.path.expanduser('~/recorded.wav')

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(APP_DIR, relative_path)

class TraySignals(QtCore.QObject):
    show_message = QtCore.pyqtSignal(str, str, int)

class TranscriberTray(QtWidgets.QSystemTrayIcon):
    def __init__(self, icon, parent=None):
        super().__init__(icon, parent)
        self.menu = QtWidgets.QMenu(parent)
        self.language = 'en'  # Default language
        self.languages = {'English': 'en', 'Portuguese': 'pt'}
        self.language_actions = {}
        self.model = whisper.load_model('base')
        self.is_recording = False
        self.recording = []
        self.recording_thread = None
        self.samplerate = 44100
        self.channels = 1
        self.ctrl_pressed = False
        self.alt_pressed = False
        self.k_pressed = False
        self.listener_thread = None
        self.listening = False
        self.listener_stop_event = threading.Event()
        self.signals = TraySignals()
        self.signals.show_message.connect(self._show_message)
        self.setup_menu()
        self.setContextMenu(self.menu)
        self.setToolTip('Whisper Transcriber')
        self.set_flag_icon()
        self.start_listening()  # Start listening by default

    @QtCore.pyqtSlot(str, str, int)
    def _show_message(self, title, message, icon):
        self.showMessage(title, message, icon)

    def get_icon(self):
        if self.language == 'en':
            return QtGui.QIcon(resource_path(os.path.join('images', 'us.png')))
        elif self.language == 'pt':
            return QtGui.QIcon(resource_path(os.path.join('images', 'br.png')))
        else:
            print(f"Invalid language code: {self.language}")
            return QtGui.QIcon(resource_path(os.path.join('images', 'us.png')))

    def set_flag_icon(self):
        self.setIcon(self.get_icon())

    def setup_menu(self):
        self.start_action = QtWidgets.QAction('Start', self.menu)
        self.start_action.triggered.connect(self.start_listening)
        self.menu.addAction(self.start_action)
        self.stop_action = QtWidgets.QAction('Stop', self.menu)
        self.stop_action.triggered.connect(self.stop_listening)
        self.menu.addAction(self.stop_action)
        self.stop_action.setEnabled(False)
        lang_menu = self.menu.addMenu('Language')
        group = QtWidgets.QActionGroup(self.menu)
        for lang_name, lang_code in self.languages.items():
            action = QtWidgets.QAction(lang_name, self.menu, checkable=True)
            if lang_code == self.language:
                action.setChecked(True)
            action.triggered.connect(lambda checked, code=lang_code: self.set_language(code))
            group.addAction(action)
            lang_menu.addAction(action)
            self.language_actions[lang_code] = action
        self.menu.addSeparator()
        quit_action = QtWidgets.QAction('Quit', self.menu)
        quit_action.triggered.connect(QtWidgets.qApp.quit)
        self.menu.addAction(quit_action)

    def set_language(self, lang_code):
        self.language = lang_code
        for code, action in self.language_actions.items():
            action.setChecked(code == lang_code)
        self.set_flag_icon()

    def start_listening(self):
        if not self.listening:
            self.listener_stop_event.clear()
            self.listener_thread = threading.Thread(target=self.hotkey_listener, daemon=True)
            self.listener_thread.start()
            self.listening = True
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(True)
            self.set_flag_icon()

    def stop_listening(self):
        if self.listening:
            self.listener_stop_event.set()
            self.listening = False
            self.start_action.setEnabled(True)
            self.stop_action.setEnabled(False)
            self.setIcon(QtGui.QIcon(resource_path(os.path.join('images', 'micoff.png'))))

    def hotkey_listener(self):
        self.ctrl_pressed = False
        self.alt_pressed = False
        self.k_pressed = False
        def on_press(key):
            if self.listener_stop_event.is_set():
                return False
            if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                self.ctrl_pressed = True
            if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                self.alt_pressed = True
            if key == keyboard.KeyCode.from_char('k'):
                self.k_pressed = True
            if self.ctrl_pressed and self.alt_pressed and self.k_pressed:
                self.start_recording()
        def on_release(key):
            if self.listener_stop_event.is_set():
                return False
            if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                self.ctrl_pressed = False
            if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                self.alt_pressed = False
            if key == keyboard.KeyCode.from_char('k'):
                self.k_pressed = False
            if not (self.ctrl_pressed and self.alt_pressed and self.k_pressed):
                self.stop_recording()
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            while not self.listener_stop_event.is_set():
                listener.join(0.1)

    def record_audio(self):
        self.recording = []
        def callback(indata, frames, time, status):
            if self.is_recording:
                self.recording.append(indata.copy())
        with sd.InputStream(samplerate=self.samplerate, channels=self.channels, callback=callback):
            while self.is_recording:
                sd.sleep(100)

    def start_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.recording_thread = threading.Thread(target=self.record_audio, daemon=True)
            self.recording_thread.start()
            self.setIcon(QtGui.QIcon(resource_path(os.path.join('images', 'recording.png'))))

    def stop_recording(self):
        if self.is_recording:
            self.is_recording = False
            if self.recording_thread:
                self.recording_thread.join()
            self.setIcon(QtGui.QIcon(resource_path(os.path.join('images', 'transcribing.png'))))
            if self.recording:
                audio_np = np.concatenate(self.recording, axis=0)
                sf.write(AUDIO_OUTPUT, audio_np, self.samplerate)
                threading.Thread(target=self.transcribe_and_copy, daemon=True).start()
            else:
                print('No audio file found to transcribe.')
        self.set_flag_icon()

    def transcribe_and_copy(self):
        if os.path.exists(AUDIO_OUTPUT):
            result = self.model.transcribe(AUDIO_OUTPUT, language=self.language)
            text = result["text"]
            pyperclip.copy(text)
        else:
            print('No audio file found to transcribe.')
        self.set_flag_icon()

def main():
    app = QtWidgets.QApplication(sys.argv)
    icon = QtGui.QIcon(resource_path(os.path.join('images', 'us.png')))
    tray = TranscriberTray(icon)
    tray.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main() 