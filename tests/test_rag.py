"""
tests/test_rag.py

Tests for the RAG pipeline: chunker, embedder, retriever.

Mocking strategy:
- chunker.py: pure functions, no I/O -> tested directly, no mocks needed.
- embedder.py: SentenceTransformer loads a real ~80MB model from HuggingFace
  on first call. We NEVER let that happen in tests -- it's slow, needs network,
  and will fail/hang in CI. We mock the model object itself.
- retriever.py: talks to real Pinecone over the network via the `Pinecone` class.
  We mock `Pinecone` (and the embedder functions it calls) so zero real API
  calls happen. This is why conftest.py sets fake PINECONE_API_KEY -- it only
  needs to exist, never needs to be valid, because we never reach the network.

Patch location rule: we patch `app.rag.retriever.Pinecone`, not `pinecone.Pinecone`.
This is "patch where it's used, not where it's defined" -- it keeps the mock
scoped to this module's import of the name, so it can't leak into other tests.
"""
import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from app.rag.chunker import chunk_diff, CodeChunk, _split_by_file, _split_by_hunk, _sliding_window
from app.rag import embedder
from app.rag import retriever


# ---------------------------------------------------------------------------
# Fixtures: realistic sample data shared across tests
# ---------------------------------------------------------------------------

@pytest.fixture
def small_diff():
    """A minimal, realistic single-file, single-hunk diff."""
    return (
        "diff --git a/app/main.py b/app/main.py\n"
        "index 1234567..89abcde 100644\n"
        "--- a/app/main.py\n"
        "+++ b/app/main.py\n"
        "@@ -1,3 +1,4 @@\n"
        " def hello():\n"
        "+    print('hi')\n"
        "     return True\n"
    )


@pytest.fixture
def multi_file_diff():
    """Two files, one hunk each."""
    return (
        "diff --git a/app/a.py b/app/a.py\n"
        "index 111..222 100644\n"
        "--- a/app/a.py\n"
        "+++ b/app/a.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def a():\n"
        "+    pass\n"
        "diff --git a/app/b.py b/app/b.py\n"
        "index 333..444 100644\n"
        "--- a/app/b.py\n"
        "+++ b/app/b.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def b():\n"
        "+    pass\n"
    )


@pytest.fixture
def multi_hunk_diff():
    """One file, two separate hunks."""
    return (
        "diff --git a/app/c.py b/app/c.py\n"
        "index 555..666 100644\n"
        "--- a/app/c.py\n"
        "+++ b/app/c.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def one():\n"
        "+    pass\n"
        "@@ -10,2 +10,2 @@\n"
        " def two():\n"
        "+    pass\n"
    )


@pytest.fixture
def sample_chunk():
    return CodeChunk(
        content="def foo(): pass",
        chunk_index=0,
        pr_number=42,
        repo="user/auto-reviewer",
        file_hint="app/foo.py",
    )


# ---------------------------------------------------------------------------
# chunker.py
# ---------------------------------------------------------------------------

