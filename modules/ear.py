import os
import sounddevice as sd
import numpy as np
from scipy.io import wavfile
from groq import Groq

class AudioEar:
    def __init__(self, api_key, sample_rate=16000):
        self.client = Groq(api_key=api_key)
        self.sample_rate = sample_rate
        self.temp_filename = "user_command.wav"
        
        # --- PARÁMETROS DE CALIBRACIÓN ACÚSTICA ---
        self.threshold = 0.02        # Umbral de volumen (RMS). Menos de esto es silencio.
        self.silence_limit = 1.5     # Segundos consecutivos de silencio antes de cortar.
        self.chunk_size = 1024       # Tamaño de cada bloque de lectura (muestras).

    def record_audio(self):
        """Abre un stream continuo de audio y corta automáticamente al detectar silencio."""
        print("🎙️ Josesito escuchando... Habla cuando quieras.")
        
        audio_frames = []
        silence_counter = 0
        has_spoken = False
        
        # Calculamos cuántos segundos representa cada 'chunk' en base al sample_rate
        chunk_duration = self.chunk_size / self.sample_rate

        # Abrimos el canal directo (Stream) con la tarjeta de sonido
        # Usamos float32 porque normaliza la onda entre -1.0 y 1.0, facilitando el cálculo matemático
        with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='float32', blocksize=self.chunk_size) as stream:
            while True:
                # 1. Leer un bloque de audio desde el hardware
                data, overflowed = stream.read(self.chunk_size)
                audio_frames.append(data.copy())
                
                # 2. Calcular la energía del bloque actual (RMS)
                rms = np.sqrt(np.mean(data**2))
                
                # 3. Lógica de la Máquina de Estados (VAD Casero)
                if rms > self.threshold:
                    if not has_spoken:
                        print("🗣️ ¡Voz detectada! Grabando...")
                        has_spoken = True
                    silence_counter = 0  # Reseteamos el contador porque el usuario sigue hablando
                else:
                    if has_spoken:
                        silence_counter += chunk_duration
                
                # 4. Condición de término: El usuario habló y luego se calló por el tiempo límite
                if has_spoken and silence_counter >= self.silence_limit:
                    print("🤫 Silencio detectado. Deteniendo grabación.")
                    break
        
        # Concatena todos los fragmentos leídos en un solo gran array de datos
        full_audio = np.concatenate(audio_frames, axis=0)
        
        # Para guardarlo como .wav estándar, transformamos los floats (-1 a 1) a enteros de 16 bits
        audio_int16 = (full_audio * 32767).astype(np.int16)
        
        # Guardar a disco de forma física
        wavfile.write(self.temp_filename, self.sample_rate, audio_int16)
        return self.temp_filename

    def transcribe_audio(self, file_path):
        """Manda el archivo generado a Whisper de Groq."""
        if not file_path or not os.path.exists(file_path):
            return ""

        try:
            with open(file_path, "rb") as file:
                transcription = self.client.audio.transcriptions.create(
                    file=(file_path, file.read()),
                    model="whisper-large-v3",
                    prompt="Conversación informal con un asistente inteligente llamado Josesito. "
                    "Se mencionan términos como Melipilla, El Bulla, Universidad de Chile, "
                    "Groq, API, prompt, software engineering, Pokémon, F1, NBA y modismos chilenos como cachái o al tiro.",
                    language="es"
                )
            os.remove(file_path)
            return transcription.text
        except Exception as e:
            print(f"❌ Error en Whisper: {e}")
            if os.path.exists(file_path): os.remove(file_path)
            return ""
        
    def calibrate_ambient_noise(self, duration=2.0):
        """
        Escucha el entorno durante un tiempo fijo para medir el ruido blanco base
        y calcular un umbral (threshold) de activación dinámico.
        """
        print(f"🤫 Calibrando ruido ambiental por {duration} segundos. Guarda silencio...")
        
        rms_values = []
        
        # Decisión de Diseño: Calculamos cuántos bloques (chunks) caben en la duración deseada.
        # Si duration = 2s y sample_rate = 16000Hz, necesitamos 32,000 muestras en total.
        # Dividido por chunk_size (1024), nos da aproximadamente 31 iteraciones en el bucle.
        total_chunks = int((duration * self.sample_rate) / self.chunk_size)
        
        # Abrimos el flujo de entrada de la tarjeta de sonido de forma idéntica a la grabación
        with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='float32', blocksize=self.chunk_size) as stream:
            for _ in range(total_chunks):
                data, overflowed = stream.read(self.chunk_size)
                
                # Calculamos la energía RMS de este bloque de "silencio"
                rms = np.sqrt(np.mean(data**2))
                rms_values.append(rms)
                
        # Calculamos el promedio matemático de todo el ruido de fondo capturado
        ambient_noise_average = np.mean(rms_values)
        
        # DECISIÓN DE INGENIERÍA (El Factor de Tolerancia):
        # Si dejamos el threshold exactamente igual al ruido promedio, cualquier mínimo soplido o el eco
        # de la pieza activaría la grabación. Multiplicarlo por 1.5 crea un "colchón de seguridad" ideal.
        self.threshold = ambient_noise_average * 1.5
        
        # Guardafrenos (Safe Guard): Si tu habitación es extremadamente silenciosa, el RMS podría dar casi 0.
        # Un umbral demasiado bajo causaría que el micrófono se active con el simple hecho de que respires.
        if self.threshold < 0.005:
            self.threshold = 0.005
            
        print(f"✅ Calibración completada con éxito:")
        print(f"   - Ruido base promedio: {ambient_noise_average:.5f}")
        print(f"   - Umbral dinámico fijado en (Threshold): {self.threshold:.5f}\n")