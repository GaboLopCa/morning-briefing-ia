import os
import time
import re
import asyncio
import pygame
import edge_tts

class VoiceAssistant:
    def __init__(self, speed):
        # El formato de velocidad para edge-tts es "+50%" para x1.5, "+70%" para x1.7, etc.
        percentage = int((speed - 1.0) * 100)
        self.speed_str = f"+{percentage}%" if percentage >= 0 else f"{percentage}%"
        self.voice = "es-CL-LorenzoNeural"
        pygame.mixer.init()

    def clean_text(self, text):
        text = re.sub(r'https?://\S+', '', text)
        text = text.replace('*', '').replace('#', '')
        return " ".join(text.split())

    async def _generate_audio(self, text, output_file):
        communicate = edge_tts.Communicate(text, self.voice, rate=self.speed_str)
        await communicate.save(output_file)

    def speak(self, text):
        text = self.clean_text(text)
        temp_file = "speech_output.mp3"

        try:
            # 1. Generar audio (necesita ser ejecutado en el loop de asyncio)
            asyncio.run(self._generate_audio(text, temp_file))

            # 2. Reproducir
            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()

            print(f"🔊 Assistant speaking (Edge-TTS) at {self.speed_str} speed...")
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)

            pygame.mixer.music.unload()

        except Exception as e:
            print(f"Error in voice module: {e}")
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)