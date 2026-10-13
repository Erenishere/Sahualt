import Link from "next/link";

type SahulatMarkProps = {
  className?: string;
  title?: string;
};

export function SahulatMark({ className, title }: SahulatMarkProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 48 48"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <path className="sahulat-mark-surface" d="M15 3h18c7.2 0 12 4.8 12 12v18c0 7.2-4.8 12-12 12H15C7.8 45 3 40.2 3 33V15C3 7.8 7.8 3 15 3Z" />
      <path className="sahulat-mark-ribbon" d="M31.6 13.2c-2.2-1.8-5.1-2.7-8-2.3-4.6.5-7.5 3.1-7.2 6.3.3 3.3 3.5 4.7 8.3 5.5 4.5.7 7 2 7.3 5 .3 3.7-3 6.5-8 6.9-3.4.3-6.5-.7-8.9-2.8" />
      <circle className="sahulat-mark-lens" cx="29.5" cy="29.5" r="5.2" />
      <path className="sahulat-mark-handle" d="m33.4 33.4 4.2 4.2" />
      <circle className="sahulat-mark-spark" cx="13.2" cy="12.8" r="1.5" />
    </svg>
  );
}

type SahulatBrandProps = {
  className?: string;
  descriptor?: string;
  href?: string;
  onClick?: () => void;
  inverse?: boolean;
};

export function SahulatBrand({
  className,
  descriptor = "AI COMMERCE",
  href,
  onClick,
  inverse = false,
}: SahulatBrandProps) {
  const classes = ["sahulat-brand", inverse ? "sahulat-brand-inverse" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");
  const content = (
    <>
      <SahulatMark className="sahulat-brand-mark" />
      <span className="sahulat-brand-copy">
        <b>Sahulat</b>
        <small>{descriptor}</small>
      </span>
    </>
  );

  if (href) {
    return <Link className={classes} href={href} aria-label="Sahulat home">{content}</Link>;
  }

  return <button className={classes} type="button" onClick={onClick} aria-label="Sahulat home">{content}</button>;
}
