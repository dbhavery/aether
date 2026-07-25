import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-[70vh] flex items-center justify-center flex-col text-center gap-4 px-6">
      <div className="text-[72px] font-medium tracking-tight text-fg-muted leading-none">404</div>
      <p className="text-fg-secondary">That route doesn't exist.</p>
      <Link href="/" className="text-accent hover:underline text-[13px]">
        Back to start
      </Link>
    </div>
  );
}
