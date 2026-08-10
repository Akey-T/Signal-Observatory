import type { Category, Topic } from "../types/api";

export function compareTopics(left: Topic, right: Topic): number {
  if (left.monitoring_priority !== right.monitoring_priority) {
    return right.monitoring_priority - left.monitoring_priority;
  }
  if (left.canonical_name < right.canonical_name) return -1;
  if (left.canonical_name > right.canonical_name) return 1;
  return left.slug.localeCompare(right.slug);
}

export function categoryName(
  slug: string | null,
  categories: Category[],
): string {
  if (slug === null) return "Uncategorized";
  return categories.find((category) => category.slug === slug)?.name ?? slug;
}

export function categoryPath(
  slug: string | null,
  categories: Category[],
): Category[] {
  if (slug === null) return [];
  const bySlug = new Map(
    categories.map((category) => [category.slug, category]),
  );
  const result: Category[] = [];
  const visited = new Set<string>();
  let current = bySlug.get(slug);
  while (current && !visited.has(current.slug)) {
    result.unshift(current);
    visited.add(current.slug);
    current = current.parent ? bySlug.get(current.parent) : undefined;
  }
  return result;
}

export function rootCategorySlug(
  slug: string | null,
  categories: Category[],
): string {
  const path = categoryPath(slug, categories);
  return path[0]?.slug ?? slug ?? "uncategorized";
}

export function selectFeaturedTopics(
  topics: Topic[],
  categories: Category[],
  count = 3,
): Topic[] {
  const candidates = topics
    .filter((topic) => topic.status === "active")
    .sort(compareTopics);
  const selected: Topic[] = [];
  const selectedRoots = new Set<string>();

  for (const topic of candidates) {
    const root = rootCategorySlug(topic.category, categories);
    if (selectedRoots.has(root)) continue;
    selected.push(topic);
    selectedRoots.add(root);
    if (selected.length === count) return selected;
  }

  for (const topic of candidates) {
    if (selected.some((item) => item.topic_id === topic.topic_id)) continue;
    selected.push(topic);
    if (selected.length === count) break;
  }
  return selected;
}

export function selectSupportingTopics(
  topics: Topic[],
  featured: Topic[],
  count = 30,
): Topic[] {
  const featuredIds = new Set(featured.map((topic) => topic.topic_id));
  return topics
    .filter(
      (topic) => topic.status === "active" && !featuredIds.has(topic.topic_id),
    )
    .sort(compareTopics)
    .slice(0, count);
}

export type TopicUniverseGroup = {
  category: Category;
  count: number;
  topics: Topic[];
};

export function categoryDescendantSlugs(
  root: Category,
  categories: Category[],
): Set<string> {
  const result = new Set([root.slug]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const category of categories) {
      if (
        category.parent &&
        result.has(category.parent) &&
        !result.has(category.slug)
      ) {
        result.add(category.slug);
        changed = true;
      }
    }
  }
  return result;
}

export function buildTopicUniverse(
  topics: Topic[],
  categories: Category[],
  topicsPerGroup = 5,
): TopicUniverseGroup[] {
  return categories
    .filter((category) => category.parent === null)
    .map((category) => {
      const slugs = categoryDescendantSlugs(category, categories);
      const groupedTopics = topics
        .filter((topic) => topic.category !== null && slugs.has(topic.category))
        .sort(compareTopics);
      return {
        category,
        count: groupedTopics.length,
        topics: groupedTopics.slice(0, topicsPerGroup),
      };
    })
    .filter((group) => group.count > 0);
}
