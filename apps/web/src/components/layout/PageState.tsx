type PageErrorProps = {
  title?: string;
  message?: string;
  onRetry: () => void;
};

export function PageLoading({
  label = "Loading Topic Registry",
}: {
  label?: string;
}) {
  return (
    <div
      className="page-state page-state--loading"
      role="status"
      aria-live="polite"
    >
      <span className="loading-orbit" aria-hidden="true" />
      <div>
        <strong>{label}</strong>
        <p>Reading the current curated registry.</p>
      </div>
    </div>
  );
}

export function PageError({
  title = "Topic Registry could not be loaded.",
  message = "The read-only registry API is unavailable. No values have been substituted.",
  onRetry,
}: PageErrorProps) {
  return (
    <div className="page-state page-state--error" role="alert">
      <span className="state-code">REGISTRY / UNAVAILABLE</span>
      <h2>{title}</h2>
      <p>{message}</p>
      <button
        className="button button--secondary"
        type="button"
        onClick={onRetry}
      >
        Retry
      </button>
    </div>
  );
}

export function PageNotFound() {
  return (
    <div className="page-container page-state page-state--not-found">
      <span className="state-code">404 / NOT FOUND</span>
      <h1>This observation path does not exist.</h1>
      <p>Return to the curated Topic Registry to continue exploring.</p>
      <a className="button button--primary" href="/topics">
        Explore topics
      </a>
    </div>
  );
}
