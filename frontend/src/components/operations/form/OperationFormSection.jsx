export default function OperationFormSection({ title, grid = true, children }) {
  return (
    <section className="card">
      {title && <h2 className="card__title">{title}</h2>}
      <div className={grid ? 'form-grid' : undefined}>{children}</div>
    </section>
  );
}
