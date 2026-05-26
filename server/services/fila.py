"""
Fila Global Transparente — Sistema de controlo de concorrência.

O frontend não sabe que esta fila existe. Os pedidos HTTP ficam
bloqueados (await) até um slot ficar livre, executam, e devolvem
o resultado normalmente. Do ponto de vista do utilizador, a
análise está simplesmente "a correr".

Configuração via variáveis de ambiente:
  MAX_CONCURRENT_TASKS  — tarefas pesadas em paralelo (default: 1)
  MAX_QUEUE_SIZE        — máximo de pedidos em espera  (default: 10, 0=ilimitado)
"""

import os
import asyncio
import logging
from datetime import datetime

from fastapi import HTTPException

logger = logging.getLogger("tes.fila")


class FilaGlobal:
    """
    Fila transparente que limita a concorrência de tarefas pesadas
    sem que o frontend saiba da sua existência.

    Usa um asyncio.Semaphore para limitar slots de execução e um
    contador protegido por Lock para limitar o tamanho da fila de espera.
    """

    def __init__(self):
        self._max_concurrent = int(os.getenv("MAX_CONCURRENT_TASKS", "1"))
        self._max_queue_size = int(os.getenv("MAX_QUEUE_SIZE", "10"))

        self._semaforo = asyncio.Semaphore(self._max_concurrent)
        self._bloqueio = asyncio.Lock()

        # Contadores
        self._em_espera = 0
        self._em_execucao = 0
        self._total_executadas = 0

        logger.info(
            "[Fila] Inicializada (max_concurrent=%d, max_queue_size=%d)",
            self._max_concurrent, self._max_queue_size,
        )
        # Also print since this runs at import time before logging.basicConfig
        print(
            f"[Fila] Inicializada (max_concurrent={self._max_concurrent}, "
            f"max_queue_size={self._max_queue_size})"
        )

    async def executar(self, coro_fn, *args, **kwargs):
        """
        Executa uma coroutine através da fila. Bloqueia até completar.

        Se todos os slots estão ocupados, o pedido espera silenciosamente.
        Se a fila de espera está cheia, devolve HTTP 503.

        Parâmetros:
            coro_fn — Função async a executar (não a coroutine já chamada).
            *args, **kwargs — Argumentos passados a coro_fn().

        Retorna:
            O resultado de coro_fn(*args, **kwargs).
        """
        # 1. Verificar se há espaço na fila de espera
        async with self._bloqueio:
            if 0 < self._max_queue_size <= self._em_espera:
                logger.warning(
                    f"[Fila] Rejeitado — fila cheia "
                    f"(em_espera={self._em_espera}, max={self._max_queue_size})"
                )
                raise HTTPException(
                    status_code=503,
                    detail="Servidor ocupado, tente novamente mais tarde.",
                )
            self._em_espera += 1

        if self._em_espera > 0:
            logger.info(
                f"[Fila] Pedido enfileirado — a aguardar slot "
                f"(em_espera={self._em_espera}, em_execucao={self._em_execucao})"
            )

        adquiriu_slot = False
        try:
            # 2. Esperar por um slot (bloqueia aqui se todos ocupados)
            await self._semaforo.acquire()
            adquiriu_slot = True

            # 3. Passou de "em espera" para "em execução"
            async with self._bloqueio:
                self._em_espera -= 1
                self._em_execucao += 1

            logger.info(
                f"[Fila] Slot adquirido — a executar "
                f"(em_execucao={self._em_execucao}/{self._max_concurrent}, "
                f"em_espera={self._em_espera})"
            )

            # 4. Executar a tarefa real
            return await coro_fn(*args, **kwargs)

        finally:
            if adquiriu_slot:
                # Tarefa terminou (sucesso ou erro) — libertar slot
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
                # Cancelado antes de adquirir o slot (ex: CancelledError)
                async with self._bloqueio:
                    self._em_espera -= 1
                logger.info(
                    f"[Fila] Pedido cancelado antes de adquirir slot "
                    f"(em_espera={self._em_espera})"
                )

    def info(self) -> dict:
        """Informação do estado da fila para o endpoint /api/health."""
        return {
            "fila": {
                "em_espera": self._em_espera,
                "em_execucao": self._em_execucao,
                "total_executadas": self._total_executadas,
                "max_concurrent": self._max_concurrent,
                "max_queue_size": self._max_queue_size,
            }
        }


# Singleton — uma única fila global para todo o servidor
fila = FilaGlobal()
