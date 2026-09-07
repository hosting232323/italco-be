"""Wrapper sottile sulla CLI `claude` in modalita' headless.

`claude -p` legge il prompt da stdin e stampa su stdout un envelope JSON
(`{type, subtype, is_error, result, ...}`); qui si estrae `result`, cioe' il
testo prodotto dal modello. Tutto il resto (costruzione del prompt, parsing e
validazione della risposta) vive in prompt.py / planner.py: questo modulo sa
solo lanciare il processo e riportare errori con un tipo dedicato.
"""

import json
import logging
import os
import shutil
import subprocess
import time


logger = logging.getLogger('italco.schedulation.ai')


class ClaudeCliError(RuntimeError):
  """La CLI non e' disponibile, e' uscita male o non ha risposto come atteso."""


DEFAULT_TIMEOUT_SECONDS = 180


def run_claude(prompt: str, *, system: str | None = None, timeout: int | None = None) -> str:
  """Esegue `claude -p` con il prompt su stdin e restituisce il testo di risposta.

  system, se passato, viene aggiunto al system prompt della CLI. Nessun tool e'
  abilitato e il giro e' a turno singolo: vogliamo solo la risposta del modello.
  `--strict-mcp-config` senza `--mcp-config` fa partire la CLI senza caricare
  alcun server MCP dell'utente: e' il grosso del cold start in headless.
  Timeout: argomento esplicito, altrimenti CLAUDE_CLI_TIMEOUT, altrimenti 180s.
  """
  if timeout is None:
    timeout = int(os.environ.get('CLAUDE_CLI_TIMEOUT', DEFAULT_TIMEOUT_SECONDS))

  binary = _resolve_binary()
  args = [binary, '-p', '--output-format', 'json', '--max-turns', '1', '--strict-mcp-config']
  model = os.environ.get('CLAUDE_CLI_MODEL')
  if model:
    args += ['--model', model]
  if system:
    args += ['--append-system-prompt', system]

  logger.info(
    'lancio la CLI: %s%s  (prompt su stdin, %d caratteri, timeout %ds)',
    os.path.basename(binary),
    f' --model {model}' if model else '',
    len(prompt),
    timeout,
  )
  started = time.monotonic()
  try:
    completed = subprocess.run(
      args,
      input=prompt,
      capture_output=True,
      text=True,
      timeout=timeout,
      check=False,
    )
  except subprocess.TimeoutExpired as error:
    logger.warning('la CLI non ha risposto entro %ds (interrotta)', timeout)
    raise ClaudeCliError(f'La CLI Claude non ha risposto entro {timeout}s') from error
  except OSError as error:
    logger.warning('impossibile eseguire la CLI: %s', error)
    raise ClaudeCliError(f'Impossibile eseguire la CLI Claude: {error}') from error

  elapsed = time.monotonic() - started
  if completed.returncode != 0:
    detail = (completed.stderr or completed.stdout or '').strip()
    logger.warning("la CLI e' uscita con codice %d dopo %.1fs: %s", completed.returncode, elapsed, detail[:300])
    raise ClaudeCliError(f"La CLI Claude e' uscita con codice {completed.returncode}: {detail[:500]}")

  result = _extract_result(completed.stdout)
  logger.info('la CLI ha risposto in %.1fs (%d caratteri di testo)', elapsed, len(result))
  logger.info('risposta grezza del modello: %s', result[:1000] + (' [...]' if len(result) > 1000 else ''))
  return result


def _resolve_binary() -> str:
  configured = os.environ.get('CLAUDE_CLI_PATH')
  if configured:
    if os.path.isfile(configured):
      return configured
    resolved = shutil.which(configured)
    if resolved:
      return resolved
    raise ClaudeCliError(f'CLAUDE_CLI_PATH non punta a un eseguibile valido: {configured}')

  resolved = shutil.which('claude')
  if not resolved:
    raise ClaudeCliError('CLI `claude` non trovata nel PATH (imposta CLAUDE_CLI_PATH)')
  return resolved


def _extract_result(stdout: str) -> str:
  try:
    envelope = json.loads(stdout)
  except json.JSONDecodeError as error:
    raise ClaudeCliError(f"Output della CLI Claude non e' JSON: {stdout[:500]}") from error

  if envelope.get('is_error') or envelope.get('subtype') not in (None, 'success'):
    raise ClaudeCliError(f'La CLI Claude ha segnalato un errore: {envelope.get("result", envelope)}')

  result = envelope.get('result')
  if not isinstance(result, str) or not result.strip():
    raise ClaudeCliError('Risposta della CLI Claude priva del campo `result`')
  return result