class TestChunkDiff:

    def test_empty_diff_returns_empty_list(self):
        assert chunk_diff("", pr_number=1, repo="user/repo") == []

    def test_whitespace_only_diff_returns_empty_list(self):
        assert chunk_diff("   \n\n  \n", pr_number=1, repo="user/repo") == []

    def test_none_like_falsy_diff_returns_empty_list(self):
        # chunk_diff explicitly checks `if not diff_text`, so this must be safe.
        assert chunk_diff(None, pr_number=1, repo="user/repo") == []

    def test_single_small_hunk_produces_one_chunk(self, small_diff):
        chunks = chunk_diff(small_diff, pr_number=7, repo="user/repo")
        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.pr_number == 7
        assert chunk.repo == "user/repo"
        assert chunk.chunk_index == 0
        assert "def hello" in chunk.content

    def test_multi_file_diff_separates_file_hints(self, multi_file_diff):
        chunks = chunk_diff(multi_file_diff, pr_number=1, repo="user/repo")
        file_hints = {c.file_hint for c in chunks}
        assert "a.py" in {h.split("/")[-1] for h in file_hints}
        assert "b.py" in {h.split("/")[-1] for h in file_hints}
        assert len(chunks) == 2

    def test_multi_hunk_single_file_produces_separate_chunks(self, multi_hunk_diff):
        chunks = chunk_diff(multi_hunk_diff, pr_number=1, repo="user/repo")
        assert len(chunks) == 2
        # Both chunks should share the same file_hint since it's one file
        assert chunks[0].file_hint == chunks[1].file_hint
        assert "def one" in chunks[0].content
        assert "def two" in chunks[1].content

    def test_chunk_index_increments_sequentially(self, multi_file_diff):
        chunks = chunk_diff(multi_file_diff, pr_number=1, repo="user/repo")
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_large_hunk_triggers_sliding_window(self):
        # Build a hunk well over the default max_chunk_size (512 chars)
        big_hunk = "@@ -1,100 +1,100 @@\n" + ("+    line of code here\n" * 60)
        diff = f"diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n{big_hunk}"
        chunks = chunk_diff(diff, pr_number=1, repo="user/repo", max_chunk_size=512, overlap=50)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.content) <= 512

    def test_sliding_window_overlap_shares_content(self):
        text = "A" * 1000
        windows = _sliding_window(text, size=512, overlap=50)
        assert len(windows) >= 2
        # The tail of window[0] should overlap with the head of window[1]
        # because step = size - overlap means windows[1] starts 50 chars
        # before window[0] ends.
        overlap_region = windows[0][-50:]
        assert overlap_region in windows[1]

    def test_pr_number_and_repo_stamped_on_every_chunk(self, multi_file_diff):
        chunks = chunk_diff(multi_file_diff, pr_number=99, repo="acme/widgets")
        assert all(c.pr_number == 99 for c in chunks)
        assert all(c.repo == "acme/widgets" for c in chunks)

    def test_malformed_diff_without_git_header_does_not_crash(self):
        # No "diff --git" line at all -- just raw hunk-like text.
        ragged = "@@ -1,2 +1,2 @@\n some code\n+added line\n"
        chunks = chunk_diff(ragged, pr_number=1, repo="user/repo")
        # Should not raise; should still produce at least the content as a chunk
        # under whatever file_hint ("") it falls back to.
        assert isinstance(chunks, list)


class TestSplitByFile:

    def test_extracts_filename_from_git_header(self):
        diff = "diff --git a/app/foo.py b/app/foo.py\n+some change\n"
        sections = _split_by_file(diff)
        assert len(sections) == 1
        file_hint, content = sections[0]
        assert file_hint == "app/foo.py"

    def test_multiple_files_produce_multiple_sections(self, multi_file_diff):
        sections = _split_by_file(multi_file_diff)
        assert len(sections) == 2


class TestSplitByHunk:

    def test_splits_on_at_markers(self, multi_hunk_diff):
        # Grab just the second file's section text for a focused test
        sections = _split_by_file(multi_hunk_diff)
        _, section_text = sections[0]
        hunks = _split_by_hunk(section_text)
        assert len(hunks) == 2
        assert hunks[0].startswith("diff --git") is False or "@@ -1,2" in hunks[0]
        assert "@@ -10,2" in hunks[1]


# ---------------------------------------------------------------------------
# embedder.py
# ---------------------------------------------------------------------------

