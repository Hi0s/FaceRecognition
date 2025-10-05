import random
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import tensorflow as tf
from keras.applications import InceptionResNetV2
from keras import mixed_precision

SEED = 5
IMAGE_SIZE = (256, 256)
IMAGE_CHANNELS = 3
INPUT_SHAPE = IMAGE_SIZE + (IMAGE_CHANNELS,)
DATA_ROOT = Path("./CelebDataProcessed")
BATCH_SIZE = 32
TRAIN_RATIO = 0.9
MARGIN = 0.5
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}

mixed_precision.set_global_policy("mixed_float16")

DatasetDict = Dict[str, np.ndarray]
import os
os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'

def configure_environment(seed: int = SEED) -> None:
    """Configure GPU memory growth and seed all RNGs for reproducibility."""
    gpus = tf.config.experimental.list_physical_devices("GPU")
    for gpu in gpus:
        try:
            tf.config.experimental.set_memory_growth(gpu, True)
        except RuntimeError as exc:
            print(f"Could not set memory growth for {gpu}: {exc}")
    print("Num GPUs Available:", len(tf.config.list_physical_devices("GPU")))
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def load_image_to_array(image_path: Path) -> np.ndarray:
    image_bytes = tf.io.read_file(str(image_path))
    image = tf.image.decode_image(
        image_bytes,
        channels=IMAGE_CHANNELS,
        expand_animations=False,
    )
    image = tf.image.resize(image, IMAGE_SIZE)
    image = tf.image.convert_image_dtype(image, tf.float32)
    return image.numpy()


def load_dataset_to_memory(root_dir: Path) -> DatasetDict:
    dataset: DatasetDict = {}
    for person_dir in sorted(root_dir.iterdir()):
        if not person_dir.is_dir():
            continue
        images = []
        for image_path in sorted(person_dir.iterdir()):
            if image_path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
                continue
            images.append(load_image_to_array(image_path))
        if len(images) >= 2:
            dataset[person_dir.name] = np.asarray(images, dtype=np.float32)
    if len(dataset) < 2:
        raise ValueError("Expected at least two identities with two images each.")
    total_images = sum(arr.shape[0] for arr in dataset.values())
    print(f"Loaded {total_images} images from {len(dataset)} identities into RAM.")
    return dataset


def split_dataset(
    dataset: DatasetDict, train_ratio: float, seed: int
) -> Tuple[DatasetDict, DatasetDict]:
    person_ids = list(dataset.keys())
    rng = random.Random(seed)
    rng.shuffle(person_ids)
    split_index = int(len(person_ids) * train_ratio)
    split_index = min(max(split_index, 1), len(person_ids) - 1)
    train_ids = person_ids[:split_index]
    val_ids = person_ids[split_index:]
    train_data = {pid: dataset[pid] for pid in train_ids}
    val_data = {pid: dataset[pid] for pid in val_ids}
    return train_data, val_data


class TripletBatchGenerator:
    """Samples triplets from the in-memory dataset for tf.data."""

    def __init__(self, dataset: DatasetDict, batch_size: int, seed: int):
        if len(dataset) < 2:
            raise ValueError("Triplet generation requires at least two identities.")
        self.dataset = dataset
        self.batch_size = batch_size
        self.rng = np.random.default_rng(seed)
        self.person_ids = list(dataset.keys())
        self.negative_candidates = {
            pid: [other for other in self.person_ids if other != pid]
            for pid in self.person_ids
        }

    def generate(self):
        while True:
            anchors = []
            positives = []
            negatives = []
            for _ in range(self.batch_size):
                anchor_id = self.rng.choice(self.person_ids)
                anchor_images = self.dataset[anchor_id]
                a_idx, p_idx = self.rng.choice(
                    anchor_images.shape[0], size=2, replace=False
                )
                negative_id = self.rng.choice(self.negative_candidates[anchor_id])
                negative_images = self.dataset[negative_id]
                n_idx = self.rng.integers(0, negative_images.shape[0])

                anchors.append(anchor_images[a_idx])
                positives.append(anchor_images[p_idx])
                negatives.append(negative_images[n_idx])

            anchor_batch = np.stack(anchors, axis=0).astype(np.float32)
            positive_batch = np.stack(positives, axis=0).astype(np.float32)
            negative_batch = np.stack(negatives, axis=0).astype(np.float32)
            labels = np.zeros((self.batch_size, 1), dtype=np.float32)
            yield (anchor_batch, positive_batch, negative_batch), labels


def build_tf_dataset(generator: TripletBatchGenerator) -> tf.data.Dataset:
    output_signature = (
        (
            tf.TensorSpec(shape=(generator.batch_size, *INPUT_SHAPE), dtype=tf.float32),
            tf.TensorSpec(shape=(generator.batch_size, *INPUT_SHAPE), dtype=tf.float32),
            tf.TensorSpec(shape=(generator.batch_size, *INPUT_SHAPE), dtype=tf.float32),
        ),
        tf.TensorSpec(shape=(generator.batch_size, 1), dtype=tf.float32),
    )
    return tf.data.Dataset.from_generator(
        generator.generate, output_signature=output_signature
    ).prefetch(tf.data.AUTOTUNE)


class DistanceLayer(tf.keras.layers.Layer):
    def call(self, anchor, positive, negative):
        ap_distance = tf.reduce_sum(tf.square(anchor - positive), axis=-1)
        an_distance = tf.reduce_sum(tf.square(anchor - negative), axis=-1)
        return ap_distance, an_distance


