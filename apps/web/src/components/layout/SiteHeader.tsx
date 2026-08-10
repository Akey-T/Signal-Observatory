import { NavLink } from "react-router-dom";

const apiDocsUrl =
  import.meta.env.VITE_API_DOCS_URL ?? "http://localhost:8000/docs";

export function SiteHeader() {
  return (
    <header className="site-header">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <div className="site-header__inner">
        <NavLink
          className="brand"
          to="/"
          aria-label="Signal Observatory overview"
        >
          <span className="brand__mark" aria-hidden="true">
            SO
          </span>
          <span>
            Signal
            <strong>Observatory</strong>
          </span>
        </NavLink>
        <nav aria-label="Primary navigation">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/topics">Topics</NavLink>
          <a href={apiDocsUrl} target="_blank" rel="noreferrer">
            API <span aria-hidden="true">↗</span>
          </a>
        </nav>
      </div>
    </header>
  );
}
