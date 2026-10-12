from collections import defaultdict
from dataclasses import dataclass

from feedback_hub.feedback.normalize import prepare_text, source_text

Neighbor = tuple[str, float]
LabeledPair = tuple[str, str, bool]

# Starter labels for the synthetic Appwrite CSV. The same request in different
# words is a duplicate. A related but different request is not. The full
# 200-pair set is later manual labeling, not this list.
LABELED_PAIRS: tuple[LabeledPair, ...] = (
    ("AW-SYN-001", "AW-SYN-002", True),
    ("AW-SYN-007", "AW-SYN-008", True),
    ("AW-SYN-008", "AW-SYN-041", True),
    ("AW-SYN-011", "AW-SYN-012", True),
    ("AW-SYN-021", "AW-SYN-042", True),
    ("AW-SYN-001", "AW-SYN-006", False),
    ("AW-SYN-002", "AW-SYN-003", False),
    ("AW-SYN-004", "AW-SYN-011", False),
    ("AW-SYN-013", "AW-SYN-007", False),
    ("AW-SYN-018", "AW-SYN-015", False),
)


@dataclass(frozen=True, slots=True)
class HashableFeedback:
    id: str
    source: str
    title: str
    body: str
    language: str | None
    content_hash: str | None


@dataclass(frozen=True, slots=True)
class DuplicateLink:
    left_id: str
    right_id: str
    kind: str
    score: float


@dataclass(frozen=True, slots=True)
class DuplicateComponent:
    kind: str
    member_ids: list[str]


@dataclass(frozen=True, slots=True)
class LabelScore:
    labeled: int
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float | None:
        predicted = self.true_positives + self.false_positives
        if predicted == 0:
            return None
        return self.true_positives / predicted

    @property
    def recall(self) -> float | None:
        relevant = self.true_positives + self.false_negatives
        if relevant == 0:
            return None
        return self.true_positives / relevant


def content_digest(stored: str | None, raw: str, language: str | None) -> str | None:
    """Use the stored redacted hash, or hash the text now. Skip text that is too short."""
    if stored:
        return stored
    prepared = prepare_text(raw, declared_language=language)
    if prepared.skip_reason is not None:
        return None
    return prepared.content_hash


def links_for_feedback(
    items: list[HashableFeedback],
    pairs: list[tuple[str, str, float]],
    *,
    threshold: float,
    neighbors: int,
) -> list[DuplicateLink]:
    hashed: list[tuple[str, str]] = []
    for item in items:
        digest = content_digest(
            item.content_hash,
            source_text(source=item.source, title=item.title, body=item.body),
            item.language,
        )
        if digest is not None:
            hashed.append((item.id, digest))
    return build_links(hashed, pairs, threshold=threshold, neighbors=neighbors)


def build_links(
    hashed: list[tuple[str, str]],
    pairs: list[tuple[str, str, float]],
    *,
    threshold: float,
    neighbors: int,
) -> list[DuplicateLink]:
    exact = exact_links(hashed)
    blocked = {(link.left_id, link.right_id) for link in exact}
    semantic = semantic_links(
        rank_neighbors(pairs),
        threshold=threshold,
        neighbors=neighbors,
        blocked=blocked,
    )
    return exact + semantic


