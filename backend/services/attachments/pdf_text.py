"""Extract bounded, page-labelled text from large PDFs in a separate process."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


async def extract_pdf_text(data: bytes, byte_budget: int, *, conversation_id: str = "") -> str:
    """Keep the PDF off the JSON/IPC path and reap the worker on timeout."""
    from services.memory_diagnostics import log_memory_snapshot

    with TemporaryDirectory(prefix="areqa-pdf-") as directory:
        source = Path(directory) / "upload.pdf"
        source.write_bytes(data)
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).resolve()), str(source), str(byte_budget),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
        except asyncio.TimeoutError:
            log_memory_snapshot(
                "pdf_text_worker_timeout", conversation_id=conversation_id, attachment_bytes=len(data),
            )
            raise
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.communicate()
        if process.returncode or not stdout.strip():
            log_memory_snapshot(
                "pdf_text_worker_failed", conversation_id=conversation_id, attachment_bytes=len(data),
                worker_returncode=process.returncode,
            )
            raise ValueError("pdf_text_unavailable")
        return stdout.decode("utf-8")


def _extract(path: str, byte_budget: int) -> str:
    import pymupdf

    with pymupdf.open(path, filetype="pdf") as document:
        page_count = document.page_count
        if document.needs_pass or not page_count:
            return ""
        sample_count = min(page_count, 120)
        page_budget = max(0, byte_budget // sample_count - 32)
        truncated = sample_count < page_count
        excerpts = []
        for sample in range(sample_count):
            index = sample * (page_count - 1) // max(1, sample_count - 1)
            text = document[index].get_text().strip().encode("utf-8")
            if text:
                truncated |= len(text) > page_budget
                excerpt = text[:page_budget].decode("utf-8", errors="ignore")
                excerpts.append(f"[PDF page {index + 1}]\n{excerpt}")
        if not excerpts:
            return ""
        if truncated:
            excerpts.insert(0, "[PDF text excerpts only. Omitted content and images are unavailable.]")
        else:
            excerpts.insert(0, "[Extracted PDF text. Original images are unavailable.]")
        return "\n\n".join(excerpts)


if __name__ == "__main__":
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (192 * 1024 * 1024,) * 2)
    sys.stdout.buffer.write(_extract(sys.argv[1], int(sys.argv[2])).encode("utf-8"))
