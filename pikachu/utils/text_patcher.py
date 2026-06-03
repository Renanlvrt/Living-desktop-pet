"""
pikachu/utils/text_patcher.py — Safe asynchronous text patch application.

Uses Google's diff-match-patch (Myers diff algorithm + fuzzy matching) to
safely reconcile an LLM correction that was generated against Text State A
with Text State B (the current, potentially mutated document text).

This solves the race condition where:
  1. The poll loop reads "I cn't do it."            (State A)
  2. Mistral takes 3 seconds to respond with a fix
  3. During those 3 seconds, the user adds more text (State B: "I cn't do it now.")
  4. We still need to apply the fix correctly without corrupting State B

If the user has mutated the text *too heavily* (deleted the entire sentence,
for example), try_patch() returns None and the correction card is silently
discarded rather than corrupting the document.
"""

from __future__ import annotations

from pikachu.utils.logger import get_logger

log = get_logger(__name__)


class TextPatcher:
    """
    Applies a single word-level correction to a potentially-mutated text.

    Usage::

        patcher = TextPatcher()
        result = patcher.try_patch(
            original_text="I cn't do it.",
            current_text="I cn't do it now.",
            error="cn't",
            corrected="can't",
        )
        if result is not None:
            # result == "I can't do it now."
            push_to_word(result)
        else:
            dismiss_stale_card()
    """

    def __init__(self):
        try:
            from diff_match_patch import diff_match_patch
            self._dmp = diff_match_patch()
            # Allow fuzzy matching with up to 600 chars of drift
            self._dmp.Match_Distance = 600
            # Patch tolerance — a score ≥ 0.5 means the patch applies cleanly
            self._dmp.Patch_DeleteThreshold = 0.5
            self._available = True
            log.info("TextPatcher: diff-match-patch loaded successfully.")
        except ImportError:
            self._dmp = None
            self._available = False
            log.warning("TextPatcher: diff-match-patch not installed. Fuzzy patching disabled.")

    # ── Public API ─────────────────────────────────────────────────────────────

    def try_patch(
        self,
        original_text: str,
        current_text: str,
        error: str,
        corrected: str,
    ) -> str | None:
        """
        Try to apply a correction to the current (potentially mutated) text.

        Args:
            original_text:  The exact text that was sent to the LLM.
            current_text:   The current text in the document (may have changed).
            error:          The error string from the LLM response.
            corrected:      The corrected string from the LLM response.

        Returns:
            The patched text string if the correction applied cleanly, or
            ``None`` if the document has drifted too far to apply safely.
        """
        if not self._available or self._dmp is None:
            # Fallback: simple exact replacement on current text
            if error in current_text:
                return current_text.replace(error, corrected, 1)
            return None

        if not error or not original_text:
            return None

        # 1. Build what the corrected text *should* look like (in memory only)
        expected_text = original_text.replace(error, corrected, 1)
        if expected_text == original_text:
            # Nothing to replace — error wasn't in original_text
            log.debug("TextPatcher: error %r not found in original_text.", error)
            return None

        # 2. Generate a structural patch from (original → expected)
        patches = self._dmp.patch_make(original_text, expected_text)
        if not patches:
            log.debug("TextPatcher: patch_make produced no patches.")
            return None

        # 3. Apply the patch to the *current* mutated text
        new_text, results = self._dmp.patch_apply(patches, current_text)

        if all(results):
            log.info(
                "TextPatcher: patch applied cleanly (%d patch(es)).", len(results)
            )
            return new_text
        else:
            failed = sum(1 for r in results if not r)
            log.warning(
                "TextPatcher: %d/%d patch(es) failed — context has drifted too far. "
                "Discarding stale correction (error=%r).",
                failed, len(results), error,
            )
            return None

    def is_available(self) -> bool:
        """Returns True if diff-match-patch was successfully imported."""
        return self._available
