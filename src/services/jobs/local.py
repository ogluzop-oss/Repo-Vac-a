"""
Backend LOCAL de la cola de jobs (Fase 10): cola en memoria, thread-safe. Backend por defecto en DEV; permite
probar TODO el ciclo de jobs (incluido el aislamiento por tenant y el worker de IA) sin AWS.
"""

import collections
import queue
import threading

from src.services.jobs.base import Job, JobQueue


class LocalQueue(JobQueue):
    nombre = "local"

    def __init__(self):
        self._q = queue.Queue()
        self._lock = threading.Lock()
        self._por_id = collections.OrderedDict()

    def encolar(self, job: Job) -> str:
        with self._lock:
            self._por_id[job.id] = job
        self._q.put(job)
        return job.id

    def siguiente(self, *, timeout=0):
        try:
            return self._q.get(block=timeout > 0, timeout=timeout or None) if timeout else self._q.get_nowait()
        except queue.Empty:
            return None

    def profundidad(self) -> int:
        return self._q.qsize()

    def obtener(self, job_id):
        with self._lock:
            return self._por_id.get(job_id)
