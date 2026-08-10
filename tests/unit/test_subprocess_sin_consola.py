"""
Al arrancar la app (GUI sin terminal), los subprocess de herramientas de CONSOLA (ffmpeg del grabador de
cámaras, mysqldump/mysql del backup) NO deben abrir una ventana negra de consola. El helper único
`plataforma.kwargs_sin_consola()` aporta los flags correctos y todos esos subprocess lo usan.
"""

import subprocess

from src.utils import plataforma
from src.utils.plataforma import kwargs_sin_consola


def test_kwargs_sin_consola_por_plataforma():
    kw = kwargs_sin_consola()
    assert isinstance(kw, dict)
    if plataforma.ES_WINDOWS:
        cnw = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        assert kw.get("creationflags", 0) & cnw          # oculta la consola
        assert "startupinfo" in kw                        # + SW_HIDE (cinturón y tirantes)
    else:
        assert kw == {}                                   # en POSIX no aplica


def test_subprocess_acepta_los_kwargs():
    # Un proceso de consola lanzado con estos kwargs se ejecuta con normalidad (y sin ventana en Windows).
    r = subprocess.run(["python", "-c", "print('ok')"], capture_output=True, text=True,
                       **kwargs_sin_consola())
    assert r.returncode == 0 and r.stdout.strip() == "ok"


def test_grabador_camaras_usa_el_helper():
    import inspect
    from src.services.camaras import grabacion
    assert "kwargs_sin_consola" in inspect.getsource(grabacion.grabar_dia_ffmpeg)


def test_backup_usa_el_helper():
    import inspect
    from src.db import backup
    assert "kwargs_sin_consola" in inspect.getsource(backup)