def get_embedding_model(input_shape: Tuple[int, int, int]) -> tf.keras.Model:
    base_model = InceptionResNetV2(
        include_top=False,
        weights="imagenet",
        pooling="avg",
        input_shape=input_shape,
    )
    for layer in base_model.layers[:-30]:
        layer.trainable = False
    for layer in base_model.layers[-30:]:
        layer.trainable = True

    inputs = tf.keras.Input(shape=input_shape, name="embedding_input")
    x = base_model(inputs)
    x = tf.keras.layers.Flatten()(x)
    x = tf.keras.layers.Dense(512, activation="relu")(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.Dropout(0.3)(x)
    x = tf.keras.layers.Dense(256, activation="relu")(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.Dropout(0.2)(x)
    outputs = tf.keras.layers.Lambda(
        lambda embeddings: tf.math.l2_normalize(embeddings, axis=1),
        name="l2_normalization",
    )(x)
    return tf.keras.Model(inputs=inputs, outputs=outputs, name="Embedding")


def build_siamese_network(input_shape: Tuple[int, int, int]) -> tf.keras.Model:
    embedding_model = get_embedding_model(input_shape)

    anchor_input = tf.keras.layers.Input(name="anchor", shape=input_shape)
    positive_input = tf.keras.layers.Input(name="positive", shape=input_shape)
    negative_input = tf.keras.layers.Input(name="negative", shape=input_shape)

    anchor_embedding = embedding_model(anchor_input)
    positive_embedding = embedding_model(positive_input)
    negative_embedding = embedding_model(negative_input)

    distances = DistanceLayer(name="triplet_distances")(
        anchor_embedding, positive_embedding, negative_embedding
    )
    return tf.keras.Model(
        inputs=[anchor_input, positive_input, negative_input],
        outputs=distances,
        name="SiameseNetwork",
    )


class SiameseModelWrapper(tf.keras.Model):
    def __init__(self, siamese_network: tf.keras.Model, margin: float):
        super().__init__()
        self.siamese_network = siamese_network
        self.margin = margin
        self.loss_tracker = tf.keras.metrics.Mean(name="loss")

    def call(self, inputs, training=False):
        return self.siamese_network(inputs, training=training)

    @staticmethod
    def compute_triplet_loss(ap_distance, an_distance, margin):
        return tf.maximum(ap_distance - an_distance + margin, 0.0)

    def train_step(self, data):
        triplets, _ = data
        with tf.GradientTape() as tape:
            ap_distance, an_distance = self.siamese_network(triplets, training=True)
            loss = tf.reduce_mean(
                self.compute_triplet_loss(ap_distance, an_distance, self.margin)
            )
        gradients = tape.gradient(loss, self.siamese_network.trainable_weights)
        self.optimizer.apply_gradients(
            zip(gradients, self.siamese_network.trainable_weights)
        )
        self.loss_tracker.update_state(loss)
        return {"loss": self.loss_tracker.result()}

    def test_step(self, data):
        triplets, _ = data
        ap_distance, an_distance = self.siamese_network(triplets, training=False)
        loss = tf.reduce_mean(
            self.compute_triplet_loss(ap_distance, an_distance, self.margin)
        )
        self.loss_tracker.update_state(loss)
        return {"loss": self.loss_tracker.result()}

    @property
    def metrics(self):
        return [self.loss_tracker]


def extract_encoder(trained_model: SiameseModelWrapper) -> tf.keras.Model:
    embedding = trained_model.siamese_network.get_layer("Embedding")
    encoder = tf.keras.models.clone_model(embedding)
    encoder(tf.zeros((1, *INPUT_SHAPE)))
    encoder.set_weights(embedding.get_weights())
    return encoder


def main() -> None:
    configure_environment(SEED)

    dataset = load_dataset_to_memory(DATA_ROOT)
    train_data, val_data = split_dataset(dataset, train_ratio=TRAIN_RATIO, seed=SEED)
    print(
        f"Train identities: {len(train_data)}, validation identities: {len(val_data)}"
    )

    train_generator = TripletBatchGenerator(train_data, batch_size=BATCH_SIZE, seed=SEED)
    val_generator = TripletBatchGenerator(val_data, batch_size=BATCH_SIZE, seed=SEED + 1)

    train_ds = build_tf_dataset(train_generator)
    val_ds = build_tf_dataset(val_generator)

    siamese_network = build_siamese_network(INPUT_SHAPE)
    siamese_network.summary()

    model = SiameseModelWrapper(siamese_network, margin=MARGIN)
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4))

    checkpoint_path = Path("checkpoints/siameseModel_celeb_v2.keras")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=5,
            verbose=1,
            restore_best_weights=True,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            patience=4,
            verbose=1,
            factor=0.3,
            min_lr=1e-8,
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=str(checkpoint_path),
            monitor="val_loss",
            mode="min",
            save_best_only=True,
            verbose=1,
        ),
    ]

    history = model.fit(
        train_ds,
        steps_per_epoch=100,
        validation_data=val_ds,
        validation_steps=100,
        epochs=128,
        callbacks=callbacks,
    )

    encoder = extract_encoder(model)
    encoder.save("encoder_celeb_Inception.keras")
    encoder.summary()


if __name__ == "__main__":
    main()
