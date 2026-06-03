"""
pikachu/brain/grammar.py
──────────────────────────
Grammar correction engine.

Flow:
  1. GrammarEngine.activate(app_name, class_name)
       → loads Mistral 7B, starts polling thread
  2. Every GRAMMAR_POLL_INTERVAL_S seconds:
       → reads current text via TextReader
       → diffs against previous snapshot
       → if changed paragraphs exist, sends them to Mistral
  3. Mistral returns JSON: {"corrections": [{original, corrected, explanation}]}
  4. Emits correction_ready(List[Correction]) signal
  5. GrammarEngine.deactivate()
       → stops polling, unloads Mistral
"""

import json
import threading
import time
from typing import List, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from pikachu import config as cfg
from pikachu.ui.correction_panel import Correction
from pikachu.utils.logger import get_logger
from pikachu.utils.text_reader import TextReader

log = get_logger(__name__)

# ── Mistral prompt ────────────────────────────────────────────────────────────
_GRAMMAR_SYSTEM = """You are a precise writing assistant. Your task is to find and correct ALL spelling, grammar, and style errors.

CRITICAL RULES:
- Every sentence can contain MULTIPLE independent errors (e.g., typos AND grammar errors). Scan the entire text and report every single error. Do not stop after the first one.
- "spelling" scope is for typos/misspellings (e.g. mistekes -> mistakes).
- "grammar" scope is for objective rules (e.g. makes -> make).
- "style" scope is for awkward phrasing.
- The "error" field MUST contain ONLY the exact incorrect word or phrase from the text. Do not add any parenthetical comments, corrections, explanations, or notes (e.g. NEVER write "a lot" (should be "a lot of")).
- The "corrected" field MUST contain ONLY the clean replacement word or phrase. Do not add explanations, notes, or commentary.
- NEVER rewrite or repeat the entire sentence or context in the "corrected" field. Only provide the exact word or phrase that fixes the error. Example: If the error is "They going", the corrected field is "They are going".
- Output ONLY a valid JSON object. Do not include markdown code blocks (```json).

Format:
{
  "corrections": [
    {
      "question": "The complete original sentence containing the error",
      "scope": "spelling" | "grammar" | "style",
      "error": "The exact incorrect word or phrase",
      "corrected": "The corrected word or phrase",
      "explanation": "Short reason for the fix"
    }
  ]
}

If no errors are found, return exactly: {"corrections": []}"""


class GrammarSignals(QObject):
    correction_ready = pyqtSignal(list)   # List[Correction]
    status_changed   = pyqtSignal(bool)   # True = active, False = inactive
    gpu_released     = pyqtSignal()


