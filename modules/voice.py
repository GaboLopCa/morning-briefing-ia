import asyncio
import os
import re
import tempfile
import time as time_mod

import edge_tts
import pygame

from config import VARIANTE_VOZ, VOZ_RAPIDEZ


class VoiceAssistant:
    def __init__(self, velocidad=VOZ_RAPIDEZ, variante=VARIANTE_VOZ):
        porcentaje = int((velocidad - 1.0) * 100)
        self.speed_str = f"+{porcentaje}%" if porcentaje >= 0 else f"{porcentaje}%"
        self.voice = variante
        self._mixer_iniciado = False
        self._habilitado = True

    def clean_text(self, text):
        texto_limpio = re.sub(r"https?://\S+", "", text)
        texto_limpio = texto_limpio.replace("*", "").replace("#", "")
        return " ".join(texto_limpio.split())

    def _iniciar_mixer(self):
        """Inicializa pygame.mixer de forma perezosa y tolerante a fallos."""
        if self._mixer_iniciado:
            return True
        try:
            pygame.mixer.init()
            self._mixer_iniciado = True
            return True
        except pygame.error as exc:  # noqa: BLE001
            print(f"⚠️ Sin salida de audio ({exc}); Josesito responderá solo por texto.")
            self._habilitado = False
            return False

    async def _generate_audio(self, text, output_file):
        communicate = edge_tts.Communicate(text, self.voice, rate=self.speed_str)
        await communicate.save(output_file)

    def speak(self, text):
        if not self._habilitado:
            return
        text = self.clean_text(text)
        if not text.strip():
            return
        if not self._iniciar_mixer():
            return

        temp_file = os.path.join(tempfile.gettempdir(), f"speech_{os.getpid()}.mp3")
        try:
            asyncio.run(self._generate_audio(text, temp_file))

            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()
            print(f"🔊 Assistant speaking (Edge-TTS) at {self.speed_str} speed...")
            while pygame.mixer.music.get_busy():
                time_mod.sleep(0.1)
            pygame.mixer.music.unload()
        except Exception as exc:  # noqa: BLE001
            print(f"Error in voice module: {exc}")
        finally:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass