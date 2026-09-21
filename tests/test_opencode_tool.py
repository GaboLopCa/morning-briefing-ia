import types as py_types

from modules.opencode_tool import OPENCODE_SALIDA_MAX, OpenCodeRunner


class RespuestaSubprocess:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class TestOpenCodeRunner:
    def test_proyecto_desconocido(self):
        runner = OpenCodeRunner(confirmador=lambda p, r: True)
        resultado = runner.ejecutar(proyecto="no_existe", peticion="haz algo")
        assert resultado["status"] == "error"
        assert "Proyecto desconocido" in resultado["mensaje"]

    def test_confirmacion_rechazada_no_ejecuta(self, monkeypatch):
        runner = OpenCodeRunner(confirmador=lambda p, r: False)

        def fake_run(*args, **kwargs):
            raise AssertionError("no debería ejecutarse")

        monkeypatch.setattr("modules.opencode_tool.subprocess.run", fake_run)
        monkeypatch.setattr("modules.opencode_tool.shutil.which", lambda cmd: "opencode")

        resultado = runner.ejecutar(proyecto="asistente", peticion="tarea")
        assert resultado["status"] == "error"
        assert "canceló" in resultado["mensaje"]

    def test_error_con_codigo_de_salida_no_cero(self, monkeypatch):
        runner = OpenCodeRunner(confirmador=lambda p, r: True)

        def fake_run(*args, **kwargs):
            return RespuestaSubprocess(stdout="salió mal", returncode=1)

        monkeypatch.setattr("modules.opencode_tool.subprocess.run", fake_run)
        monkeypatch.setattr("modules.opencode_tool.shutil.which", lambda cmd: "opencode")

        resultado = runner.ejecutar(proyecto="asistente", peticion="tarea")
        assert resultado["status"] == "error"
        assert "código 1" in resultado["mensaje"]

    def test_exito_devuelve_salida_completa(self, monkeypatch):
        runner = OpenCodeRunner(confirmador=lambda p, r: True)
        out = "gran resultado"

        def fake_run(*args, **kwargs):
            return RespuestaSubprocess(stdout=out)

        monkeypatch.setattr("modules.opencode_tool.subprocess.run", fake_run)
        monkeypatch.setattr("modules.opencode_tool.shutil.which", lambda cmd: "opencode")

        resultado = runner.ejecutar(proyecto="asistente", peticion="tarea")
        assert resultado["status"] == "ok"
        assert resultado["data"] == out

    def test_salida_larga_se_trunca(self, monkeypatch):
        runner = OpenCodeRunner(confirmador=lambda p, r: True)
        out = "a" * (OPENCODE_SALIDA_MAX + 500)

        def fake_run(*args, **kwargs):
            return RespuestaSubprocess(stdout=out)

        monkeypatch.setattr("modules.opencode_tool.subprocess.run", fake_run)
        monkeypatch.setattr("modules.opencode_tool.shutil.which", lambda cmd: "opencode")

        resultado = runner.ejecutar(proyecto="asistente", peticion="tarea")
        assert resultado["status"] == "ok"
        assert len(resultado["data"]) <= OPENCODE_SALIDA_MAX + 500  # + la elipsis
        assert "…" in resultado["data"]

    def test_sin_binario_devuelve_error(self, monkeypatch):
        runner = OpenCodeRunner(confirmador=lambda p, r: True)
        monkeypatch.setattr("modules.opencode_tool.shutil.which", lambda cmd: None)

        resultado = runner.ejecutar(proyecto="asistente", peticion="tarea")
        assert resultado["status"] == "error"
        assert "opencode" in resultado["mensaje"]