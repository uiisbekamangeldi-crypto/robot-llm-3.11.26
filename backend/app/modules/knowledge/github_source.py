from dataclasses import dataclass
from urllib.parse import quote, urlparse

import httpx

from app.modules.knowledge.parsing import SUPPORTED_EXTENSIONS, validate_path


@dataclass(frozen=True)
class GitHubFile:
    path: str
    size: int


def is_knowledge_path(path: str) -> bool:
    parts = path.split("/")
    return (len(parts) == 1 and path.lower().endswith(".pdf")) or (
        len(parts) > 1 and parts[0] == "knowledge"
    )


class GitHubSource:
    def __init__(self, repository_url: str, branch: str, token: str | None = None) -> None:
        parsed = urlparse(repository_url.rstrip("/"))
        if parsed.scheme != "https" or parsed.netloc != "github.com":
            raise ValueError("Only HTTPS github.com repositories are supported")
        parts = parsed.path.strip("/").removesuffix(".git").split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("Repository URL must contain owner and name")
        self.owner, self.name = parts
        self.branch = branch
        self.repository_url = f"https://github.com/{self.owner}/{self.name}"
        self.headers = {"Accept": "application/vnd.github+json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    async def snapshot(self, client: httpx.AsyncClient) -> tuple[str, list[GitHubFile]]:
        base = f"https://api.github.com/repos/{self.owner}/{self.name}"
        response = await client.get(
            f"{base}/commits/{quote(self.branch, safe='')}", headers=self.headers
        )
        response.raise_for_status()
        sha = response.json()["sha"]
        if not isinstance(sha, str) or len(sha) != 40:
            raise ValueError("GitHub returned an invalid commit SHA")
        tree = await client.get(
            f"{base}/git/trees/{sha}", params={"recursive": "1"}, headers=self.headers
        )
        tree.raise_for_status()
        payload = tree.json()
        if payload.get("truncated"):
            raise ValueError("GitHub tree is truncated")
        files = [
            GitHubFile(validate_path(item["path"]), item["size"])
            for item in payload["tree"]
            if item.get("type") == "blob"
            and item["path"].lower().endswith(tuple(SUPPORTED_EXTENSIONS))
            and is_knowledge_path(item["path"])
        ]
        return sha, files

    async def download(self, client: httpx.AsyncClient, commit: str, file: GitHubFile) -> bytes:
        if file.size > 20 * 1024 * 1024:
            raise ValueError("Document exceeds 20 MiB limit")
        path = quote(validate_path(file.path), safe="/")
        url = f"https://raw.githubusercontent.com/{self.owner}/{self.name}/{commit}/{path}"
        response = await client.get(url, headers=self.headers)
        response.raise_for_status()
        if len(response.content) > 20 * 1024 * 1024:
            raise ValueError("Downloaded document exceeds 20 MiB limit")
        return response.content
