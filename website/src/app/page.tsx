import Link from "next/link";
import Image from "next/image";
import { ArrowRight, Github } from "lucide-react";

export default function Home() {
  return (
    <div className="container mx-auto flex flex-col items-center px-4 py-24 text-center sm:py-32">
      <Image
        src="/logo.png"
        alt="eval-banana logo"
        width={120}
        height={134}
        priority
        className="mb-8 h-28 w-auto"
      />

      <span className="mb-6 inline-flex items-center rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-muted-foreground">
        Open source · Apache-2.0
      </span>

      <h1 className="max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">
        Score anything with simple YAML checks.
      </h1>

      <p className="mt-6 max-w-2xl text-lg text-muted-foreground">
        <span className="font-semibold text-foreground">eval-banana</span> is a
        lightweight, aspect-based evaluation framework. It auto-discovers YAML
        check definitions from <code>eval_checks/</code> directories, runs them,
        and produces a scored report. Every check is pass/fail — objective
        assertions run as scripts, qualitative ones are graded by an AI judge.
      </p>

      <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row">
        <Link
          href="/docs"
          className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          Read the docs
          <ArrowRight className="h-4 w-4" />
        </Link>
        <a
          href="https://github.com/writeitai/eval-banana"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-md border border-border px-5 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent/50"
        >
          <Github className="h-4 w-4" />
          View on GitHub
        </a>
      </div>

      <div className="mt-12 w-full max-w-md">
        <div className="overflow-x-auto rounded-lg border border-border bg-card px-5 py-4 text-left font-mono text-sm">
          <span className="text-muted-foreground select-none">$ </span>
          uv add eval-banana
        </div>
      </div>
    </div>
  );
}
