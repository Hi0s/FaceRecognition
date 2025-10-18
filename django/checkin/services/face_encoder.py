import base64
import logging
from pathlib import Path
from time import time
from typing import Iterable, List

import numpy as np
import tensorflow as tf
from django.conf import settings

_MODEL = None
_INPUT_SHAPE = (256, 256, 3)
_KERAS_MODEL_PATH = Path(settings.BASE_DIR) / 'encoder_celeb_Inception.keras'
_LOGGER = logging.getLogger(__name__)


def get_embedding_model(input_shape: tuple[int, int, int] = _INPUT_SHAPE) -> tf.keras.Model:
    """Reconstruct the embedding network exactly as trained."""
    base_model = tf.keras.applications.InceptionResNetV2(
        input_shape=input_shape,
        include_top=False,
        weights='imagenet',
        pooling='avg',
    )
    for layer in base_model.layers[:-30]:
        layer.trainable = False
    for layer in base_model.layers[-30:]:
        layer.trainable = True

    model = tf.keras.Sequential(
        [
            base_model,
            tf.keras.layers.Flatten(),
            tf.keras.layers.Dense(512, activation='relu'),
            tf.keras.layers.BatchNormalization(),
            tf.keras.layers.Dense(256, activation='relu'),
            tf.keras.layers.Lambda(lambda x: tf.math.l2_normalize(x, axis=1)),
        ],
        name='Embedding',
    )
    return model


def _build_embedding_model() -> tf.keras.Model:
    return get_embedding_model(_INPUT_SHAPE)


def _load_model() -> tf.keras.Model:
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    if _KERAS_MODEL_PATH.exists():
        model = _build_embedding_model()
        model.load_weights(_KERAS_MODEL_PATH)
        _MODEL = model
        return _MODEL

    raise FileNotFoundError('Encoder model keras file not found.')





def _preprocess_image_bytes(image_bytes: bytes) -> tf.Tensor:
    image = tf.io.decode_image(image_bytes, channels=3, expand_animations=False)
    image = tf.image.convert_image_dtype(image, tf.float32)
    image = tf.image.resize(image, _INPUT_SHAPE[:2])
    return image


def _decode_data_url(data_url: str) -> bytes:
    if data_url.startswith('data:'):
        header, b64data = data_url.split(',', 1)
        return base64.b64decode(b64data)
    return base64.b64decode(data_url)


def encode_image_file(image_bytes: bytes, employee_id: int, recognize: bool) -> np.ndarray:
    model = _load_model()
    tensor = _preprocess_image_bytes(image_bytes)
    if settings.DEBUG:
        try:
            debug_tensor = tf.image.convert_image_dtype(tensor, dtype=tf.uint8, saturate=True)
            if recognize: 
                 tf.io.write_file(
                f'image.jpg',
                tf.image.encode_jpeg(debug_tensor),
                ) 
            else:  
                tf.io.write_file(
                    f'image/employee_{employee_id}/image_{int(time())}.jpg',
                    tf.image.encode_jpeg(debug_tensor),
                )
        except Exception as exc:
            _LOGGER.warning('Failed to write debug image for %s: %s', employee_id, exc)
    batch = tf.expand_dims(tensor, axis=0)
    embedding = model.predict(batch)
    return embedding
