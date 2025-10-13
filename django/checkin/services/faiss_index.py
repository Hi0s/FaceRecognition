from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import List, Tuple

import faiss  # type: ignore
import numpy as np
from django.conf import settings

_DIMENSION = 256
_INDEX_PATH = Path(settings.BASE_DIR) / 'faiss_index.bin'
_LOCK = Lock()


class FaceIndex:
    def __init__(self) -> None:
        self._index: faiss.IndexIDMap | None = None

    def _create_index(self) -> faiss.IndexIDMap:
        base_index = faiss.IndexFlatL2(_DIMENSION)
        return faiss.IndexIDMap(base_index)

    def ensure_loaded(self) -> None:
        if self._index is not None:
            return
        with _LOCK:
            if self._index is not None:
                return
            if _INDEX_PATH.exists():
                self._index = faiss.read_index(str(_INDEX_PATH))
            else:
                self._index = self._create_index()

    def _save(self) -> None:
        if self._index is None:
            return
        faiss.write_index(self._index, str(_INDEX_PATH))

    def upsert_vector(self, idx: int, vector: np.ndarray) -> None:
        self.ensure_loaded()
        with _LOCK:
            if self._index is None:
                raise RuntimeError('FAISS index is not initialised.')
            if vector.ndim != 1:
                raise ValueError('Vector must be 1-dimensional.')
            id_array = np.asarray([idx], dtype='int64')
            self._index.remove_ids(id_array)
            self._index.add_with_ids(vector.astype('float32')[np.newaxis, :], id_array)
            self._save()

    def remove_id(self, idx: int) -> None:
        self.ensure_loaded()
        with _LOCK:
            if self._index is None:
                return
            id_array = np.asarray([idx], dtype='int64')
            self._index.remove_ids(id_array)
            self._save()

    def search(self, vector: np.ndarray, k: int = 1) -> List[Tuple[int, float]]:
        self.ensure_loaded()
        if vector.ndim == 1:
            vector = np.expand_dims(vector, axis=0)
        distances, indices = self._index.search(vector.astype('float32'), k)
        results: List[Tuple[int, float]] = []
        for idx, distance in zip(indices[0], distances[0]):
            if idx == -1:
                continue
            results.append((int(idx), float(distance)))
        return results


face_index = FaceIndex()


def reset_index_cache() -> None:
    global face_index
    with _LOCK:
        face_index = FaceIndex()
        face_index.ensure_loaded()
