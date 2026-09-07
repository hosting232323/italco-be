"""Wrapper sottile sulla CLI `claude` in modalita' headless.

`claude -p` legge il prompt da stdin e stampa su stdout un envelope JSON
(`{type, subtype, is_error, result, ...}`); qui si estrae `result`, cioe' il
testo prodotto dal modello. Tutto il resto (costruzione del prompt, parsing e
validazione della risposta) vive in prompt.py / planner.py: questo modulo sa
solo lanciare il processo e riportare errori con un tipo dedicato.
"""

import json
import os
import shutil
import subprocess


class ClaudeCliError(RuntimeError):
  """La CLI non e' disponibile, e' uscita male o non ha risposto come atteso."""


DEFAULT_TIMEOUT_SECONDS = 120


def run_claude(prompt: str, *, system: str | None = None, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
  """Esegue `claude -p` con il prompt su stdin e restituisce il testo di risposta.

  system, se passato, viene aggiunto al system prompt della CLI. Nessun tool e'
  abilitato e il giro e' a turno singolo: vogliamo solo la risposta del modello.
  """
  binary = _resolve_binary()
  args = [binary, '-p', '--output-format', 'json', '--max-turns', '1']
  model = os.environ.get('CLAUDE_CLI_MODEL')
  if model:
    args += ['--model', model]
  if system:
    args += ['--append-system-prompt', system]

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
    raise ClaudeCliError(f'La CLI Claude non ha risposto entro {timeout}s') from error
  except OSError as error:
    raise ClaudeCliError(f'Impossibile eseguire la CLI Claude: {error}') from error

  if completed.returncode != 0:
    detail = (completed.stderr or completed.stdout or '').strip()
    raise ClaudeCliError(f"La CLI Claude e' uscita con codice {completed.returncode}: {detail[:500]}")

  return _extract_result(completed.stdout)


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
