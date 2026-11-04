import Link from "next/link";

export function AdminReviewLink() {
  return (
    <section className="sidebar-review" aria-label="Administrator review">
      <div className="side-label">ADMINISTRATION</div>
      <Link className="side-item" href="/admin/reviews"><span aria-hidden="true">✓</span> Review &amp; approve</Link>
      <div className="sidebar-review-copy"><strong>A conversation.<br />A reviewed change.</strong><p>Your agent prepares the request. You authorize the change with your own Vault permissions.</p></div>
    </section>
  );
}
