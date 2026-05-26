import logging
from typing import Any

import numpy as np

from app.infrastructure.ml.text_embedder import get_text_embedder

logger = logging.getLogger(__name__)

# Cosine similarity threshold above which two entity surface forms
# are considered the same canonical entity and merged.
MERGE_THRESHOLD = float(0.92)


class Disambiguator:
    """
    Resolves surface form variants to canonical entity labels.

    Uses the existing TextEmbedder (pplx-embed-v1) to compute similarity
    between entity surface forms. Forms above MERGE_THRESHOLD are clustered
    into a single canonical label (the most frequent surface form in the cluster).
    """

    def merge(self, triples: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not triples:
            return []

        surfaces = list({t["subject"] for t in triples})
        if len(surfaces) == 1:
            return triples

        embedder = get_text_embedder()
        vectors = np.array(embedder.embed_texts(surfaces))  # (N, D)

        # Build canonical map via greedy single-linkage clustering
        canonical_map = self._cluster(surfaces, vectors)

        merged = []
        for t in triples:
            canon = canonical_map.get(t["subject"], t["subject"])
            merged.append({**t, "subject": canon})

        logger.info(
            "[DISAMBIGUATOR] Resolved %d surface forms → %d canonical entities",
            len(surfaces),
            len(set(canonical_map.values())),
        )
        return merged

    @staticmethod
    def _cluster(surfaces: list[str], vectors: np.ndarray) -> dict[str, str]:
        """Greedy single-linkage: each surface maps to the canonical label of its cluster."""
        norms = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9)
        sim_matrix = norms @ norms.T  # (N, N)

        parent: dict[int, int] = {i: i for i in range(len(surfaces))}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(len(surfaces)):
            for j in range(i + 1, len(surfaces)):
                if sim_matrix[i, j] >= MERGE_THRESHOLD:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[rj] = ri

        # Map each index to the most representative surface in its cluster (shortest = cleanest)
        clusters: dict[int, list[int]] = {}
        for i in range(len(surfaces)):
            root = find(i)
            clusters.setdefault(root, []).append(i)

        canonical_map: dict[str, str] = {}
        for members in clusters.values():
            canonical = min(members, key=lambda i: len(surfaces[i]))
            canonical_label = surfaces[canonical]
            for m in members:
                canonical_map[surfaces[m]] = canonical_label

        return canonical_map
