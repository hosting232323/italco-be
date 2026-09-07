"""Pianificazione automatica sperimentale via LLM.

Spike: l'AI riceve gli ordini di una data con vincoli e utenti delivery e
restituisce direttamente la proposta completa (gruppi + corriere per gruppo).
Il codice qui sotto non si fida: valida la risposta contro i dati di partenza e
solleva AiPlanningError al primo scostamento, cosi' durante l'esperimento si
vede subito quando e perche' il modello sbaglia.

La chiamata passa dalla CLI `claude` in modalita' headless (vedi cli.py): scelta
buona per provare in locale sfruttando l'abbonamento, non una strada di
produzione (i termini della subscription non coprono l'uso da backend, e per
richiesta paghi un cold start di Node). L'orchestrazione sta dietro
ai_execute_schedulation, cosi' sostituire la CLI con l'API domani tocca un solo
modulo.
"""

import logging
import sys


# Logger dedicato allo spike: durante i test manuali si vuole vedere sulla
# console del server cosa succede (CLI lanciata, tempi, risposta grezza, esito
# della validazione). Handler proprio cosi' e' visibile anche se l'app non
# configura il logging; propagate=False per non sporcare gli altri log.
logger = logging.getLogger('italco.schedulation.ai')
if not logger.handlers:
  _handler = logging.StreamHandler(sys.stderr)
  _handler.setFormatter(logging.Formatter('[AI-PLANNING %(asctime)s] %(message)s', datefmt='%H:%M:%S'))
  logger.addHandler(_handler)
  logger.setLevel(logging.INFO)
  logger.propagate = False


from .planner import AiPlanningError, ai_execute_schedulation  # noqa: E402


__all__ = ['AiPlanningError', 'ai_execute_schedulation', 'logger']
