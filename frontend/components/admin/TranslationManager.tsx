'use client';
import React, { useState, useEffect } from 'react';
import { Globe, Plus, Search, Edit2, Trash2, Check, X, Loader2 } from 'lucide-react';
import { translationAPI } from '@/lib/api';
import { getErrorMessage } from '@/lib/utils';
import { toast } from "sonner";
import { useTranslations } from "next-intl";

interface TranslationItem {
  id: number;
  ticker: string;
  name_ko: string;
}

export function TranslationManager() {
  const t = useTranslations("admin_ui");
  const [translations, setTranslations] = useState<TranslationItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [currentPage, setCurrentPage] = useState<number>(1);
  const itemsPerPage = 10;
  
  const [newTicker, setNewTicker] = useState<string>("");
  const [newNameKo, setNewNameKo] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState<string>("");
  const [refreshTrigger, setRefreshTrigger] = useState<number>(0);

  useEffect(() => {
    let active = true;
    translationAPI.getAll()
      .then((res) => {
        if (active) {
          setTranslations(res.data);
          setLoading(false);
        }
      })
      .catch((error) => {
        if (active) {
          toast.error(t("translation.dict_load_failed", { error: getErrorMessage(error) }));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [refreshTrigger, t]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const tickerClean = newTicker.trim().toUpperCase();
    const nameClean = newNameKo.trim();

    if (!tickerClean || !nameClean) {
      toast.warning(t("translation.fill_both"));
      return;
    }

    setIsSubmitting(true);
    try {
      await translationAPI.save(tickerClean, nameClean);
      toast.success(t("translation.register_success", { ticker: tickerClean, name: nameClean }));
      setNewTicker("");
      setNewNameKo("");
      setRefreshTrigger(prev => prev + 1);
    } catch (error) {
      toast.error(t("translation.register_failed", { error: getErrorMessage(error) }));
    } finally {
      setIsSubmitting(false);
    }
  };

  const startEdit = (item: TranslationItem) => {
    setEditingId(item.id);
    setEditingName(item.name_ko);
  };

  const handleUpdate = async (id: number) => {
    const nameClean = editingName.trim();
    if (!nameClean) {
      toast.warning(t("translation.fill_name"));
      return;
    }

    try {
      await translationAPI.update(id, nameClean);
      toast.success(t("translation.update_success"));
      setEditingId(null);
      setRefreshTrigger(prev => prev + 1);
    } catch (error) {
      toast.error(t("translation.update_failed", { error: getErrorMessage(error) }));
    }
  };

  const handleDelete = (id: number, ticker: string) => {
    toast(t("translation.delete_confirm", { ticker }), {
      description: t("translation.delete_confirm_desc"),
      action: {
        label: t("translation.delete_label"),
        onClick: async () => {
          try {
            await translationAPI.delete(id);
            toast.success(t("translation.delete_success", { ticker }));
            setRefreshTrigger(prev => prev + 1);
          } catch (error) {
            toast.error(t("translation.delete_failed", { error: getErrorMessage(error) }));
          }
        }
      },
      cancel: {
        label: t("translation.cancel_label"),
        onClick: () => {}
      }
    });
  };

  const filteredTranslations = translations.filter(
    (t) =>
      t.ticker.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.name_ko.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="bg-surface-card/80 backdrop-blur-xl rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Plus size={18} className="text-blue-400" />
            {t("translation.register_title")}
          </h2>
          <span className="text-[10px] text-zinc-400 font-semibold bg-zinc-800 px-2 py-0.5 rounded">
            AUTO SYNC ACTIVE
          </span>
        </div>
        
        <form onSubmit={handleCreate} className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          <div>
            <label className="block text-xs text-zinc-400 font-semibold mb-1.5 uppercase tracking-wider">{t("translation.ticker_label")}</label>
            <input
              type="text"
              placeholder={t("translation.ticker_placeholder")}
              value={newTicker}
              onChange={(e) => setNewTicker(e.target.value)}
              className="w-full bg-surface-card-subtle border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 tracking-widest font-mono uppercase"
              disabled={isSubmitting}
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 font-semibold mb-1.5 uppercase tracking-wider">{t("translation.name_label")}</label>
            <input
              type="text"
              placeholder={t("translation.name_placeholder")}
              value={newNameKo}
              onChange={(e) => setNewNameKo(e.target.value)}
              className="w-full bg-surface-card-subtle border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
              disabled={isSubmitting}
            />
          </div>
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-sm py-2.5 px-4 rounded-xl shadow-lg shadow-indigo-950/20 hover:scale-[1.01] active:scale-[0.99] transition-all flex items-center justify-center gap-2"
          >
            {isSubmitting ? <><Loader2 size={16} className="animate-spin" />{t("translation.submitting")}</> : t("translation.submit")}
          </button>
        </form>
      </div>

      <div className="bg-surface-card/80 backdrop-blur-xl rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-zinc-800 pb-4">
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <Globe size={18} className="text-emerald-400" />
              {t("translation.list_title")}
            </h2>
            <p className="text-xs text-zinc-400 mt-1">
              {t("translation.list_count_pre")}<strong className="text-emerald-400">{translations.length}{t("translation.list_count_suffix")}</strong>
            </p>
          </div>
          
          <div className="relative max-w-xs w-full">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              placeholder={t("translation.search_placeholder")}
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full bg-surface-card-subtle border border-zinc-800 rounded-xl pl-10 pr-4 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center gap-3">
              <Loader2 size={36} className="animate-spin text-zinc-500" />
              <span className="text-xs text-zinc-500 font-semibold">{t("translation.db_loading")}</span>
            </div>
          ) : filteredTranslations.length === 0 ? (
            <div className="py-16 text-center">
              <Globe size={48} className="mx-auto text-zinc-700 mb-3" />
              <p className="text-sm font-semibold text-zinc-500">{t("translation.no_match")}</p>
            </div>
          ) : (() => {
            const totalPages = Math.ceil(filteredTranslations.length / itemsPerPage);
            const indexOfLastItem = currentPage * itemsPerPage;
            const indexOfFirstItem = indexOfLastItem - itemsPerPage;
            const currentItems = filteredTranslations.slice(indexOfFirstItem, indexOfLastItem);
            
            return (
              <>
                <table className="min-w-full divide-y divide-zinc-800/60">
                  <thead>
                    <tr className="text-left text-xs uppercase text-zinc-500 font-bold tracking-wider">
                      <th className="px-6 py-3.5">ID</th>
                      <th className="px-6 py-3.5">{t("translation.th_ticker")}</th>
                      <th className="px-6 py-3.5">{t("translation.th_name")}</th>
                      <th className="px-6 py-3.5 text-right">{t("translation.th_manage")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/40 text-sm">
                    {currentItems.map((item) => (
                      <tr key={item.id} className={`transition-colors duration-150 hover:bg-zinc-800/10 ${editingId === item.id ? "bg-blue-950/10" : ""}`}>
                        <td className="px-6 py-4 text-xs font-mono text-zinc-500 font-bold">{item.id}</td>
                        <td className="px-6 py-4 font-mono font-bold text-slate-300 tracking-wider">{item.ticker}</td>
                        <td className="px-6 py-4">
                          {editingId === item.id ? (
                            <input
                              type="text"
                              value={editingName}
                              onChange={(e) => setEditingName(e.target.value)}
                              className="bg-surface-card-subtle border border-indigo-500/50 rounded-lg px-3 py-1 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                              onKeyDown={(e) => {
                                if (e.key === "Enter") handleUpdate(item.id);
                                if (e.key === "Escape") setEditingId(null);
                              }}
                              autoFocus
                            />
                          ) : (
                            <span className="text-slate-100 font-medium">{item.name_ko}</span>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center justify-end gap-2">
                            {editingId === item.id ? (
                              <>
                                <button onClick={() => handleUpdate(item.id)} className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20" title={t("translation.action_save")}><Check size={16} /></button>
                                <button onClick={() => setEditingId(null)} className="p-1.5 rounded-lg bg-zinc-800 text-zinc-400 hover:bg-zinc-700" title={t("translation.action_cancel")}><X size={16} /></button>
                              </>
                            ) : (
                              <>
                                <button onClick={() => startEdit(item)} className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20" title={t("translation.action_edit")}><Edit2 size={16} /></button>
                                <button onClick={() => handleDelete(item.id, item.ticker)} className="p-1.5 rounded-lg bg-rose-500/10 text-rose-400 hover:bg-rose-500/20" title={t("translation.action_delete")}><Trash2 size={16} /></button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                
                {totalPages > 1 && (
                  <div className="flex flex-col sm:flex-row items-center justify-between border-t border-zinc-800/80 pt-5 mt-4 gap-4">
                    <span className="text-xs text-zinc-500 font-semibold">
                      Showing <strong className="text-zinc-300">{indexOfFirstItem + 1}</strong> to <strong className="text-zinc-300">{Math.min(indexOfLastItem, filteredTranslations.length)}</strong> of <strong className="text-zinc-300">{filteredTranslations.length}</strong> items
                    </span>
                    <div className="flex items-center gap-1.5">
                      <button onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))} disabled={currentPage === 1} className="px-3 py-2 rounded-xl text-xs font-bold border border-zinc-800 bg-surface-card-subtle hover:bg-zinc-800/60 disabled:opacity-40 text-zinc-400 hover:text-white transition-all">Previous</button>
                      <button type="button" className="w-9 h-9 rounded-xl text-xs font-bold transition-all flex items-center justify-center bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-lg border border-teal-500/20">{currentPage}</button>
                      <button onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))} disabled={currentPage === totalPages} className="px-3 py-2 rounded-xl text-xs font-bold border border-zinc-800 bg-surface-card-subtle hover:bg-zinc-800/60 disabled:opacity-40 text-zinc-400 hover:text-white transition-all">Next</button>
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
