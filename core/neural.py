"""Optional free neural search (sentence embeddings) - runs on CPU, no API key, no cost.

Uses `fastembed` (ONNX runtime) with the small open model BAAI/bge-small-en-v1.5 (~130 MB, downloaded once).
Everything is optional: when the package or the model is not available (for example on a host that blocks
huggingface.co, like the free PythonAnywhere plan) `available()` is False, the menu entry is hidden and the
search silently uses the Hybrid method instead.
Install:  pip install fastembed      (disable with the environment variable STUDYMATE_NEURAL=0)
"""
import os
import threading

import numpy as np

MODEL = os.environ.get("STUDYMATE_NEURAL_MODEL", "BAAI/bge-small-en-v1.5")
_state = {"emb": None, "tried": False}
_lock = threading.Lock()


def _load():
    if os.environ.get("STUDYMATE_NEURAL", "1") == "0":
        return None
    try:
        from fastembed import TextEmbedding
        return TextEmbedding(MODEL)
    except Exception:                                    # not installed / model cannot be downloaded
        return None


def get():
    with _lock:
        if not _state["tried"]:
            _state["tried"] = True
            _state["emb"] = _load()
        return _state["emb"]


def available():
    return get() is not None


def embed(texts):
    """L2-normalised float32 matrix (n, d) or None when the model is not available."""
    e = get()
    if e is None:
        return None
    v = np.asarray(list(e.embed(list(texts))), dtype=np.float32)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
