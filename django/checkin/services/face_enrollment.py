from __future__ import annotations

import base64
from typing import Iterable

import numpy as np

from .face_encoder import encode_image_file
from .faiss_index import face_index




def _decode_data_url(data_url: str) -> bytes:
    if data_url.startswith('data:'):
        _, b64data = data_url.split(',', 1)
        return base64.b64decode(b64data)
    return base64.b64decode(data_url)


def register_employee_faces(employee_id: int, image_data: Iterable[str]) -> np.ndarray:
    embeddings: list[np.ndarray] = []
    for offset, entry in enumerate(image_data, start=1):
        try:
            image_bytes = _decode_data_url(entry)
        except (base64.binascii.Error, ValueError) as exc:
            raise ValueError('Unable to decode captured image data.') from exc
        embedding = encode_image_file(image_bytes, employee_id, False)
        # Convert embedding from (1,256) to (256,)
        vector = embedding.flatten().astype('float32')
        embeddings.append(vector)
        face_index.upsert_vector(employee_id * 100 + offset, vector)
    return np.asarray(embeddings, dtype='float32')



def remove_employee_faces(employee_id: int) -> None:
    for offset in range(1, 101):
        face_index.remove_id(employee_id * 100 + offset)
