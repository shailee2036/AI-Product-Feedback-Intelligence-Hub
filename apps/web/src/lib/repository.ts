const OWNER = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/;
const REPO = /^[A-Za-z0-9._-]{1,100}$/;

export type RepositoryInputResult = { ok: true; value: string } | { ok: false; error: string };

/** Mirrors the API's parser so obvious mistakes are caught before a round trip. */
export function parseRepositoryInput(input: unknown): RepositoryInputResult {
  if (typeof input !== "string" || input.trim() === "") {
    return { ok: false, error: "Enter a repository like appwrite/appwrite or its GitHub URL." };
  }

  let path = input.trim();
  if (/^https?:\/\//i.test(path)) {
    let url: URL;
    try {
      url = new URL(path);
    } catch {
      return { ok: false, error: "That URL is not valid." };
    }
    if (!["github.com", "www.github.com"].includes(url.hostname)) {
      return { ok: false, error: "Only github.com repositories are supported." };
    }
    if (url.search || url.hash) {
      return { ok: false, error: "Remove query strings from the repository URL." };
    }
    path = url.pathname;
  }

  const parts = path.split("/").filter(Boolean);
  if (parts.length !== 2) {
    return { ok: false, error: "Use the form owner/repo, for example appwrite/appwrite." };
  }
  const [owner, rawName] = parts;
  const name = rawName.replace(/\.git$/, "");
  if (!OWNER.test(owner) || owner.endsWith("-") || owner.includes("--")) {
    return { ok: false, error: "That GitHub owner name is not valid." };
  }
  if (!REPO.test(name) || name === "." || name === "..") {
    return { ok: false, error: "That GitHub repository name is not valid." };
  }
  return { ok: true, value: `${owner}/${name}` };
}
