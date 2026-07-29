import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { PortalShell } from "../../components/portal/PortalShell";
import {
  EMPTY_FILTERS,
  FilterSidebar,
  type ListingFilters,
} from "../../components/portal/FilterSidebar";
import { ListingGrid } from "../../components/portal/sections";
import { PortalButton, SectionHeading } from "../../components/portal/kit";
import { portal } from "../../api/portal";

const PAGE_SIZE = 18;

/**
 * The full tender catalogue: filter rail on the left, results on the right.
 *
 * Public. A signed-out visitor browses exactly what a vendor does — the difference between
 * them is whether the Apply button leads to a form or to registration, which is decided on
 * the detail page rather than by hiding the list.
 */
export function TendersPage() {
  const [filters, setFilters] = useState<ListingFilters>(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);

  const categories = useQuery({ queryKey: ["portal", "categories"], queryFn: portal.categories });

  const query = useMemo(
    () => ({
      q: filters.q.trim() || undefined,
      category: filters.category,
      emirate: filters.emirate,
      budget_min: filters.budget_min || undefined,
      budget_max: filters.budget_max || undefined,
      closing_within_days: filters.closing_within_days || undefined,
      sort: filters.sort,
      limit: PAGE_SIZE,
      offset,
    }),
    [filters, offset],
  );

  const listings = useQuery({
    queryKey: ["portal", "listings", "browse", query],
    queryFn: () => portal.listings(query),
    // Keeps the previous page on screen while the next loads, so changing a filter does not
    // collapse the grid to skeletons and bounce the scroll position.
    placeholderData: keepPreviousData,
  });

  const applyFilters = (next: ListingFilters) => {
    setFilters(next);
    setOffset(0); // a new filter set always starts at page one
  };

  const total = listings.data?.total ?? 0;
  const shown = (listings.data?.items ?? []).length;
  const hasMore = offset + shown < total;

  return (
    <PortalShell>
      <div className="mx-auto max-w-7xl px-5 py-12">
        <SectionHeading
          eyebrow="Open tenders"
          title="Browse the marketplace"
          description="Every tender currently accepting applications, from all seven emirates."
        />

        <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,17rem)_1fr]">
          <div className="lg:sticky lg:top-24 lg:self-start">
            <FilterSidebar
              filters={filters}
              categories={categories.data ?? []}
              onChange={applyFilters}
              onReset={() => applyFilters(EMPTY_FILTERS)}
              totalResults={listings.isPending ? undefined : total}
            />
          </div>

          <div>
            <ListingGrid
              listings={listings.data?.items ?? []}
              loading={listings.isPending}
              error={listings.isError ? (listings.error as Error).message : null}
              columns="lg:grid-cols-2 xl:grid-cols-3"
              skeletonCount={9}
              emptyTitle="No tenders match those filters"
              emptyBody="Try widening the contract value, clearing the category, or looking at a longer closing window."
            />

            {hasMore ? (
              <div className="mt-10 flex justify-center">
                <PortalButton
                  variant="ghost"
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  disabled={listings.isFetching}
                >
                  {listings.isFetching ? "Loading…" : `Show more (${total - offset - shown} left)`}
                </PortalButton>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </PortalShell>
  );
}
