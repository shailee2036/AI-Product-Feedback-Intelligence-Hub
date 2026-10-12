from collections import defaultdict

from feedback_hub.feedback.duplicates import Neighbor, rank_neighbors

# Starter themes from the synthetic Appwrite CSV. The same product area can
# contain more than one theme. The full set of 10-15 labeled themes is later
# manual work.
LABELED_THEMES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("oauth-callback", ("AW-SYN-001", "AW-SYN-002")),
    ("import-progress", ("AW-SYN-007", "AW-SYN-008", "AW-SYN-041")),
    ("upload-resume", ("AW-SYN-011", "AW-SYN-012")),
    (
        "realtime-reconnect",
        tuple(f"AW-SYN-{number:03d}" for number in (*range(19, 26), 42)),
    ),
    ("deployment-backups", ("AW-SYN-038", "AW-SYN-039", "AW-SYN-040")),
)

_GATHERED = 0.5


def theme_groups(
    pairs: list[tuple[str, str, float]],
    *,
    threshold: float,
    neighbors: int,
    minimum_size: int,
) -> list[list[str]]:
    """Connected components of a mutual nearest-neighbor graph.

    A one-way cutoff chains unrelated rows into a single component. Requiring
    each row to be among the other's closest neighbors keeps themes apart.
    Groups smaller than the minimum stay with duplicate detection.
    """
    edges = mutual_edges(rank_neighbors(pairs), threshold=threshold, neighbors=neighbors)
    groups = [sorted(group) for group in _components(edges) if len(group) >= minimum_size]
    groups.sort(key=lambda group: (-len(group), group))
    return groups


def mutual_edges(
    nearest: dict[str, list[Neighbor]], *, threshold: float, neighbors: int
) -> list[tuple[str, str]]:
    top = {item_id: ranked[:neighbors] for item_id, ranked in nearest.items()}
    seen: set[tuple[str, str]] = set()
    edges: list[tuple[str, str]] = []
    for item_id, ranked in top.items():
        for other_id, score in ranked:
            if score < threshold or not _lists(top.get(other_id, []), item_id, threshold):
                continue
            pair = (item_id, other_id) if item_id < other_id else (other_id, item_id)
            if pair in seen:
                continue
            seen.add(pair)
            edges.append(pair)
    return edges


def score_themes(
    groups: list[list[str]],
    identities: list[tuple[str, str]],
    labels: list[tuple[str, tuple[str, ...]]],
) -> tuple[int, int, float] | None:
    """Return labeled count, how many themes share a cluster, and mean cohesion.

    Cohesion is the largest share of a labeled theme that landed in one cluster.
    A theme counts as gathered when that share is at least half.
    """
    by_external = {external_id: item_id for item_id, external_id in identities}
    location: dict[str, int] = {}
    for index, group in enumerate(groups):
        for item_id in group:
            location[item_id] = index
    cohesions: list[float] = []
    for _name, external_ids in labels:
        present = [
            by_external[external_id] for external_id in external_ids if external_id in by_external
        ]
        if len(present) < 2:
            continue
        counts: dict[int, int] = defaultdict(int)
        for item_id in present:
            cluster = location.get(item_id)
            if cluster is not None:
                counts[cluster] += 1
        best = max(counts.values()) if counts else 0
        cohesions.append(best / len(present))
    if not cohesions:
        return None
    gathered = sum(cohesion >= _GATHERED for cohesion in cohesions)
    return len(cohesions), gathered, sum(cohesions) / len(cohesions)


def _lists(ranked: list[Neighbor], item_id: str, threshold: float) -> bool:
    return any(other_id == item_id and score >= threshold for other_id, score in ranked)


def _components(edges: list[tuple[str, str]]) -> list[set[str]]:
    parent: dict[str, str] = {}

    def find(item_id: str) -> str:
        parent.setdefault(item_id, item_id)
        while parent[item_id] != item_id:
            parent[item_id] = parent[parent[item_id]]
            item_id = parent[item_id]
        return item_id

    for left, right in edges:
        lead, follow = find(left), find(right)
        if lead != follow:
            parent[follow] = lead
    grouped: dict[str, set[str]] = defaultdict(set)
    for item_id in parent:
        grouped[find(item_id)].add(item_id)
    return list(grouped.values())
