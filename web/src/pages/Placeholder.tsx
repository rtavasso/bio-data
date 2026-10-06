export default function Placeholder({ title, module }: { title: string; module: string }) {
  return (
    <section>
      <h1>{title}</h1>
      <p className="muted">{module} is not built yet.</p>
    </section>
  );
}
