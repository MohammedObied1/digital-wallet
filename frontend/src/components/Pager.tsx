export function Pager({
  page,
  pages,
  onChange,
}: {
  page: number
  pages: number
  onChange: (page: number) => void
}) {
  if (pages <= 1) return null
  return (
    <div className="pager">
      <button disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Prev
      </button>
      <span>
        Page {page} of {pages}
      </span>
      <button disabled={page >= pages} onClick={() => onChange(page + 1)}>
        Next
      </button>
    </div>
  )
}
