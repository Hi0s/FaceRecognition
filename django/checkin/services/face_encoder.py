import base64
import logging
from pathlib import Path
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
        _MODEL = tf.keras.models.load_model(_KERAS_MODEL_PATH, compile=False)
        return _MODEL

    raise FileNotFoundError('Encoder model keras file not found.')



# Load the model once when the module is imported so predictions are ready.
try:
    _load_model()
except Exception as exc:  # pylint: disable=broad-except
    _LOGGER.warning("Face encoder model not loaded at startup: %s", exc)


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


def encode_base64_images(data_urls: Iterable[str]) -> np.ndarray:
    model = _load_model()
    tensors: List[tf.Tensor] = []
    for data_url in data_urls:
        image_bytes = _decode_data_url(data_url)
        tensors.append(_preprocess_image_bytes(image_bytes))

    if not tensors:
        raise ValueError('At least one image is required to encode.')

    batch = tf.stack(tensors, axis=0)
    embeddings = model(batch, training=False)
    return embeddings.numpy().astype('float32')


def encode_image_file(image_bytes: bytes) -> np.ndarray:
    model = _load_model()
    tensor = _preprocess_image_bytes(image_bytes)
    batch = tf.expand_dims(tensor, axis=0)
    embedding = model(batch, training=False)
    return embedding.numpy().astype('float32')[0]
