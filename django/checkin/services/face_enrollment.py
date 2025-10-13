from __future__ import annotations

import base64
from typing import Iterable

import numpy as np

from .face_encoder import encode_image_file
from .faiss_index import face_index


def _employee_id_to_index(employee_id: str) -> int:
    try:
        return int(employee_id)
    except (TypeError, ValueError) as exc:  # ensure deterministic ids
        raise ValueError('Employee ID must be numeric to register embeddings.') from exc


def _decode_data_url(data_url: str) -> bytes:
    if data_url.startswith('data:'):
        _, b64data = data_url.split(',', 1)
        return base64.b64decode(b64data)
    return base64.b64decode(data_url)


def register_employee_faces(employee_id: str, image_data: Iterable[str]) -> np.ndarray:
    embeddings = []
    for entry in image_data:
        try:
            image_bytes = _decode_data_url(entry)
        except (base64.binascii.Error, ValueError) as exc:
            raise ValueError('Unable to decode captured image data.') from exc
        embedding = encode_image_file(image_bytes)
        embeddings.append(embedding.astype('float32'))

    if not embeddings:
        raise ValueError('At least one face capture is required.')

    vectors = np.stack(embeddings, axis=0)
    vector = np.mean(vectors, axis=0).astype('float32')
    if vector.shape[0] == 0:
        raise ValueError('Generated embedding is empty.')
    index_id = _employee_id_to_index(employee_id)
    face_index.upsert_vector(index_id, vector)
    return vector


def remove_employee_faces(employee_id: str) -> None:
    index_id = _employee_id_to_index(employee_id)
    face_index.remove_id(index_id)
