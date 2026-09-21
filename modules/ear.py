import os
import sys
import time as time_mod

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from scipy.io import wavfile

from config import (
    DURACION_MAX_GRABACION,
    MODELO_TRANSCRIPCION,
    PAUSA_SILENCIO,
    UMBRAL_MINIMO_RMS,
    VOCABULARIO_PERSONAL,
)


def _abortar_por_tecla():
    """Devuelve True si se pulsó ESC (solo Windows, con msvcrt)."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import msvcrt

        if msvcrt.kbhit():
            return ord(msvcrt.getch()) == 27
    except ImportError:
        pass
    return False


class AudioEar:
    def __init__(
        self,
        api_key,
        sample_rate=16000,
        modelo_transcripcion=MODELO_TRANSCRIPCION,
    ):
        self.client = genai.Client(api_key=api_key)
        self.modelo_transcripcion = modelo_transcripcion
        self.sample_rate = sample_rate
        self.temp_filename = "user_command.wav"

        self.threshold = 0.02
        self.silence_limit = PAUSA_SILENCIO
        self.chunk_size = 1024
        self.max_duration = DURACION_MAX_GRABACION

    # -------------------------------------------------------------- grabación

    def record_audio(self):
        """Graba mientras hay voz y corta por silencio, tiempo máximo o ESC.

        Devuelve la ruta del WAV, o None si se abortó (ESC) o no se detectó voz.
        """
        print("🎙️ Josesito escuchando... Habla cuando quieras.")
        audio_frames = []
        silence_counter = 0.0
        has_spoken = False
        abortado = False
        frames_leidos = 0

        chunk_duration = self.chunk_size / self.sample_rate
        max_chunks = int(self.max_duration / chunk_duration)

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.chunk_size,
        ) as stream:
            while True:
                data, overflowed = stream.read(self.chunk_size)
                if overflowed:
                    print("⚠️ overflow de micrófono (bloque perdido).")
                audio_frames.append(data.copy())
                frames_leidos += 1

                rms = float(np.sqrt(np.mean(data**2)))

                if rms > self.threshold:
                    if not has_spoken:
                        print("🗣️ ¡Voz detectada! Grabando...")
                        has_spoken = True
                    silence_counter = 0.0
                elif has_spoken:
                    silence_counter += chunk_duration

                if has_spoken and silence_counter >= self.silence_limit:
                    print("🤫 Silencio detectado. Deteniendo grabación.")
                    break
                if frames_leidos >= max_chunks:
                    print("⏱️ Límite de duración alcanzado. Deteniendo grabación.")
                    break
                if _abortar_por_tecla():
                    print("⛔ Abortado por teclado (ESC).")
                    abortado = True
                    break

        if abortado or not has_spoken:
            if not has_spoken:
                print("⚠️ No se detectó voz útil.")
            return None

        full_audio = np.concatenate(audio_frames, axis=0)
        audio_int16 = np.clip(full_audio * 32767, -32768, 32767).astype(np.int16)
        wavfile.write(self.temp_filename, self.sample_rate, audio_int16)
        return self.temp_filename

    # ----------------------------------------------------------- transcripción

    def transcribe_audio(self, file_path):
        """Transcribe un WAV con el modelo de transcripción de Gemini."""
        if not file_path or not os.path.exists(file_path):
            return ""
        try:
            with open(file_path, "rb") as archivo:
                audio_bytes = archivo.read()

            response = self.client.models.generate_content(
                model=self.modelo_transcripcion,
                contents=[types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")],
                config=types.GenerateContentConfig(
                    audio_transcription_config=types.AudioTranscriptionConfig(
                        language_codes=["es-CL"],
                        custom_vocabulary=VOCABULARIO_PERSONAL,
                    )
                ),
            )
            return (getattr(response, "text", "") or "").strip()
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Error en transcripción: {exc}")
            return ""
        finally:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

    # ------------------------------------------------------- calibración ruido

    def calibrate_ambient_noise(self, duration=2.0):
        """Mide el ruido ambiente y fija un umbral dinámico de activación."""
        print(f"🤫 Calibrando ruido ambiental por {duration} segundos. Guarda silencio...")

        rms_values = []
        total_chunks = int((duration * self.sample_rate) / self.chunk_size)

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.chunk_size,
        ) as stream:
            for _ in range(total_chunks):
                data, _overflowed = stream.read(self.chunk_size)
                rms = float(np.sqrt(np.mean(data**2)))
                rms_values.append(rms)
                if _abortar_por_tecla():
                    break

        ambient_noise_average = float(np.mean(rms_values)) if rms_values else 0.0
        self.threshold = ambient_noise_average * 1.5
        if self.threshold < UMBRAL_MINIMO_RMS:
            self.threshold = UMBRAL_MINIMO_RMS

        print(f"✅ Calibración completada:")
        print(f"   - Ruido base promedio: {ambient_noise_average:.5f}")
        print(f"   - Umbral dinámico fijado: {self.threshold:.5f}\n")