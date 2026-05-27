import os
import asyncio
import logging
from datetime import datetime

from fastapi import HTTPException

logger = logging.getLogger("tes.fila")


class FilaGlobal:

    def __init__(self):
        self._max_concurrent = int(os.getenv("MAX_CONCURRENT_TASKS", "1"))
        self._max_queue_size = int(os.getenv("MAX_QUEUE_SIZE", "10"))

        self._semaforo = asyncio.Semaphore(self._max_concurrent)
        self._bloqueio = asyncio.Lock()

        self._em_espera = 0
        self._em_execucao = 0
        self._total_executadas = 0

        logger.info(
            "[Fila] Inicializada (max_concurrent=%d, max_queue_size=%d)",
            self._max_concurrent, self._max_queue_size,
        )
        print(
            f"[Fila] Inicializada (max_concurrent={self._max_concurrent}, "
            f"max_queue_size={self._max_queue_size})"
        )

    async def executar(self, coro_fn, *args, **kwargs):
        async with self._bloqueio:
            if 0 < self._max_queue_size <= self._em_espera:
                logger.warning(
                    f"[Fila] Rejeitado - fila cheia "
                    f"(em_espera={self._em_espera}, max={self._max_queue_size})"
                )
                raise HTTPException(
                    status_code=503,
                    detail="Servidor ocupado, tente novamente mais tarde.",
                )
            self._em_espera += 1

        if self._em_espera > 0:
            logger.info(
                f"[Fila] Pedido enfileirado - a aguardar slot "
                f"(em_espera={self._em_espera}, em_execucao={self._em_execucao})"
            )

        adquiriu_slot = False
        try:
            await self._semaforo.acquire()
            adquiriu_slot = True

            async with self._bloqueio:
                self._em_espera -= 1
                self._em_execucao += 1

            logger.info(
                f"[Fila] Slot adquirido - a executar "
                f"(em_execucao={self._em_execucao}/{self._max_concurrent}, "
                f"em_espera={self._em_espera})"
            )

            return await coro_fn(*args, **kwargs)

        finally:
            if adquiriu_slot:
                async with self._bloqueio:
                    self._em_execucao -= 1
                    self._total_executadas += 1
                self._semaforo.release()
                logger.info(
                    f"[Fila] Slot libertado "
                    f"(em_execucao={self._em_execucao}, "
                    f"total={self._total_executadas})"
                )
            else:
                async with self._bloqueio:
                    self._em_espera -= 1
                logger.info(
                    f"[Fila] Pedido cancelado antes de adquirir slot "
                    f"(em_espera={self._em_espera})"
                )

    def info(self) -> dict:
        return {
            "fila": {
                "em_espera": self._em_espera,
                "em_execucao": self._em_execucao,
                "total_executadas": self._total_executadas,
                "max_concurrent": self._max_concurrent,
                "max_queue_size": self._max_queue_size,
            }
        }

fila = FilaGlobal()