class TestEmbedder:

    def setup_method(self):
        # Reset the module-level singleton before each test so tests don't
        # leak state into each other (e.g. a prior test's mock model object
        # sticking around for the next test).
        embedder._model = None

    def teardown_method(self):
        embedder._model = None

    @patch("app.rag.embedder.SentenceTransformer")
    def test_get_model_loads_once_and_caches(self, mock_st_class):
        mock_instance = MagicMock()
        mock_st_class.return_value = mock_instance

        first = embedder.get_model()
        second = embedder.get_model()

        # Constructor called exactly once, despite two get_model() calls --
        # this proves the singleton pattern is working.
        mock_st_class.assert_called_once_with(embedder.MODEL_NAME)
        assert first is second

    @patch("app.rag.embedder.SentenceTransformer")
    def test_embed_texts_converts_numpy_to_python_floats(self, mock_st_class):
        mock_instance = MagicMock()
        # Simulate a real model returning a numpy array
        mock_instance.encode.return_value = np.array([[0.1, 0.2, 0.3]])
        mock_st_class.return_value = mock_instance

        result = embedder.embed_texts(["some code"])

        assert isinstance(result, list)
        assert isinstance(result[0], list)
        # Pinecone rejects numpy float types -- must be plain Python float
        assert all(isinstance(x, float) for x in result[0])
        mock_instance.encode.assert_called_once_with(["some code"], show_progress_bar=False)

    @patch("app.rag.embedder.SentenceTransformer")
    def test_embed_texts_empty_list(self, mock_st_class):
        mock_instance = MagicMock()
        mock_instance.encode.return_value = np.array([])
        mock_st_class.return_value = mock_instance

        result = embedder.embed_texts([])
        assert result == []

    @patch("app.rag.embedder.SentenceTransformer")
    def test_embed_single_returns_first_vector_only(self, mock_st_class):
        mock_instance = MagicMock()
        mock_instance.encode.return_value = np.array([[0.5, 0.6]])
        mock_st_class.return_value = mock_instance

        result = embedder.embed_single("one string")

        assert result == [0.5, 0.6]


# ---------------------------------------------------------------------------
# retriever.py
# ---------------------------------------------------------------------------

class TestGetClient:

    def test_raises_if_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("PINECONE_API_KEY", raising=False)
        with pytest.raises(ValueError, match="PINECONE_API_KEY"):
            retriever._get_client()


class TestUpsertChunks:

    def test_empty_chunk_list_returns_zero_without_calling_pinecone(self):
        with patch("app.rag.retriever.Pinecone") as mock_pinecone_class:
            result = retriever.upsert_chunks([])
            assert result == 0
            # Short-circuit means we never even construct a client
            mock_pinecone_class.assert_not_called()

    @patch("app.rag.retriever.embed_texts")
    @patch("app.rag.retriever.Pinecone")
    def test_upsert_calls_index_upsert_with_correct_shape(
        self, mock_pinecone_class, mock_embed_texts, sample_chunk
    ):
        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone_class.return_value = mock_client
        mock_embed_texts.return_value = [[0.1, 0.2, 0.3]]

        count = retriever.upsert_chunks([sample_chunk])

        assert count == 1
        mock_index.upsert.assert_called_once()
        call_kwargs = mock_index.upsert.call_args.kwargs
        vectors = call_kwargs["vectors"]
        assert len(vectors) == 1
        assert vectors[0]["values"] == [0.1, 0.2, 0.3]
        assert vectors[0]["metadata"]["pr_number"] == sample_chunk.pr_number
        assert vectors[0]["metadata"]["repo"] == sample_chunk.repo
        assert vectors[0]["metadata"]["file_hint"] == sample_chunk.file_hint
        assert "id" in vectors[0]

    @patch("app.rag.retriever.embed_texts")
    @patch("app.rag.retriever.Pinecone")
    def test_upsert_batches_over_100_chunks(self, mock_pinecone_class, mock_embed_texts):
        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone_class.return_value = mock_client

        chunks = [
            CodeChunk(content=f"chunk {i}", chunk_index=i, pr_number=1, repo="user/repo")
            for i in range(150)
        ]
        mock_embed_texts.return_value = [[0.0] * 3 for _ in range(150)]

        count = retriever.upsert_chunks(chunks)

        assert count == 150
        # 150 vectors at batch_size 100 -> two .upsert() calls (100 + 50)
        assert mock_index.upsert.call_count == 2
        first_batch = mock_index.upsert.call_args_list[0].kwargs["vectors"]
        second_batch = mock_index.upsert.call_args_list[1].kwargs["vectors"]
        assert len(first_batch) == 100
        assert len(second_batch) == 50

    @patch("app.rag.retriever.embed_texts")
    @patch("app.rag.retriever.Pinecone")
    def test_upsert_truncates_content_in_metadata(self, mock_pinecone_class, mock_embed_texts):
        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone_class.return_value = mock_client
        mock_embed_texts.return_value = [[0.1]]

        huge_chunk = CodeChunk(
            content="x" * 2000, chunk_index=0, pr_number=1, repo="user/repo"
        )
        retriever.upsert_chunks([huge_chunk])

        vectors = mock_index.upsert.call_args.kwargs["vectors"]
        assert len(vectors[0]["metadata"]["content"]) == 1000


