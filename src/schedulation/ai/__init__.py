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

from .planner import AiPlanningError, ai_execute_schedulation


__all__ = ['AiPlanningError', 'ai_execute_schedulation']
