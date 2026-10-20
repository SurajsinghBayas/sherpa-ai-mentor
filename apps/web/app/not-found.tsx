import Link from "next/link";
import { Sherpa } from "../components/sherpa";
import { buttonVariants } from "../components/ui/button-variants";

export default function NotFound() {
  return (
    <main className="container flex min-h-[calc(100dvh-3.5rem)] flex-col items-center justify-center py-16 text-center">
      <Sherpa pose="exploring" size={128} />
      <p className="eyebrow mt-6">404</p>
      <h1 className="mt-2 text-3xl font-semibold">This path isn&apos;t on the map</h1>
      <p className="mt-2 max-w-sm text-muted-foreground">The page you&apos;re looking for doesn&apos;t exist or has moved.</p>
      <Link href="/" className={buttonVariants({ variant: "ink", size: "lg", className: "mt-8" })}>
        Back to the start
      </Link>
    </main>
  );
}