class TestMakeVectorId:

    def test_deterministic_same_input_same_id(self, sample_chunk):
        id1 = retriever._make_vector_id(sample_chunk)
        id2 = retriever._make_vector_id(sample_chunk)
        assert id1 == id2

    def test_different_chunk_index_different_id(self, sample_chunk):
        other = CodeChunk(
            content=sample_chunk.content,
            chunk_index=1,  # only this differs
            pr_number=sample_chunk.pr_number,
            repo=sample_chunk.repo,
        )
        assert retriever._make_vector_id(sample_chunk) != retriever._make_vector_id(other)

    def test_different_repo_different_id(self, sample_chunk):
        other = CodeChunk(
            content=sample_chunk.content,
            chunk_index=sample_chunk.chunk_index,
            pr_number=sample_chunk.pr_number,
            repo="someone-else/other-repo",
        )
        assert retriever._make_vector_id(sample_chunk) != retriever._make_vector_id(other)


class TestQuerySimilar:

    @patch("app.rag.retriever.embed_single")
    @patch("app.rag.retriever.Pinecone")
    def test_query_returns_reshaped_metadata(self, mock_pinecone_class, mock_embed_single):
        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone_class.return_value = mock_client
        mock_embed_single.return_value = [0.1, 0.2]

        mock_index.query.return_value = {
            "matches": [
                {
                    "score": 0.95,
                    "metadata": {
                        "content": "def foo(): pass",
                        "pr_number": 5,
                        "repo": "user/repo",
                        "file_hint": "foo.py",
                    },
                }
            ]
        }

        results = retriever.query_similar("find foo function")

        assert len(results) == 1
        assert results[0]["score"] == 0.95
        assert results[0]["content"] == "def foo(): pass"
        assert results[0]["pr_number"] == 5

    @patch("app.rag.retriever.embed_single")
    @patch("app.rag.retriever.Pinecone")
    def test_query_with_filter_repo_includes_filter(self, mock_pinecone_class, mock_embed_single):
        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone_class.return_value = mock_client
        mock_embed_single.return_value = [0.1]
        mock_index.query.return_value = {"matches": []}

        retriever.query_similar("query text", filter_repo="user/repo")

        call_kwargs = mock_index.query.call_args.kwargs
        assert call_kwargs["filter"] == {"repo": {"$eq": "user/repo"}}

    @patch("app.rag.retriever.embed_single")
    @patch("app.rag.retriever.Pinecone")
    def test_query_without_filter_repo_omits_filter(self, mock_pinecone_class, mock_embed_single):
        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone_class.return_value = mock_client
        mock_embed_single.return_value = [0.1]
        mock_index.query.return_value = {"matches": []}

        retriever.query_similar("query text")

        call_kwargs = mock_index.query.call_args.kwargs
        assert "filter" not in call_kwargs

    @patch("app.rag.retriever.embed_single")
    @patch("app.rag.retriever.Pinecone")
    def test_query_propagates_pinecone_errors(self, mock_pinecone_class, mock_embed_single):
        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone_class.return_value = mock_client
        mock_embed_single.return_value = [0.1]
        mock_index.query.side_effect = RuntimeError("Pinecone unavailable")

        # query_similar has no try/except, so the error should bubble up --
        # this test documents and locks in that behavior. If someone later
        # adds silent error-swallowing, this test will catch the regression.
        with pytest.raises(RuntimeError, match="Pinecone unavailable"):
            retriever.query_similar("query text")

    @patch("app.rag.retriever.embed_single")
    @patch("app.rag.retriever.Pinecone")
    def test_query_respects_top_k(self, mock_pinecone_class, mock_embed_single):
        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone_class.return_value = mock_client
        mock_embed_single.return_value = [0.1]
        mock_index.query.return_value = {"matches": []}

        retriever.query_similar("query text", top_k=10)

        call_kwargs = mock_index.query.call_args.kwargs
        assert call_kwargs["top_k"] == 10