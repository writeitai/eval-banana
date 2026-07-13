export type NavItem = {
  title: string;
  href: string;
  children?: NavItem[];
};

// Single source of truth for the docs sidebar order and grouping. It also
// drives prev/next pagination. Add a page here when you add its page.mdx.
export const docsNavigation: NavItem[] = [
  { title: "Introduction", href: "/docs" },
  { title: "Getting Started", href: "/docs/getting-started" },
  { title: "Concepts", href: "/docs/concepts" },
  {
    title: "Check Types",
    href: "/docs/deterministic-checks",
    children: [
      { title: "Deterministic Checks", href: "/docs/deterministic-checks" },
      { title: "Harness Judge Checks", href: "/docs/harness-judge-checks" },
    ],
  },
  { title: "Configuration", href: "/docs/configuration" },
  { title: "Harness Setup", href: "/docs/harness-setup" },
  { title: "Examples", href: "/docs/examples" },
  { title: "Skills", href: "/docs/skills" },
  {
    title: "Reference",
    href: "/docs/check-format",
    children: [
      { title: "Check Format", href: "/docs/check-format" },
      { title: "CLI Reference", href: "/docs/cli-reference" },
      { title: "Reports", href: "/docs/reports" },
    ],
  },
  { title: "Troubleshooting", href: "/docs/troubleshooting" },
];

export function flattenNavigation(items: NavItem[]): NavItem[] {
  const result: NavItem[] = [];
  for (const item of items) {
    result.push(item);
    if (item.children) {
      result.push(...flattenNavigation(item.children));
    }
  }
  return result;
}

export function findAdjacentPages(pathname: string): {
  prev: NavItem | null;
  next: NavItem | null;
} {
  // Only leaf entries are real pages. Section headers (items with children)
  // reuse their first child's href — e.g. "Check Types" -> Deterministic
  // Checks — so excluding them keeps prev/next labeled with the page title
  // instead of the section title, and avoids a self-adjacency on that href.
  const flat = flattenNavigation(docsNavigation).filter((item) => !item.children);

  const normalize = (p: string) => (p.length > 1 ? p.replace(/\/$/, "") : p);
  const target = normalize(pathname);
  const index = flat.findIndex((item) => normalize(item.href) === target);
  if (index === -1) {
    return { prev: null, next: null };
  }
  return {
    prev: index > 0 ? flat[index - 1] : null,
    next: index < flat.length - 1 ? flat[index + 1] : null,
  };
}
