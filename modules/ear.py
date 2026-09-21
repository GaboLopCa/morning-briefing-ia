import os
import sys

import numpy as np
import sounddevice as sd
from groq import Groq

from config import (
    DURACION_MAX_GRABACION,
    MODELO_TRANSCRIPCION,
    PAUSA_SILENCIO,
    UMBRAL_MINIMO_RMS,
)

from modules.recorder import Grabadora, nivel_rms


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


def transcribir(api_key, file_path, modelo=MODELO_TRANSCRIPCION):
    """Transcribe un WAV con Whisper de Groq (`whisper-large-v3-turbo`).

    Función standalone (sin prints) para reutilizarla desde el segundo plano;
    borra el WAV en `finally`. Devuelve texto o "" si no hay archivo o falla.
    """
    if not file_path or not os.path.exists(file_path):
        return ""
    try:
        client = Groq(api_key=api_key)
        with open(file_path, "rb") as archivo:
            transcripcion = client.audio.transcriptions.create(
                model=modelo,
                file=(os.path.basename(file_path), archivo, "audio/wav"),
                language="es",
                response_format="text",
            )
        return str(transcripcion or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Error en transcripción: {exc}")
        return ""
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


class AudioEar:
    def __init__(
        self,
        api_key,
        sample_rate=16000,
        modelo_transcripcion=MODELO_TRANSCRIPCION,
    ):
        self.client = Groq(api_key=api_key)
        self.modelo_transcripcion = modelo_transcripcion
        self.sample_rate = sample_rate

        self.threshold = 0.02
        self.silence_limit = PAUSA_SILENCIO
        self.chunk_size = 1024
        self.max_duration = DURACION_MAX_GRABACION

    # -------------------------------------------------------------- grabación

    def record_audio(self):
        """Graba mientras hay voz y corta por silencio, tiempo máximo o ESC.

        Reutiliza `modules.recorder.dresGrabadora` (mismo VAD que el segundo
        plano) y escribe el WAV en el temp del SO. Devuelve la ruta del WAV,
        o None si se abortó (ESC) o no se detectó voz.
        """
        print("🎙️ Josesito escuchando... Habla cuando quieras.")
        grabadora = Grabadora(
            tasa=self.sample_rate,
            umbral=self.threshold,
            pausa=self.silence_limit,
            tope=self.max_duration,
        )
        grabadora.comenzar()

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.chunk_size,
        ) as stream:
            while not grabadora.esta_lista():
                data, overflowed = stream.read(self.chunk_size)
                if overflowed:
                    print("⚠️ overflow de micrófono (bloque perdido).")
                bloque_int16 = np.clip(data * 32767, -32768, 32767).astype(np.int16).reshape(-1)
                grabadora.alimentar(bloque_int16)
                if _abortar_por_tecla():
                    print("⛔ Abortado por teclado (ESC).")
                    return None

        if grabadora.ruta_wav is not None:
            print("🤫 Silencio o límite alcanzado. Deteniendo grabación.")
            return grabadora.ruta_wav
        print("⚠️ No se detectó voz útil.")
        return None

    # ----------------------------------------------------------- transcripción

    def transcribe_audio(self, file_path):
        """Transcribe un WAV (delega en `transcribir` y borra el archivo)."""
        return transcribir(self.client.api_key, file_path, self.modelo_transcripcion)

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