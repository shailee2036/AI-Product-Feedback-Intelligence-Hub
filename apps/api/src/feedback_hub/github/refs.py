import re
from dataclasses import dataclass
from urllib.parse import urlparse

_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class InvalidRepositoryReferenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RepositoryRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


def parse_repository_reference(value: str) -> RepositoryRef:
    """Accept `owner/repo` or a github.com URL; reject anything that is not a plain repo path."""
    raw = value.strip()
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        if parsed.hostname not in {"github.com", "www.github.com"}:
            raise InvalidRepositoryReferenceError("Only github.com repositories are supported.")
        if parsed.query or parsed.fragment:
            raise InvalidRepositoryReferenceError("Repository URL must not include query strings.")
        raw = parsed.path

    parts = [part for part in raw.strip("/").split("/") if part]
    if len(parts) != 2:
        raise InvalidRepositoryReferenceError("Expected a repository in the form owner/repo.")

    owner, name = parts
    name = name.removesuffix(".git")
    if not _OWNER.fullmatch(owner) or owner.endswith("-") or "--" in owner:
        raise InvalidRepositoryReferenceError("Invalid GitHub owner name.")
    if not _REPO.fullmatch(name) or name in {".", ".."}:
        raise InvalidRepositoryReferenceError("Invalid GitHub repository name.")
    return RepositoryRef(owner=owner, name=name)
