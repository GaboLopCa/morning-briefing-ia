"""Wake word JARVIS con openWakeWord.

openWakeWord (Apache-2.0, ONNX, local). Sesión 3: usa el modelo preentrenado
"hey jarvis"; entrenar un "jarvis" corto (grabaciones propias + Piper) queda
para una fase posterior (ver TAREAS_PENDIENTES).

`WakeWordDetector` es lógica pura (numpy int16 -> puntajes) y se testea con un
modelo falso. `crear_detector()` es la factoría con **degradación elegante**:
si openwakeword/onnxruntime faltan o el modelo no carga, devuelve None y la app
sigue funcionando con hotkeys/bandeja (solo se pierde la wake word).
"""
import logging
from pathlib import Path
import time as time_mod
import urllib.request

from config import (
    WAKE_WORD_ARCHIVO,
    WAKE_WORD_HISTERESIS,
    WAKE_WORD_MODELO,
    WAKE_WORD_REPORTE_INTERVALO,
    WAKE_WORD_REPORTE_UMBRAL,
    WAKE_WORD_UMBRAL,
)

logger = logging.getLogger("josesito")

# openWakeWord no empaqueta los modelos: se descargan de GitHub Releases al
# primer uso (una sola vez). ONNX (no tflite): onnxruntime es la dependencia.
_BASE_DESCARGAS = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/"
_MODELOS_ONNX = ("embedding_model.onnx", "melspectrogram.onnx", "hey_jarvis_v0.1.onnx")


def _clave_prediccion(claves):
    """Elige la etiqueta del modelo: la de 'jarvis' si existe, si no la primera."""
    for clave in claves:
        if "jarvis" in clave:
            return clave
    return claves[0] if claves else None


class WakeWordDetector:
    """Detecta el flanco de la wake word con histéresis y reporte de near-miss.

    - Retroceso: solo dispara una vez por mantención de energía sonora.
    - Sin gating de eco: dispara también mientras el asistente habla (barge-in,
      sesión 5.b). La decisión de interrumpir la toma la máquina de estados.
    - Reporte: cuando el puntaje queda entre `reporte_umbral` y el umbral real
      (casi dispara, sin llegar), llama `al_reporte(clave, puntaje)` como
      máximo cada `reporte_intervalo` segundos — sirve para calibrar el umbral
      al acento del usuario ("no me oye" -> ver el log y bajar `WAKE_WORD_UMBRAL`).
    """

    def __init__(
        self,
        modelo,
        al_detectar=None,
        al_reporte=None,
        umbral=WAKE_WORD_UMBRAL,
        histeresis=WAKE_WORD_HISTERESIS,
        reporte_umbral=WAKE_WORD_REPORTE_UMBRAL,
        reporte_intervalo=WAKE_WORD_REPORTE_INTERVALO,
    ):
        self._modelo = modelo
        self.al_detectar = al_detectar
        self.al_reporte = al_reporte
        self._umbral = umbral
        self._hist = histeresis
        self._reporte_umbral = reporte_umbral
        self._reporte_intervalo = reporte_intervalo
        self._disparado = False
        self._ultimo_reporte = 0.0

    def alimentar(self, audio):
        """`audio`: np.ndarray int16 mono (~80 ms). True solo en el flanco."""
        prediccion = self._modelo.predict(audio)
        clave = _clave_prediccion(prediccion)
        if clave is None:
            return False
        puntaje = prediccion[clave]
        if puntaje >= self._umbral:
            if not self._disparado:
                self._disparado = True
                if self.al_detectar is not None:
                    self.al_detectar()
                    return True
        elif puntaje < self._hist:
            self._disparado = False
        if self.al_reporte is not None and self._umbral > puntaje >= self._reporte_umbral:
            ahora = time_mod.monotonic()
            if ahora - self._ultimo_reporte >= self._reporte_intervalo:
                self._ultimo_reporte = ahora
                self.al_reporte(clave, puntaje)
        return False

    def reset(self):
        self._disparado = False
        if hasattr(self._modelo, "reset"):
            self._modelo.reset()


def _directorio_modelos():
    import openwakeword

    return Path(openwakeword.__file__).parent / "resources" / "models"


def _asegurar_modelos():
    """Descarga (una sola vez) los modelos ONNX que openwakeword no incluye."""
    directorio = _directorio_modelos()
    directorio.mkdir(parents=True, exist_ok=True)
    for nombre in _MODELOS_ONNX:
        destino = directorio / nombre
        if destino.exists() and destino.stat().st_size > 0:
            continue
        url = _BASE_DESCARGAS + nombre
        logger.info("Descargando modelo ONNX de wake word: %s", nombre)
        urllib.request.urlretrieve(url, destino)


def crear_detector(compartido=None, al_detectar=None):
    """Factoría con degradación elegante; devuelve None si algo falla."""
    try:
        from openwakeword.model import Model
    except ImportError as exc:
        logger.warning("Wake word desactivada: openwakeword no disponible (%s).", exc)
        return None
    try:
        _asegurar_modelos()
        if WAKE_WORD_ARCHIVO:
            modelo = Model(wakeword_models=[WAKE_WORD_ARCHIVO], inference_framework="onnx")
        else:
            # Solo "hey jarvis" (un `Model()` sin nombres cargaría TODO y fallaría
            # porque el resto de preentrenados no está descargado).
            modelo = Model(wakeword_models=[WAKE_WORD_MODELO], inference_framework="onnx")
    except Exception as exc:
        logger.warning("Wake word desactivada: no se pudo cargar el modelo (%s).", exc)
        return None
    detector = WakeWordDetector(
        modelo,
        al_detectar=al_detectar,
        al_reporte=lambda clave, puntaje: logger.info(
            "Wake word casi dispara: %s = %.3f (umbral %s). Si no te oye, baja "
            "WAKE_WORD_UMBRAL en config.py.",
            clave,
            puntaje,
            WAKE_WORD_UMBRAL,
        ),
    )
    logger.info("Wake word activa (modelo: %s, umbral: %s).", WAKE_WORD_MODELO, WAKE_WORD_UMBRAL)
    return detector