from __future__ import annotations

import subprocess
import threading
from time import monotonic

import pytesseract
from PIL.Image import Image
from pytesseract import TesseractError, TesseractNotFoundError

from app.documents.ocr.base import OCRError, OCRProvider, OCRRuntimeInfo

PROBE_TIMEOUT_SECONDS = 10.0


class TesseractOCRProvider(OCRProvider):
    """Local Tesseract integration with safe arguments and bounded concurrency."""

    def __init__(self, language: str, max_concurrency: int = 1) -> None:
        self.language = language
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self._probe_lock = threading.Lock()
        self._runtime_info: OCRRuntimeInfo | None = None

    def verify(self, timeout_seconds: float) -> OCRRuntimeInfo:
        if self._runtime_info is not None:
            return self._runtime_info
        with self._probe_lock:
            if self._runtime_info is not None:
                return self._runtime_info
            probe_timeout = max(0.001, min(timeout_seconds, PROBE_TIMEOUT_SECONDS))
            deadline = monotonic() + probe_timeout
            try:
                version_result = subprocess.run(
                    ["tesseract", "--version"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self._remaining_seconds(deadline),
                )
                languages_result = subprocess.run(
                    ["tesseract", "--list-langs"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self._remaining_seconds(deadline),
                )
            except FileNotFoundError as exc:
                raise OCRError(
                    "OCR_UNAVAILABLE",
                    "Local OCR is unavailable on this server",
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise OCRError(
                    "OCR_TIMEOUT",
                    "OCR exceeded the configured time limit",
                ) from exc
            except (OSError, subprocess.SubprocessError) as exc:
                raise OCRError(
                    "OCR_UNAVAILABLE",
                    "Local OCR is unavailable on this server",
                ) from exc

            version_lines = version_result.stdout.splitlines()
            if not version_lines:
                raise OCRError(
                    "OCR_UNAVAILABLE",
                    "Local OCR is unavailable on this server",
                )
            first_line = version_lines[0].strip()
            prefix = "tesseract "
            engine_version = (
                first_line[len(prefix):].strip()
                if first_line.casefold().startswith(prefix)
                else first_line
            )
            if not engine_version:
                raise OCRError(
                    "OCR_UNAVAILABLE",
                    "Local OCR is unavailable on this server",
                )
            installed_languages = {
                line.strip()
                for line in languages_result.stdout.splitlines()
                if line.strip()
                and not line.casefold().startswith("list of available languages")
            }
            requested_languages = set(self.language.split("+"))
            if not requested_languages.issubset(installed_languages):
                raise OCRError(
                    "OCR_LANGUAGE_UNAVAILABLE",
                    "The configured OCR language is not installed",
                )
            self._runtime_info = OCRRuntimeInfo(
                engine="tesseract",
                version=engine_version[:50],
                language=self.language,
            )
            return self._runtime_info

    def recognize(self, image: Image, timeout_seconds: float) -> str:
        self.verify(timeout_seconds)
        deadline = monotonic() + timeout_seconds
        if timeout_seconds <= 0 or not self._semaphore.acquire(timeout=timeout_seconds):
            raise OCRError("OCR_TIMEOUT", "OCR exceeded the configured time limit")
        try:
            remaining = self._remaining_seconds(deadline)
            if remaining <= 0:
                raise OCRError("OCR_TIMEOUT", "OCR exceeded the configured time limit")
            return pytesseract.image_to_string(
                image,
                lang=self.language,
                timeout=remaining,
            )
        except TesseractNotFoundError as exc:
            raise OCRError(
                "OCR_UNAVAILABLE",
                "Local OCR is unavailable on this server",
            ) from exc
        except RuntimeError as exc:
            raise OCRError(
                "OCR_TIMEOUT",
                "OCR exceeded the configured time limit",
            ) from exc
        except TesseractError as exc:
            raise OCRError(
                "OCR_PROCESSING_FAILED",
                "The page could not be processed by local OCR",
            ) from exc
        except (OSError, ValueError) as exc:
            raise OCRError(
                "OCR_PROCESSING_FAILED",
                "The page could not be processed by local OCR",
            ) from exc
        finally:
            self._semaphore.release()

    @staticmethod
    def _remaining_seconds(deadline: float) -> float:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise OCRError("OCR_TIMEOUT", "OCR exceeded the configured time limit")
        return remaining
