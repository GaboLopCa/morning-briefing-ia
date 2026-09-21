"""Tool que delega tareas de programación al CLI de opencode (modo headless).

Ejecuta `opencode run --dir <ruta> "<peticion>"`. El usuario debe confirmar
antes de cualquier ejecución (callback inyectado desde main.py).
"""
import shutil
import subprocess
import sys

from config import OPENCODE_PROYECTOS, OPENCODE_SALIDA_MAX, OPENCODE_TIMEOUT
from modules.contract import error, ok

COMANDO = "opencode"


class OpenCodeRunner:
    def __init__(self, confirmador):
        # confirmador(peticion: str, ruta: str) -> bool
        self.confirmador = confirmador
        self.proyectos = OPENCODE_PROYECTOS

    def _flags_ocultar_consola(self):
        if sys.platform.startswith("win"):
            return subprocess.CREATE_NO_WINDOW
        return 0

    def _binario(self):
        return shutil.which(COMANDO)

    def ejecutar(self, *, proyecto, peticion):
        ruta = self.proyectos.get(proyecto)
        if not ruta:
            disponibles = ", ".join(sorted(self.proyectos))
            return error(f"Proyecto desconocido: '{proyecto}'. Proyectos disponibles: {disponibles}.")

        binario = self._binario()
        if not binario:
            return error(
                "El binario 'opencode' no está disponible en el PATH. Instálalo "
                "(npm/choco/scoop o WSL) o verifica la configuración del entorno."
            )

        if not (self.confirmador and self.confirmador(peticion, ruta)):
            return error("El usuario canceló la ejecución de opencode.")

        print("[OpenCode] Lanzando agente (puede tardar unos minutos)...")
        try:
            resultado = subprocess.run(
                [binario, "run", "--dir", ruta, peticion],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=OPENCODE_TIMEOUT,
                creationflags=self._flags_ocultar_consola(),
            )
        except subprocess.TimeoutExpired:
            print("[OpenCode] Timeout excedido; tarea interrumpida.")
            return error("OpenCode excedió el tiempo límite; la tarea quedó interrumpida.")
        except OSError as exc:
            print(f"[OpenCode] OSError al lanzar el binario: {exc}")
            return error("No se pudo lanzar opencode en este equipo.")

        partes_salida = [resultado.stdout or ""]
        if resultado.stderr:
            partes_salida.append(f"[stderr] {resultado.stderr}")
        salida = "".join(partes_salida).strip()
        if not salida:
            salida = "(sin salida)"

        if resultado.returncode != 0:
            print(f"[OpenCode] Terminó con código {resultado.returncode}.")
            return error(
                f"OpenCode terminó con código {resultado.returncode}. "
                f"Salida: {salida[:800]}"
            )

        truncada = salida
        if len(truncada) > OPENCODE_SALIDA_MAX:
            truncada = truncada[:OPENCODE_SALIDA_MAX].rstrip() + "…"
        return ok(truncada)