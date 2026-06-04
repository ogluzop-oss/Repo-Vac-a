import struct
import wave

import numpy as np

# ============================================================
# BLOQUE GENERACIÓN DE AUDIO WAV
# ============================================================

def generar_beep(
    nombre_archivo="error.wav",
    duracion=1.5,
    frecuencia=440,
    volumen=0.5,
    sample_rate=44100,
):
    """
    Genera un archivo WAV con un beep simple.

    Parámetros:
    - nombre_archivo: nombre del archivo de salida (.wav)
    - duracion: duración del beep en segundos
    - frecuencia: frecuencia del beep en Hz (ej. 440 para A4)
    - volumen: volumen entre 0 y 1
    - sample_rate: frecuencia de muestreo, típicamente 44100 Hz
    """
    n_samples = int(sample_rate * duracion)
    t = np.linspace(0, duracion, n_samples, False)  # eje temporal
    onda = np.sin(2 * np.pi * frecuencia * t)  # onda senoidal

    # Escalar a 16-bit PCM
    onda_int = np.int16(onda * volumen * 32767)

    # Crear archivo WAV
    with wave.open(nombre_archivo, "w") as wav_file:
        nchannels = 1
        sampwidth = 2  # 2 bytes = 16 bits
        wav_file.setparams(
            (nchannels, sampwidth, sample_rate, n_samples, "NONE", "not compressed")
        )

        # Escribir samples
        for sample in onda_int:
            wav_file.writeframes(struct.pack("<h", sample))

    print(f"Archivo WAV generado: {nombre_archivo}")


# ============================================================
# BLOQUE EJECUCIÓN
# ============================================================

generar_beep("assets/error.wav", duracion=1.5, frecuencia=440, volumen=0.5)
