"""
pikachu/utils/text_reader.py
─────────────────────────────
Text extraction from active writing applications.

Strategy per app:
  Microsoft Word  → COM Automation (win32com) — non-invasive, reliable
  Notepad         → UI Automation TextPattern (uiautomation) — non-invasive
  Notepad++ / TeXstudio → NOT continuously polled (Scintilla can't expose
                           text via UIA without clipboard). Pikachu offers
                           to read on-demand only.

Nothing here uses a keylogger. We read from OS accessibility APIs —
the same APIs used by screen readers and accessibility tools.
"""

import difflib
import unicodedata
from typing import Optional, List

from pikachu.utils.logger import get_logger

log = get_logger(__name__)


def _normalize_for_search(text: str) -> str:
    """
    NFKC-normalize text and map smart-quote/dash variants to ASCII.

    MS Word stores text with typographical (curly) quotes (U+2018, U+2019, U+201C,
    U+201D) and em-dashes (U+2014). Local LLMs normalise these to straight ASCII
    quotes / hyphens. Without this step, Find.Execute silently fails because the
    search string literally does not match the document characters.
    """
    text = unicodedata.normalize("NFKC", text)
    for src, dst in [
        ("\u2018", "'"),  # left  single quote  → apostrophe
        ("\u2019", "'"),  # right single quote  → apostrophe
        ("\u201C", '"'),  # left  double quote  → straight quote
        ("\u201D", '"'),  # right double quote  → straight quote
        ("\u2013", "-"),  # en-dash             → hyphen
        ("\u2014", "-"),  # em-dash             → hyphen
        ("\u200B", ""),   # zero-width space    → remove
    ]:
        text = text.replace(src, dst)
    return text

