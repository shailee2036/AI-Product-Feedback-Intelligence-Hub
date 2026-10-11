const REASON_LABELS: Record<string, string> = {
  not_public: "The repository is not public.",
  not_organization_owned: "The repository is owned by a personal account, not an organization.",
  license_missing: "GitHub does not detect a recognized open-source license.",
  license_not_allowed: "The license is not on the supported open-source list.",
  issues_disabled: "GitHub Issues are disabled for this repository.",
  archived: "The repository is archived.",
  disabled: "The repository is disabled on GitHub.",
};

export function describeReason(code: string): string {
  return REASON_LABELS[code] ?? `Not eligible (${code}).`;
}
