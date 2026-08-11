import type { CoverageStatus } from "../../types/api";
import { titleCase } from "../../lib/format";

const explanations: Record<CoverageStatus, string> = {
  complete: "Collection completed for the system's declared target window.",
  partial: "Some expected historical collection remains incomplete.",
  forward_only:
    "History begins when Signal Observatory first observed this source.",
  empty: "Collection completed, with zero relevant observations.",
  unknown: "Coverage cannot yet be reliably inferred from persisted facts.",
};

export function CoverageBadge({ status }: { status: CoverageStatus }) {
  return (
    <span
      className={`coverage-badge coverage-badge--${status}`}
      title={explanations[status]}
    >
      {titleCase(status)}
    </span>
  );
}