def exact_links(hashed: list[tuple[str, str]]) -> list[DuplicateLink]:
    """One link for every pair that shares a redacted content hash."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for item_id, digest in hashed:
        grouped[digest].append(item_id)
    links: list[DuplicateLink] = []
    for members in grouped.values():
        ordered = sorted(members)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                links.append(DuplicateLink(left, right, "exact", 1.0))
    return links


def rank_neighbors(pairs: list[tuple[str, str, float]]) -> dict[str, list[Neighbor]]:
    grouped: dict[str, list[Neighbor]] = defaultdict(list)
    for left, right, score in pairs:
        safe = clamp_score(score)
        grouped[left].append((right, safe))
        grouped[right].append((left, safe))
    for ranked in grouped.values():
        ranked.sort(key=lambda item: item[1], reverse=True)
    return grouped


def semantic_links(
    nearest: dict[str, list[Neighbor]],
    *,
    threshold: float,
    neighbors: int,
    blocked: set[tuple[str, str]],
) -> list[DuplicateLink]:
    """Keep a pair only when each item is among the other's closest neighbors.

    An all-pairs cutoff pulls a whole product area into one component. Mutual
    nearest neighbors stay on paraphrases.
    """
    top = {item_id: ranked[:neighbors] for item_id, ranked in nearest.items()}
    seen: set[tuple[str, str]] = set()
    links: list[DuplicateLink] = []
    for item_id, ranked in top.items():
        for other_id, score in ranked:
            if score < threshold:
                continue
            if not _is_close_neighbor(top.get(other_id, []), item_id, threshold):
                continue
            pair = _ordered(item_id, other_id)
            if pair in seen or pair in blocked:
                continue
            seen.add(pair)
            links.append(DuplicateLink(pair[0], pair[1], "semantic", score))
    return links


def assemble_groups(links: list[DuplicateLink]) -> list[DuplicateComponent]:
    """Group links that share an item. The original rows stay separate."""
    components: list[DuplicateComponent] = []
    for group in connected_groups(links):
        kinds = {link.kind for link in group}
        kind = next(iter(kinds)) if len(kinds) == 1 else "mixed"
        member_ids = sorted({link.left_id for link in group} | {link.right_id for link in group})
        components.append(DuplicateComponent(kind, member_ids))
    components.sort(key=lambda component: (-len(component.member_ids), component.member_ids))
    return components


def connected_groups(links: list[DuplicateLink]) -> list[list[DuplicateLink]]:
    parent: dict[str, str] = {}

    def find(item_id: str) -> str:
        parent.setdefault(item_id, item_id)
        while parent[item_id] != item_id:
            parent[item_id] = parent[parent[item_id]]
            item_id = parent[item_id]
        return item_id

    for link in links:
        left, right = find(link.left_id), find(link.right_id)
        if left != right:
            parent[right] = left
    grouped: dict[str, list[DuplicateLink]] = defaultdict(list)
    for link in links:
        grouped[find(link.left_id)].append(link)
    return list(grouped.values())


def score_labels(
    links: list[DuplicateLink], labels: list[LabeledPair], present: set[str]
) -> LabelScore:
    """Score only labeled pairs whose ids both exist for this product."""
    predicted = {_ordered(link.left_id, link.right_id) for link in links}
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    labeled = 0
    for left, right, is_duplicate in labels:
        if left not in present or right not in present:
            continue
        labeled += 1
        found = _ordered(left, right) in predicted
        if is_duplicate and found:
            true_positives += 1
        elif is_duplicate:
            false_negatives += 1
        elif found:
            false_positives += 1
    return LabelScore(labeled, true_positives, false_positives, false_negatives)


def evaluate_links(
    links: list[DuplicateLink],
    identities: list[tuple[str, str]],
    labels: list[LabeledPair],
) -> LabelScore | None:
    """Map stored item ids to external ids, then score the starter labels."""
    external = dict(identities)
    labeled_links: list[DuplicateLink] = []
    for link in links:
        left = external.get(link.left_id)
        right = external.get(link.right_id)
        if left is None or right is None:
            continue
        ordered = _ordered(left, right)
        labeled_links.append(DuplicateLink(ordered[0], ordered[1], link.kind, link.score))
    score = score_labels(labeled_links, labels, set(external.values()))
    if score.labeled == 0:
        return None
    return score


def clamp_score(score: float) -> float:
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score


def _is_close_neighbor(ranked: list[Neighbor], item_id: str, threshold: float) -> bool:
    return any(other_id == item_id and score >= threshold for other_id, score in ranked)


def _ordered(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)