class GrammarEngine:
    """
    Polls the active writing app for text changes and requests
    grammar corrections from Mistral 7B.
    """

    def __init__(self, llm_engine):
        """
        Args:
            llm_engine: LLMEngine instance (for ask_big calls).
        """
        self.signals    = GrammarSignals()
        self._llm       = llm_engine
        self._reader    = TextReader()
        self._active    = False
        self._class_name = ""
        self._thread    = None
        self._last_text = ""
        self._correction_index = 0
        self._high_gpu_ticks   = 0
        self._active_corrections = []
        self._dismissed_signatures = set()
        self._blocked_reversals = set()

        # Wire up LLM response → our handler (tag-routed: only accept "grammar" responses)
        self._llm.signals.big_response_ready.connect(self._on_llm_response)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active

    def activate(self, app_name: str, class_name: str):
        """
        Start grammar monitoring for the given app.
        Loads Mistral 7B and begins the polling loop.
        """
        if self._active:
            return
        log.info("Grammar mode activating for: %s (%s)", app_name, class_name)
        self._class_name = class_name
        self._last_text  = ""
        self._active     = True

        # Pre-load the big model
        self._llm.load_big_model()

        self.signals.status_changed.emit(True)

        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def deactivate(self):
        """Stop monitoring and free GPU memory."""
        if not self._active:
            return
        log.info("Grammar mode deactivating.")
        self._active = False
        # Clear highlights of all active corrections before unloading
        self._reader.clear_highlights_in_word(self._class_name, self._active_corrections)
        self._active_corrections = []
        self._dismissed_signatures.clear()
        self._llm.unload_big_model()
        self.signals.status_changed.emit(False)

    def toggle(self, app_name: str = "", class_name: str = ""):
        """Toggle grammar mode on/off."""
        if self._active:
            self.deactivate()
        else:
            self.activate(app_name, class_name)

    def replace_text(self, correction) -> bool:
        """Replace text in the active document for the given correction."""
        # Remove from active tracking first so we don't try to clear highlight for it again
        self._active_corrections = [c for c in self._active_corrections if c.index != correction.index]
        
        # Block the reverse of this correction from being suggested again in this session
        rev_sig = (
            correction.corrected.strip().lower(),
            correction.error.strip().lower()
        )
        self._blocked_reversals.add(rev_sig)
        log.info("[DEBUG] Added reverse correction to blocked reversals: %s", rev_sig)
        
        return self._reader.replace_text_in_active_app(
            class_name = self._class_name,
            original   = correction.error,
            corrected  = correction.corrected,
            question   = correction.question,
        )

    def dismiss_correction(self, correction):
        """Dismiss a correction: clear its highlight, add to dismissed signatures, and remove from active list."""
        self._reader.clear_highlights_in_word(self._class_name, [correction])
        self._active_corrections = [c for c in self._active_corrections if c.index != correction.index]
        
        # Track dismissed signature to filter out in subsequent checks
        sig = (
            correction.error.strip().lower(),
            correction.corrected.strip().lower(),
            self._normalize_text(correction.question)
        )
        self._dismissed_signatures.add(sig)
        log.info("[DEBUG] Added correction to dismissed signatures: %s", sig)

    def _normalize_text(self, text: str) -> str:
        """Helper to strip non-alphanumeric chars and lowercase text for signature matching."""
        return "".join(c.lower() for c in text if c.isalnum())

    # ── Internal: polling loop ────────────────────────────────────────────────

    def _poll_loop(self):
        log.info("[DEBUG] Grammar monitoring thread loop started.")
        self._high_gpu_ticks  = 0
        self._pending_paragraphs: List[str] = []
        self._proofread_queue: List[str]    = []
        self._last_change_time: float       = 0.0
        while self._active:
            try:
                current_text = self._reader.read_active_app(self._class_name)
                if current_text is None:
                    log.info("Writing app closed or no active document — deactivating grammar mode.")
                    self._active = False
                    self._llm.unload_big_model()
                    self.signals.status_changed.emit(False)
                    break

                log.info("[DEBUG] Raw text read from window: %r", current_text)
                changed = TextReader.get_changed_paragraphs(self._last_text, current_text)
                if changed:
                    log.info("[DEBUG] Paragraph diff detected changes: %s", changed)
                    self._last_text        = current_text
                    # Merge new changed paragraphs into the pending queue, deduplicating
                    for p in changed:
                        if p not in self._pending_paragraphs:
                            self._pending_paragraphs.append(p)
                    self._last_change_time = time.time()
                    log.info("[DEBUG] Debounce: queued %d paragraph(s), waiting for pause...",
                             len(self._pending_paragraphs))

                # ── Debounce gate: only send after user has stopped typing ────
                pause_elapsed = time.time() - self._last_change_time
                if (self._pending_paragraphs
                        and not self._llm._big_busy
                        and pause_elapsed >= cfg.GRAMMAR_PAUSE_THRESHOLD):
                    
                    # Hard token limit check
                    combined_len = sum(len(p) for p in self._pending_paragraphs)
                    if combined_len > cfg.MAX_CHARS_PER_REQUEST:
                        log.warning("[DEBUG] Payload size %d exceeds limit %d. Dropping to prevent freeze.", combined_len, cfg.MAX_CHARS_PER_REQUEST)
                        self._pending_paragraphs = []
                    else:
                        log.info("[DEBUG] Debounce: %.1fs pause detected — sending %d paragraph(s) to Mistral.",
                                 pause_elapsed, len(self._pending_paragraphs))
                        to_send = list(self._pending_paragraphs)
                        self._pending_paragraphs = []
                        self._request_correction(to_send)

                # ── Async Queue Processing ────────────────────────────────────
                # If we have no real-time typing queued, process the background proofread queue
                if (not self._pending_paragraphs
                        and not self._llm._big_busy
                        and self._proofread_queue):
                    log.info("[DEBUG] Processing next chunk from proofread queue (%d remaining)...", len(self._proofread_queue))
                    # Take up to 2 paragraphs from the queue
                    chunk = self._proofread_queue[:2]
                    self._proofread_queue = self._proofread_queue[2:]
                    self._request_correction(chunk)

                # Monitor GPU load to auto-unload if another heavy task is active
                if not self._llm._big_busy:
                    from pikachu.utils.helpers import get_gpu_utilization
                    gpu_load = get_gpu_utilization()
                    if gpu_load > 85:
                        self._high_gpu_ticks += 1
                        log.info("[DEBUG] Sustained high GPU load detected: %d%% (tick count: %d/3)", gpu_load, self._high_gpu_ticks)
                        if self._high_gpu_ticks >= 3:
                            log.info("Sustained high GPU load (%d%%) detected from external tasks — auto-releasing VRAM.", gpu_load)
                            self._active = False
                            self._llm.unload_big_model()
                            self.signals.status_changed.emit(False)
                            self.signals.gpu_released.emit()
                            break
                    else:
                        self._high_gpu_ticks = 0

            except Exception as e:
                log.warning("Grammar poll error: %s", e)

            time.sleep(cfg.GRAMMAR_POLL_INTERVAL_S)

        log.info("[DEBUG] Grammar monitoring thread loop stopped.")

    def enqueue_full_proofread(self):
        """Called by a keyboard shortcut to queue the entire document for async proofreading."""
        if not self._active:
            log.warning("Cannot enqueue proofread: Grammar Engine is not active.")
            return

        try:
            import win32com.client
            word = win32com.client.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument
            text = doc.Content.Text
            if not text:
                return
            text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0b", "\n")
            paras = [p.strip() for p in text.split("\n") if len(p.strip()) > 10]
            self._proofread_queue.extend(paras)
            log.info("Enqueued %d paragraphs for background proofreading.", len(paras))
        except Exception as e:
            log.error("Failed to enqueue full document: %s", e)

    def _request_correction(self, paragraphs: List[str]):
        """Send changed paragraphs to Mistral for correction."""
        if not paragraphs:
            return

        combined = "\n\n".join(paragraphs)
        self._last_prompt_text = combined  # save for hallucination checking
        messages = [
            {"role": "system", "content": _GRAMMAR_SYSTEM},
            {"role": "user",   "content": combined},
        ]
        log.info("[DEBUG] Sending prompt to Mistral.")
        log.info("[DEBUG] Prompt payload system message: %s", _GRAMMAR_SYSTEM)
        log.info("[DEBUG] Prompt payload user text to check:\n%s", combined)
        # tag="grammar" enables Ollama structured outputs (schema-constrained JSON)
        # and routes the response back exclusively to _on_llm_response
        self._llm.ask_big(messages, tag="grammar")

    # ── LLM response handler ──────────────────────────────────────────────────

    def _on_llm_response(self, text: str, tag: str):
        """Parse Mistral's JSON response and emit corrections."""
        # Only handle responses routed to us via the 'grammar' tag
        if tag != "grammar":
            return
        if not self._active:
            return
        log.info("[DEBUG] Raw response received from Mistral:\n%s", text)
        try:
            # With Ollama structured outputs the response is clean JSON.
            # We keep the {} extractor as a belt-and-suspenders guard for
            # older Ollama versions that might still include whitespace padding.
            start_idx = text.find('{')
            end_idx   = text.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                cleaned = text[start_idx : end_idx + 1]
            else:
                raise ValueError("No JSON object found in response.")

            log.info("[DEBUG] Cleaned JSON payload extracted: %s", cleaned)
            data        = json.loads(cleaned)
            raw_list    = data.get("corrections", [])
            log.info("[DEBUG] List of raw correction elements in JSON: %s", raw_list)
            corrections = []
            for item in raw_list:
                question = item.get("question", "").strip()
                scope    = item.get("scope", "grammar").strip().lower()
                error    = item.get("error", item.get("original", "")).strip()
                corr     = item.get("corrected", "").strip()
                expl     = item.get("explanation", "").strip()

                log.info("[DEBUG] Parsing correction element: Question=%r, Scope=%r, Error=%r, Corrected=%r", question, scope, error, corr)
                if (error or question) and corr and error != corr:
                    c = Correction(
                        question    = question,
                        scope       = scope,
                        error       = error,
                        corrected   = corr,
                        explanation = expl,
                        index       = self._correction_index,
                    )

                    # ── Filter: scope not enabled by user config ──────────────────
                    if scope not in cfg.GRAMMAR_ENABLED_SCOPES:
                        log.info("[DEBUG] Skipping correction with disabled scope '%s'", scope)
                        continue

                    # ── Filter: previously dismissed in this session ────────────
                    sig = (
                        c.error.strip().lower(),
                        c.corrected.strip().lower(),
                        self._normalize_text(c.question)
                    )
                    if sig in self._dismissed_signatures:
                        log.info("[DEBUG] Filtering out dismissed correction: %s", sig)
                        continue

                    # Filter out flip-flops (reversals of previously accepted corrections)
                    rev_check = (
                        c.error.strip().lower(),
                        c.corrected.strip().lower()
                    )
                    if rev_check in self._blocked_reversals:
                        log.info("[DEBUG] Filtering out reversed correction (flip-flop prevented): %s", rev_check)
                        continue

                    # Filter out hallucinations (Mistral making up text that isn't in the document)
                    if hasattr(self, '_last_prompt_text'):
                        context_text = self._last_prompt_text.lower()
                    else:
                        context_text = self._last_text.lower()

                    if c.error:
                        if c.error.lower() not in context_text:
                            log.info("[DEBUG] Filtering out hallucinated correction (error %r not found in context)", c.error)
                            continue
                    elif c.question:
                        if self._normalize_text(c.question) not in self._normalize_text(context_text):
                            log.info("[DEBUG] Filtering out hallucinated correction (question %r not found in context)", c.question)
                            continue

                    # Prevent duplicate cards
                    is_dup = False
                    for existing_c in self._active_corrections:
                        if existing_c.error == c.error and existing_c.corrected == c.corrected:
                            is_dup = True
                            break
                    if not is_dup:
                        corrections.append(c)
                        log.info("[DEBUG] Created Correction (index=%d): %r", self._correction_index, corrections[-1])
                        self._correction_index += 1
                else:
                    log.info("[DEBUG] Skipped/filtered empty or identical correction: error=%r, corrected=%r", error, corr)

            self._active_corrections.extend(corrections)

            if corrections:
                log.info("Grammar: %d new correction(s) found. Total active: %d", len(corrections), len(self._active_corrections))
                # Highlight new corrections in Word
                self._reader.highlight_corrections_in_word(self._class_name, corrections, color_index=-1)
                self.signals.correction_ready.emit(corrections)
            else:
                log.info("[DEBUG] Grammar: no corrections remained after parsing/filtering.")

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            log.warning("Could not parse grammar response: %s — raw: %.200s", e, text)
