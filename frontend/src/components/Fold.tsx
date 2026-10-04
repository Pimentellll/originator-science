import type { ReactNode } from "react";

/** A section the reader opens on demand: a title, one line on what is inside, then the content. */
export function Fold({
  title,
  hint,
  open = false,
  children,
}: {
  title: string;
  hint: string;
  open?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="fold" open={open}>
      <summary className="fold__sum">
        <b>{title}</b>
        <span>{hint}</span>
      </summary>
      <div className="fold__body">{children}</div>
    </details>
  );
}
