import numpy as np
import sounddevice as sd
from collections import deque
import io
import wave
import logging
from numba import jit
from config import Config

@jit(nopython=True, fastmath=True)
def calculate_rms_numba(buffer):
    return np.sqrt(np.mean(np.square(buffer)))

class AudioAnalyzer:
    def __init__(self, sample_rate=48000, history_size=5):
        self.sample_rate = sample_rate
        self.buffer = deque(maxlen=sample_rate * 10)  # 10 секундный буфер
        self.stream = None
        self.volume_history = deque(maxlen=history_size)
        self.active = False
        print("🔹 Анализатор аудио инициализирован")
        
    def start(self):
        if self.active:
            return
            
        def callback(indata, frames, time, status):
            if self.active:
                self.buffer.extend(indata[:, 0])
            
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype='float32',
            callback=callback
        )
        self.stream.start()
        self.active = True
        print("🔹 Аудиопоток запущен")
        
    def stop(self):
        if self.stream and self.active:
            self.stream.stop()
            self.stream.close()
            self.active = False
            print("🔹 Аудиопоток остановлен")
            
    def calculate_volume(self):
        if len(self.buffer) == 0:
            return 0
            
        audio_array = np.array(self.buffer)
        rms = calculate_rms_numba(audio_array)
        dB = 20 * np.log10(rms) if rms > 0 else -100
        calibrated_dB = dB + Config.DB_CALIBRATION
        
        self.volume_history.append(calibrated_dB)
        return calibrated_dB
        
    def get_average_volume(self):
        if len(self.volume_history) == 0:
            return 0
        return np.mean(self.volume_history)
    
    def reset_history(self):
        self.volume_history.clear()
        print("🔹 История громкости сброшена")
        
    def get_audio_data(self, duration=2.0):
        samples_needed = int(self.sample_rate * duration)
        if len(self.buffer) < samples_needed:
            return None
            
        audio_data = np.array(list(self.buffer)[-samples_needed:])
        audio_data = (audio_data * 32767).astype(np.int16)
        
        with io.BytesIO() as wav_file:
            with wave.open(wav_file, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.sample_rate)
                wav.writeframes(audio_data.tobytes())
            return wav_file.getvalue()