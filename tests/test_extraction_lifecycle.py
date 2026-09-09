"""The async owner retains its tempfile and capacity until guard cleanup."""

import asyncio
from pathlib import Path
import threading

import pytest

import analysis.analyzer_async as analyzer_module
from analysis.analyzer_async import AsyncAnalyzer
from parsing.subprocess_guard import GuardCancelled
from pipeline.document_artifacts import make_artifact


def test_cancelled_extraction_cleans_worker_before_deleting_tempfile(monkeypatch):
    started = threading.Event()
    cleaned = threading.Event()
    paths = []

    async def acquire(url, banana=None):
        return make_artifact(
            requested_url=url, source_url=url, data=b'%PDF-test', content_sha256='test',
        )

    def extract(path, *args, cancel_event):
        paths.append(Path(path))
        started.set()
        assert cancel_event.wait(5), 'async cancellation never reached worker'
        assert Path(path).exists(), 'tempfile deleted while worker still owned it'
        cleaned.set()
        raise GuardCancelled('cleaned')

    monkeypatch.setattr(analyzer_module, 'get_corpus', lambda: None)
    monkeypatch.setattr(analyzer_module, '_extract_pdf_in_subprocess', extract)
    analyzer = AsyncAnalyzer(enable_llm=False)
    analyzer.acquire_document_async = acquire

    async def check():
        task = asyncio.create_task(analyzer.extract_document_async('https://example.test/a.pdf'))
        try:
            async with asyncio.timeout(5):
                while not started.is_set():
                    await asyncio.sleep(0.01)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert cleaned.is_set()
        assert not paths[0].exists()

    asyncio.run(check())