class TextReader:
    """
    Reads the current text content from the active writing application.
    Call ``read_active_app(class_name)`` to auto-dispatch to the right backend.
    """

    # ── Word COM ──────────────────────────────────────────────────────────────

    def read_word(self) -> Optional[str]:
        """
        Read the active paragraph (where the cursor is) and the preceding paragraph
        for context via COM Automation. This prevents freezing on large essays.
        Returns None if Word is not running or no document is open.
        """
        try:
            import win32com.client
            word = win32com.client.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument
            
            sel = word.Selection
            if not sel or sel.Paragraphs.Count == 0:
                return None
                
            active_para = sel.Paragraphs(1)
            text = active_para.Range.Text
            
            # Try to grab the previous paragraph for context if it exists
            try:
                prev_para = active_para.Previous()
                if prev_para and prev_para.Range.Text:
                    text = prev_para.Range.Text + text
            except Exception:
                pass # First paragraph, no previous exists

            if text:
                text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0b", "\n")
            return text.rstrip("\n")
        except Exception as e:
            log.debug("read_word: %s", e)
            return None

    # ── Notepad UIA ───────────────────────────────────────────────────────────

    def read_notepad(self) -> Optional[str]:
        """
        Read Notepad's text content via UI Automation ValuePattern.
        Returns None if Notepad is not running.
        """
        try:
            import uiautomation as auto
            notepad = auto.WindowControl(searchDepth=1, ClassName="Notepad")
            edit    = notepad.EditControl()
            return edit.GetValuePattern().Value
        except Exception as e:
            log.debug("read_notepad: %s", e)
            return None

    # ── Auto-dispatch ─────────────────────────────────────────────────────────

    def read_active_app(self, class_name: str) -> Optional[str]:
        """
        Read text from the app identified by *class_name*.
        Returns None for unsupported apps (Notepad++, TeXstudio, Chrome).
        """
        if class_name == "OpusApp":
            return self.read_word()
        if class_name == "Notepad":
            return self.read_notepad()
        # Notepad++, TeXstudio, Chrome — not continuously readable
        log.debug("read_active_app: no reader for class '%s'", class_name)
        return None

    # ── Diff helper ───────────────────────────────────────────────────────────

    @staticmethod
    def get_changed_paragraphs(old_text: str, new_text: str) -> List[str]:
        """
        Compare two snapshots and return a list of changed/added paragraphs.
        Only paragraphs with meaningful content (≥10 chars) are returned.
        """
        log.info("[DEBUG] get_changed_paragraphs: old_text length=%d, new_text length=%d", len(old_text), len(new_text))
        old_paras = [p.strip() for p in old_text.split("\n") if p.strip()]
        new_paras = [p.strip() for p in new_text.split("\n") if p.strip()]
        log.info("[DEBUG] Split old paragraphs: %s", old_paras)
        log.info("[DEBUG] Split new paragraphs: %s", new_paras)

        sm      = difflib.SequenceMatcher(None, old_paras, new_paras)
        changed = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            log.info("[DEBUG] Diff Opcode: %s on old[%d:%d] -> new[%d:%d]", tag, i1, i2, j1, j2)
            if tag in ("replace", "insert"):
                for para in new_paras[j1:j2]:
                    if len(para) >= 10:
                        log.info("[DEBUG] Found changed paragraph (>= 10 chars): %r", para)
                        changed.append(para)
                    else:
                        log.info("[DEBUG] Skipped changed paragraph (< 10 chars): %r", para)

        log.info("[DEBUG] Final list of paragraphs to send: %s", changed)
        return changed

    def replace_text_in_active_app(self, class_name: str, original: str, corrected: str, question: str = "") -> bool:
        """
        Replace the incorrect text with the corrected text in the active application.
        Currently supports Microsoft Word (OpusApp) via COM.
        """
        if class_name != "OpusApp":
            log.debug("replace_text_in_active_app: not supported for class '%s'", class_name)
            return False

        try:
            import win32com.client
            word = win32com.client.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument
            log.info("[DEBUG] replace_text_in_active_app called: original=%r, corrected=%r, question=%r", original, corrected, question)

            # ── Stale context guard ────────────────────────────────────────────
            # Re-read Word right now (not the cached snapshot). If the error
            # no longer exists the user deleted/corrected it while Mistral ran.
            if original:
                current_doc_text = doc.Content.Text or ""
                if _normalize_for_search(original) not in _normalize_for_search(current_doc_text):
                    log.warning("Stale context: error %r no longer exists in document. Aborting.", original)
                    return False

            # ── Phase 1: Sentence-context-scoped search ────────────────────────
            # Locate the exact sentence first, then search within that narrow
            # range for the error word. Prevents replacing the same word in the
            # wrong paragraph.
            if question:
                clean_q = _normalize_for_search(question.strip().replace("\n", "\r"))
                find_range = doc.Content
                find_obj = find_range.Find
                find_obj.ClearFormatting()
                find_obj.Text = clean_q
                find_obj.MatchCase = False
                find_obj.MatchWholeWord = False   # must be False for multi-word phrase
                find_obj.MatchWildcards = False

                log.info("[DEBUG] Searching for sentence context: %r", clean_q)
                if find_obj.Execute():
                    log.info("[DEBUG] Found sentence context range: [%d, %d] -> text: %r", find_range.Start, find_range.End, find_range.Text)
                    if original:
                        error_find = find_range.Find
                        error_find.ClearFormatting()
                        error_find.Text = _normalize_for_search(original.strip())
                        error_find.MatchCase = True
                        error_find.MatchWholeWord = True    # native boundary guard
                        log.info("[DEBUG] Searching for error word %r within sentence context", original.strip())
                        if error_find.Execute():
                            log.info("[DEBUG] Found error word match range: [%d, %d] -> text: %r", find_range.Start, find_range.End, find_range.Text)
                            self._expand_to_word_boundaries(doc, find_range)
                            find_range.HighlightColorIndex = 0
                            find_range.Font.Underline = 0
                            old_text = find_range.Text
                            find_range.Text = corrected.strip()
                            find_range.HighlightColorIndex = 4 # wdBrightGreen
                            log.info("Successfully replaced %r with %r (original error was %r) in Word sentence context.", old_text, corrected, original)
                            return True
                        else:
                            log.info("[DEBUG] Error word %r not found within sentence context.", original)
                    else:
                        # Style correction: replace the entire sentence range
                        log.info("[DEBUG] Style correction: replacing entire sentence range")
                        find_range.HighlightColorIndex = 0
                        find_range.Font.Underline = 0
                        find_range.Text = corrected.strip()
                        find_range.HighlightColorIndex = 4 # wdBrightGreen
                        log.info("Successfully replaced entire sentence for style in Word.")
                        return True
                else:
                    log.info("[DEBUG] Sentence context %r not found in document.", clean_q)

            # ── Phase 2: Global fallback search / Fuzzy patch ─────────────────────
            # Sentence context was not found (user edited it). Fall back to a
            # document-wide fuzzy patch or exact fallback match.
            if original:
                log.info("[DEBUG] Falling back to fuzzy patch / global search for error word: %r", original.strip())
                # Try exact global match first if the word is unique
                global_range = doc.Content
                global_find = global_range.Find
                global_find.ClearFormatting()
                global_find.Text = _normalize_for_search(original.strip())
                global_find.MatchCase = True
                global_find.MatchWholeWord = True    # native boundary guard
                if global_find.Execute():
                    log.info("[DEBUG] Found global error word match range: [%d, %d] -> text: %r", global_range.Start, global_range.End, global_range.Text)
                    self._expand_to_word_boundaries(doc, global_range)
                    global_range.HighlightColorIndex = 0
                    global_range.Font.Underline = 0
                    old_text = global_range.Text
                    global_range.Text = corrected.strip()
                    global_range.HighlightColorIndex = 4 # wdBrightGreen
                    log.info("Successfully replaced %r with %r (original error was %r) globally in Word.", old_text, corrected, original)
                    return True

                # If global search failed (e.g. they mutated the exact word slightly but Mistral matched it earlier)
                # use diff-match-patch fuzzy patching
                from pikachu.utils.text_patcher import TextPatcher
                patcher = TextPatcher()
                if patcher.is_available():
                    log.info("[DEBUG] Exact fallback failed. Trying fuzzy patch for %r -> %r", original, corrected)
                    current_doc_text = doc.Content.Text or ""
                    patched_text = patcher.try_patch(
                        original_text=question if question else original,
                        current_text=current_doc_text,
                        error=original,
                        corrected=corrected
                    )
                    if patched_text and patched_text != current_doc_text:
                        log.info("Fuzzy patch successful. Applying patched text block to document.")
                        # To avoid destroying formatting, we apply the patch structurally via Word COM
                        # (Normally we'd replace doc.Content.Text entirely, but that destroys images/styles.
                        # For now, if we reach this point and we need to replace the whole text, we do so
                        # cautiously or we log that we need a more granular COM patcher.)
                        # As a safe implementation for Phase 2:
                        doc.Content.Text = patched_text
                        return True

                log.info("[DEBUG] Global fallback / fuzzy patch search failed for: %r", original)

            log.warning("Could not locate text to replace in Word: original=%r, question=%r", original, question)
            return False

        except Exception as e:
            log.debug("replace_text_in_active_app COM error: %s", e)
            return False

    def scroll_to_correction(self, class_name: str, correction) -> bool:
        """
        Finds the correction in the active Word document and Selects it.
        This forces Word to scroll to the error and highlight it with a grey selection box.
        """
        if class_name != "OpusApp":
            return False
            
        try:
            import win32com.client
            word = win32com.client.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument
            
            question = correction.question
            original = correction.error
            
            if question:
                clean_q = question.strip().replace("\n", "\r")
                find_range = doc.Content
                find_obj = find_range.Find
                find_obj.ClearFormatting()
                find_obj.Text = clean_q
                find_obj.MatchCase = False
                find_obj.MatchWholeWord = False
                find_obj.MatchWildcards = False

                if find_obj.Execute():
                    if original:
                        error_find = find_range.Find
                        error_find.ClearFormatting()
                        error_find.Text = self._normalize_for_search(original.strip())
                        error_find.MatchCase = True
                        if error_find.Execute():
                            self._expand_to_word_boundaries(doc, find_range)
                            find_range.Select()
                            return True
                    else:
                        find_range.Select()
                        return True

            if original:
                global_range = doc.Content
                global_find = global_range.Find
                global_find.ClearFormatting()
                global_find.Text = self._normalize_for_search(original.strip())
                global_find.MatchCase = True
                if global_find.Execute():
                    self._expand_to_word_boundaries(doc, global_range)
                    global_range.Select()
                    return True
                    
            return False
            
        except Exception as e:
            log.debug("scroll_to_correction failed: %s", e)
            return False

    # ── Highlighting methods ──────────────────────────────────────────────────

    def highlight_corrections_in_word(self, class_name: str, corrections: list, color_index: int = -1) -> None:
        """
        Highlight all corrections in Word using native squiggly underlines.
        """
        if class_name != "OpusApp" or not corrections:
            return
        try:
            import win32com.client
            word = win32com.client.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument
            for c in corrections:
                self._set_correction_highlight(doc, c, True)
        except Exception as e:
            log.debug("highlight_corrections_in_word failed: %s", e)

    def clear_highlights_in_word(self, class_name: str, corrections: list) -> None:
        """
        Clear highlights for a list of corrections.
        """
        if class_name != "OpusApp" or not corrections:
            return
        try:
            import win32com.client
            word = win32com.client.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument
            for c in corrections:
                self._set_correction_highlight(doc, c, False)
        except Exception as e:
            log.debug("clear_highlights_in_word failed: %s", e)

    def _set_correction_highlight(self, doc, correction, apply: bool) -> bool:
        """
        Find the correction's error in the document context and set its wavy underline.
        """
        try:
            question = correction.question
            original = correction.error
            log.info("[DEBUG] _set_correction_highlight called: original=%r, question=%r, apply=%s", original, question, apply)
            
            # Colors: wdColorRed = 255, wdColorBlue = 16711680, wdColorGreen = 65280
            scope_colors = {
                "spelling": 255,
                "grammar": 16711680,
                "style": 65280
            }
            color = scope_colors.get(correction.scope, 255)
            
            def apply_highlight(target_range):
                if apply:
                    target_range.HighlightColorIndex = 6 # wdRed
                else:
                    target_range.HighlightColorIndex = 0 # wdNoHighlight
                    target_range.Font.Underline = 0

            if question:
                clean_q = question.strip().replace("\n", "\r")
                find_range = doc.Content
                find_obj = find_range.Find
                find_obj.ClearFormatting()
                find_obj.Text = clean_q
                find_obj.MatchCase = False
                find_obj.MatchWholeWord = False
                find_obj.MatchWildcards = False

                if find_obj.Execute():
                    if original:
                        # Find specific error within the sentence context
                        error_find = find_range.Find
                        error_find.ClearFormatting()
                        error_find.Text = original.strip()
                        error_find.MatchCase = True
                        if error_find.Execute():
                            self._expand_to_word_boundaries(doc, find_range)
                            apply_highlight(find_range)
                            return True
                    else:
                        # Style correction: highlight the entire sentence range
                        apply_highlight(find_range)
                        return True

            # Fallback global search for the original word/phrase
            if original:
                global_range = doc.Content
                global_find = global_range.Find
                global_find.ClearFormatting()
                global_find.Text = original.strip()
                global_find.MatchCase = True
                if global_find.Execute():
                    self._expand_to_word_boundaries(doc, global_range)
                    apply_highlight(global_range)
                    return True

            return False
        except Exception as e:
            log.debug("_set_correction_highlight failed: %s", e)
            return False

    def _expand_to_word_boundaries(self, doc, find_range) -> None:
        """
        Expands the given find_range to cover full word boundaries (alphanumeric + apostrophes).
        This avoids partial/substring highlighting or replacement issues (e.g. SEN -> Sentencetence).
        """
        try:
            start = find_range.Start
            end = find_range.End
            log.info("[DEBUG] _expand_to_word_boundaries starting range: [%d, %d] -> text: %r", start, end, find_range.Text)
            
            def is_word_char(c: str) -> bool:
                return c.isalnum() or c in ("'", "’")

            # Check character before start
            if start > 0:
                char_before = doc.Range(start - 1, start).Text
                log.info("[DEBUG] Character before start: %r (is_word_char: %s)", char_before, is_word_char(char_before))
            else:
                char_before = ""

            # Check character at end
            char_at_end = doc.Range(end, end + 1).Text
            log.info("[DEBUG] Character after end: %r (is_word_char: %s)", char_at_end, is_word_char(char_at_end))

            expanded = False
            # Expand start backwards
            while start > 0:
                char_before = doc.Range(start - 1, start).Text
                if is_word_char(char_before):
                    start -= 1
                    expanded = True
                else:
                    break

            # Expand end forwards
            while True:
                char_after = doc.Range(end, end + 1).Text
                if is_word_char(char_after):
                    end += 1
                    expanded = True
                else:
                    break

            if expanded:
                find_range.Start = start
                find_range.End = end
                log.info("[DEBUG] Range expanded to: [%d, %d] -> text: %r", start, end, find_range.Text)
            else:
                log.info("[DEBUG] No range expansion needed.")
        except Exception as e:
            log.debug("[DEBUG] _expand_to_word_boundaries failed: %s", e)

