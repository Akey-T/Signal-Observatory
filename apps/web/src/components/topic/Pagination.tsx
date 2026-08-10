type PaginationProps = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
};

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return (
    <nav className="pagination" aria-label="Topic result pages">
      <button
        className="button button--secondary"
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        <span aria-hidden="true">←</span> Previous
      </button>
      <p aria-live="polite">
        <strong>
          {start}–{end}
        </strong>{" "}
        of {total} · Page {page} of {totalPages}
      </p>
      <button
        className="button button--secondary"
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        Next <span aria-hidden="true">→</span>
      </button>
    </nav>
  );
}
