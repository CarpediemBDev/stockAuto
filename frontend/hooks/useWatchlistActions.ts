import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";
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
  const [addingTicker, setAddingTicker] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const {
    data,
    isLoading,
    mutate: mutateWatchlist,
  } = useSWR<WatchlistPayload>(enabled ? "/watchlist" : null, fetcher, {
    refreshInterval: 15000,
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
              ?? `${tickerClean} (${nameClean})이(가) 관심종목에 추가되었습니다.`,
          );
        }
      } catch (error) {
        const msg = reportHandledError(
          `Failed to add ${tickerClean} to watchlist`,
          error,
        );
        toast.error(`관심종목 추가 실패: ${msg}`);
        throw error;
      } finally {
        setAddingTicker(null);
      }
    },
    [mutateWatchlist],
  );

  const deleteFromWatchlist = useCallback(
    async (id: number) => {
      setDeletingId(id);
      try {
        await watchlistAPI.delete(id);
        await mutateWatchlist();
        toast.success("관심종목에서 성공적으로 제거되었습니다.");
      } catch (error) {
        const msg = reportHandledError("Failed to delete ticker", error);
        toast.error(`삭제 실패: ${msg}`);
        throw error;
      } finally {
        setDeletingId(null);
      }
    },
    [mutateWatchlist],
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
