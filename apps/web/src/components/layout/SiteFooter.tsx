import { Link } from "react-router-dom";

import { useRegistry } from "../../context/RegistryContext";

export function SiteFooter() {
  const { status, error } = useRegistry();
  const registryLabel = error
    ? "Registry status unavailable"
    : status
      ? `Topic Registry v${status.version} online`
      : "Checking Topic Registry";

  return (
    <footer className="site-footer">
      <div>
        <Link className="site-footer__brand" to="/">
          Signal Observatory
        </Link>
        <p>E00 · E01 · E02 complete</p>
      </div>
      <div className="site-footer__status">
        <span>{registryLabel}</span>
        <span>External observations not yet enabled</span>
      </div>
    </footer>
  );
}
