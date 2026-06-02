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
from typing import Optional, List

from pikachu.utils.logger import get_logger

log = get_logger(__name__)


class TextReader:
    """
    Reads the current text content from the active writing application.
    Call ``read_active_app(class_name)`` to auto-dispatch to the right backend.
    """

    # ── Word COM ──────────────────────────────────────────────────────────────

    def read_word(self) -> Optional[str]:
        """
        Read the full text of the active Word document via COM Automation.
        Returns None if Word is not running or no document is open.
        This is non-invasive — Word continues working normally.
        """
        try:
            import win32com.client
            word = win32com.client.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument
            text = doc.Content.Text
            if text:
                # Normalize Word's carriage returns (\r) and vertical tabs (\x0b) to standard newlines (\n)
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

            # 1. Try to find the sentence context first to avoid wrong replacements
            if question:
                # Normalize line endings/spaces to match Word format
                clean_q = question.strip().replace("\n", "\r")
                find_range = doc.Content
                find_obj = find_range.Find
                find_obj.ClearFormatting()
                find_obj.Text = clean_q
                find_obj.MatchCase = False
                find_obj.MatchWholeWord = False
                find_obj.MatchWildcards = False

                if find_obj.Execute():
                    # If the sentence range was found, replace within that range
                    if original:
                        error_find = find_range.Find
                        error_find.ClearFormatting()
                        error_find.Text = original.strip()
                        error_find.MatchCase = True
                        if error_find.Execute():
                            # Clear highlight of error range before replacement
                            find_range.HighlightColorIndex = 0 # wdNoHighlight
                            find_range.Text = corrected.strip()
                            find_range.HighlightColorIndex = 0 # Ensure replaced text is clean
                            log.info("Successfully replaced '%s' with '%s' in Word sentence context.", original, corrected)
                            return True
                    else:
                        # Style correction: replace the entire sentence range
                        find_range.HighlightColorIndex = 0 # wdNoHighlight
                        find_range.Text = corrected.strip()
                        find_range.HighlightColorIndex = 0
                        log.info("Successfully replaced entire sentence for style in Word.")
                        return True

            # 2. Global fallback search for the original word/phrase
            if original:
                global_range = doc.Content
                global_find = global_range.Find
                global_find.ClearFormatting()
                global_find.Text = original.strip()
                global_find.MatchCase = True
                if global_find.Execute():
                    global_range.HighlightColorIndex = 0 # wdNoHighlight
                    global_range.Text = corrected.strip()
                    global_range.HighlightColorIndex = 0
                    log.info("Successfully replaced '%s' with '%s' globally in Word.", original, corrected)
                    return True

            log.warning("Could not locate text to replace in Word: original=%r, question=%r", original, question)
            return False

        except Exception as e:
            log.error("replace_text_in_active_app failed: %s", e)
            return False

    # ── Highlighting methods ──────────────────────────────────────────────────

    def highlight_corrections_in_word(self, class_name: str, corrections: list, color_index: int = 4) -> None:
        """
        Highlight all corrections in Word using the specified color index (e.g. 4 = wdGreen).
        """
        if class_name != "OpusApp" or not corrections:
            return
        try:
            import win32com.client
            word = win32com.client.GetActiveObject("Word.Application")
            doc  = word.ActiveDocument
            for c in corrections:
                self._set_correction_highlight(doc, c, color_index)
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
                self._set_correction_highlight(doc, c, 0) # 0 = wdNoHighlight
        except Exception as e:
            log.debug("clear_highlights_in_word failed: %s", e)

    def _set_correction_highlight(self, doc, correction, color_index: int) -> bool:
        """
        Find the correction's error in the document context and set its highlight color.
        """
        try:
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
                        # Find specific error within the sentence context
                        error_find = find_range.Find
                        error_find.ClearFormatting()
                        error_find.Text = original.strip()
                        error_find.MatchCase = True
                        if error_find.Execute():
                            find_range.HighlightColorIndex = color_index
                            return True
                    else:
                        # Style correction: highlight the entire sentence range
                        find_range.HighlightColorIndex = color_index
                        return True

            # Fallback global search for the original word/phrase
            if original:
                global_range = doc.Content
                global_find = global_range.Find
                global_find.ClearFormatting()
                global_find.Text = original.strip()
                global_find.MatchCase = True
                if global_find.Execute():
                    global_range.HighlightColorIndex = color_index
                    return True

            return False
        except Exception as e:
            log.debug("_set_correction_highlight failed: %s", e)
            return False

