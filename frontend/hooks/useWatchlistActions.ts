import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import { pollInterval } from "@/lib/sse";
import { toast } from "sonner";

import { fetcher, watchlistAPI } from "@/lib/api";
import { reportHandledError } from "@/lib/utils";

export interface WatchItem {
  id: number;
  ticker: string;
  ticker_name: string | null;
}

type WatchlistPayload = WatchItem[] | { data?: WatchItem[] };

interface WatchlistActionOptions {
  successMessage?: string;
  showSuccessToast?: boolean;
}

const normalizeWatchlist = (payload?: WatchlistPayload): WatchItem[] => {
  if (!payload) return [];
  return Array.isArray(payload) ? payload : payload.data ?? [];
};

export function useWatchlistActions(enabled = true) {
  const t = useTranslations("watchlist");
  const [addingTicker, setAddingTicker] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const {
    data,
    isLoading,
    mutate: mutateWatchlist,
  } = useSWR<WatchlistPayload>(enabled ? "/watchlist" : null, fetcher, {
    refreshInterval: pollInterval(15000),
  });

  const items = useMemo(() => normalizeWatchlist(data), [data]);
  const tickers = useMemo(
    () => items.map((item) => item.ticker.toUpperCase()),
    [items],
  );

  const addToWatchlist = useCallback(
    async (
      ticker: string,
      name: string,
      options: WatchlistActionOptions = {},
    ) => {
      const tickerClean = ticker.trim().toUpperCase();
      const nameClean = name.trim() || tickerClean;
      setAddingTicker(tickerClean);
      try {
        await watchlistAPI.add(tickerClean, nameClean);
        await mutateWatchlist();
        if (options.showSuccessToast !== false) {
          toast.success(
            options.successMessage
              ?? t("toast_added", { ticker: tickerClean, name: nameClean }),
          );
        }
      } catch (error) {
        const msg = reportHandledError(
          `Failed to add ${tickerClean} to watchlist`,
          error,
        );
        toast.error(t("toast_add_failed", { msg }));
        throw error;
      } finally {
        setAddingTicker(null);
      }
    },
    [mutateWatchlist, t],
  );

  const deleteFromWatchlist = useCallback(
    async (id: number) => {
      setDeletingId(id);
      try {
        await watchlistAPI.delete(id);
        await mutateWatchlist();
        toast.success(t("toast_removed"));
      } catch (error) {
        const msg = reportHandledError("Failed to delete ticker", error);
        toast.error(t("toast_delete_failed", { msg }));
        throw error;
      } finally {
        setDeletingId(null);
      }
    },
    [mutateWatchlist, t],
  );

  return {
    items,
    tickers,
    isLoading,
    addingTicker,
    deletingId,
    addToWatchlist,
    deleteFromWatchlist,
    mutateWatchlist,
  };
}
