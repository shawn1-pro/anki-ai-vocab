"""Errors safe to display without exposing credentials or server response bodies."""


class VocabError(Exception):
    """An actionable application error."""


class ValidationError(VocabError):
    """Invalid input or generated learning content."""


class GenerationError(VocabError):
    """The remote generation could not be completed."""


class AnkiError(VocabError):
    """AnkiConnect connection, schema, or operation error."""


class ClipboardError(VocabError):
    """No usable text could be read from the desktop clipboard."""
