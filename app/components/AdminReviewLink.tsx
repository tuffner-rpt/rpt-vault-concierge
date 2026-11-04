import Link from "next/link";

export function AdminReviewLink() {
  return (
    <section className="sidebar-review" aria-label="Administrator review">
      <div className="side-label">ADMINISTRATION</div>
      <Link className="side-item" href="/admin/reviews"><span aria-hidden="true">✓</span> Review &amp; approve</Link>
    </section>
  );
}
