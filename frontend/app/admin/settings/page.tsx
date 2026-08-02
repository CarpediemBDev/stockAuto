"use client";

import React, { startTransition, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";
import { toast } from "sonner";
import {
  AlertTriangle,
  Ban,
  Key,
  Loader2,
  RefreshCw,
  Save,
  Send,
  Server,
  ShieldAlert,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { accountAPI, adminAPI, authAPI, reportAPI } from "@/lib/api";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import { StrategyCatalog } from "@/components/StrategyCatalog";

type SubTab = "environment" | "telegram" | "danger";
type TradeMode = string;

interface TradeModeOption {
  id: string;
  label: string;
  description: string;
  tone: string;
  requires_credentials: boolean;
}

interface BrokerOption {
  id: string;
  label: string;
  tone: string;
  supported_modes: string[];
}

interface CredentialMeta {
  broker_name: string;
  has_credentials: boolean;
  account_no_masked: string | null;
  verification_status: string;
  verified_trade_mode: string | null;
  verified_at: string | null;
  credential_error: string | null;
}

interface UserSettings {
  trade_mode: TradeMode;
  broker_provider: string | null;
  telegram_chat_id: string;
  telegram_enabled: boolean;
  global_bot_username?: string;
  credentials: CredentialMeta[];
  available_trade_modes: TradeModeOption[];
  available_brokers: BrokerOption[];
  simulated_initial_cash_krw: number;
  strategy_type?: string;
  available_strategies?: Array<{ id: string; name: string }>;
}

interface CredentialForm {
  app_key: string;
  app_secret: string;
  account_no: string;
}

const EMPTY_FORM: CredentialForm = {
  app_key: "",
  app_secret: "",
  account_no: "",
};

const DEFAULT_SETTINGS: UserSettings = {
  trade_mode: "SIMULATED",
  broker_provider: null,
  telegram_chat_id: "",
  telegram_enabled: false,
  global_bot_username: "",
  credentials: [],
  available_trade_modes: [],
  available_brokers: [],
  simulated_initial_cash_krw: 0,
  strategy_type: "regime_switching",
  available_strategies: [],
};

const SETTINGS_ENDPOINT = "/admin";

function normalizeTradeMode(value: unknown, modes: TradeModeOption[]): TradeMode {
  const normalized = typeof value === "string" ? value : "";
  return modes.some((mode) => mode.id === normalized)
    ? normalized
    : modes[0]?.id || "SIMULATED";
}

function supportsTradeMode(broker: BrokerOption | undefined, tradeMode: string): boolean {
  return !broker || broker.supported_modes.includes(tradeMode);
}

function unsupportedTradeModeMessage(
  broker: BrokerOption | undefined,
  tradeMode: string,
  t: (key: string, values?: Record<string, string>) => string,
): string {
  if (!broker) return "";
  return t("unsupported_mode", { broker: broker.label, mode: tradeMode });
}

export default function PersonalSettingsPage() {
  const t = useTranslations("settings");
  const router = useRouter();
  const { clearAuth, isAuthenticated, isInitialized, username: storedUsername } = useAuthStore();
  const [dbSettings, setDbSettings] = useState<UserSettings>(DEFAULT_SETTINGS);
  
  // Per-broker form state
  const [forms, setForms] = useState<Record<string, CredentialForm>>({});
  const [localVerified, setLocalVerified] = useState<Record<string, boolean>>({});
  const [credentialBroker, setCredentialBroker] = useState<string>("");

  const [username, setUsername] = useState<string>("");
  const [subTab, setSubTab] = useState<SubTab>("environment");
  const [isSaving, setIsSaving] = useState(false);
  const [isCredentialSaving, setIsCredentialSaving] = useState(false);
  const [isCredentialDeleting, setIsCredentialDeleting] = useState(false);
  const [showRealWarning, setShowRealWarning] = useState(false);
  const [showResetModal, setShowResetModal] = useState(false);
  const [showLiquidateModal, setShowLiquidateModal] = useState(false);
  const [isDangerActionLoading, setIsDangerActionLoading] = useState(false);
  const [isPersonalReportSending, setIsPersonalReportSending] = useState(false);
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [isPasswordChanging, setIsPasswordChanging] = useState(false);

  useEffect(() => {
    if (isInitialized) {
      if (!isAuthenticated) {
        router.push("/login");
        return;
      }

      startTransition(() => {
        setUsername(storedUsername || "");
      });
    }
  }, [isInitialized, isAuthenticated, storedUsername, router]);

  const applySettings = useCallback((data: Partial<UserSettings>) => {
    const availableTradeModes = data.available_trade_modes || [];
    const availableBrokers = data.available_brokers || [];
    const brokerProvider = data.broker_provider || availableBrokers[0]?.id || null;
    setDbSettings({
      trade_mode: normalizeTradeMode(data.trade_mode, availableTradeModes),
      broker_provider: brokerProvider,
      telegram_chat_id: data.telegram_chat_id || "",
      telegram_enabled: Boolean(data.telegram_enabled),
      global_bot_username: data.global_bot_username || "stockauto_official_bot",
      credentials: data.credentials || [],
      available_trade_modes: availableTradeModes,
      available_brokers: availableBrokers,
      simulated_initial_cash_krw: data.simulated_initial_cash_krw || 0,
      strategy_type: data.strategy_type || "regime_switching",
      available_strategies: data.available_strategies || [],
    });
    setForms(Object.fromEntries(
      availableBrokers.map((broker) => [broker.id, { ...EMPTY_FORM }])
    ));
    setLocalVerified(Object.fromEntries(
      availableBrokers.map((broker) => [broker.id, false])
    ));
    setCredentialBroker((current) => (
      availableBrokers.some((broker) => broker.id === current)
        ? current
        : brokerProvider || availableBrokers[0]?.id || ""
    ));
  }, []);

  const { isLoading: isSettingsLoading, mutate: mutateSettings } = useSWR<Partial<UserSettings>>(
    isInitialized && isAuthenticated ? SETTINGS_ENDPOINT : null,
    async () => {
      const res = await adminAPI.getSettings();
      return res.data;
    },
    {
      onSuccess: applySettings,
      onError: (err) => {
        const error = err as Error;
        toast.error(error.message || t("load_failed"));
      },
      revalidateOnFocus: false,
    },
  );

  const fetchSettings = useCallback(async () => {
    await mutateSettings();
  }, [mutateSettings]);

  const activeBroker = dbSettings.broker_provider || dbSettings.available_brokers[0]?.id || "";
  const activeBrokerOption = useMemo(() => {
    return dbSettings.available_brokers.find((broker) => broker.id === activeBroker);
  }, [dbSettings.available_brokers, activeBroker]);
  const credentialBrokerOption = useMemo(() => {
    return dbSettings.available_brokers.find((broker) => broker.id === credentialBroker);
  }, [dbSettings.available_brokers, credentialBroker]);
  const activeCred = useMemo(() => {
    return dbSettings.credentials.find((c) => c.broker_name === credentialBroker);
  }, [dbSettings.credentials, credentialBroker]);
  const executionCred = useMemo(() => {
    return dbSettings.credentials.find((c) => c.broker_name === activeBroker);
  }, [dbSettings.credentials, activeBroker]);

  const activeTradeMode = dbSettings.available_trade_modes.find(
    (mode) => mode.id === dbSettings.trade_mode
  );
  const requiresBrokerCredentials = Boolean(activeTradeMode?.requires_credentials);
  const selectedModeUnsupported = !supportsTradeMode(activeBrokerOption, dbSettings.trade_mode);
  const selectedModeUnsupportedMessage = unsupportedTradeModeMessage(activeBrokerOption, dbSettings.trade_mode, t);
  const credentialModeUnsupported = !supportsTradeMode(credentialBrokerOption, dbSettings.trade_mode);
  const credentialSaveMode = requiresBrokerCredentials && !credentialModeUnsupported
    ? dbSettings.trade_mode
    : "KEY_ONLY";
  const isVerifiedForSelectedMode = useMemo(() => {
    if (!executionCred) return false;
    return (
      executionCred.has_credentials &&
      executionCred.verification_status === "verified" &&
      executionCred.verified_trade_mode === dbSettings.trade_mode
    );
  }, [executionCred, dbSettings.trade_mode]);
  const isCredentialVerifiedForSelectedMode = useMemo(() => {
    if (!activeCred) return false;
    return (
      activeCred.has_credentials &&
      activeCred.verification_status === "verified" &&
      activeCred.verified_trade_mode === dbSettings.trade_mode
    );
  }, [activeCred, dbSettings.trade_mode]);

  const credentialStatusLabel = useMemo(() => {
    if (!activeCred) return t("cred_status.unsaved");
    if (activeCred.verification_status === "crypto_error") return t("cred_status.crypto_error");
    if (isCredentialVerifiedForSelectedMode) return t("cred_status.verified");
    if (activeCred.verification_status === "stored") return t("cred_status.stored");
    if (activeCred.has_credentials) return t("cred_status.reverify");
    return t("cred_status.unsaved");
  }, [activeCred, isCredentialVerifiedForSelectedMode, t]);

  const handleVerifyCredential = async (provider: string) => {
    const broker = dbSettings.available_brokers.find((item) => item.id === provider);
    const modeForCredential = requiresBrokerCredentials && supportsTradeMode(broker, dbSettings.trade_mode)
      ? dbSettings.trade_mode
      : "KEY_ONLY";

    const form = forms[provider];
    if (!form) {
      toast.error(t("toast.reset_form_failed"));
      return;
    }
    const isToss = provider === "TOSS";
    if (!form.app_key.trim() || !form.app_secret.trim() || (!isToss && !form.account_no.trim())) {
      toast.error(isToss ? t("toast.fill_keys_toss") : t("toast.fill_keys_kis"));
      return;
    }

    setIsCredentialSaving(true);
    try {
      const res = await adminAPI.verifyAndSaveCredentials({
        trade_mode: modeForCredential,
        broker_name: provider,
        app_key: form.app_key,
        app_secret: form.app_secret,
        account_no: form.account_no,
      });
      if (res.data?.success) {
        applySettings(res.data.settings);
        setLocalVerified(prev => ({ ...prev, [provider]: true }));
        toast.success(
          modeForCredential === "KEY_ONLY"
            ? t("toast.cred_saved_unverified", { provider })
            : t("toast.cred_verified", { provider })
        );
      } else {
        toast.error(res.data?.message || t("toast.cred_verify_failed", { provider }));
      }
    } catch (err) {
      toast.error((err as Error).message || t("toast.cred_verify_failed", { provider }));
    } finally {
      setIsCredentialSaving(false);
    }
  };

  const handleDeleteCredentials = async (provider: string) => {
    setIsCredentialDeleting(true);
    try {
      const res = await adminAPI.deleteCredential(provider);
      if (res.data?.settings) {
        applySettings(res.data.settings);
      } else {
        await fetchSettings();
      }
      toast.success(t("toast.cred_deleted", { provider }));
    } catch (err) {
      toast.error((err as Error).message || t("toast.cred_delete_failed", { provider }));
    } finally {
      setIsCredentialDeleting(false);
    }
  };

  const handleSave = async (forceReal = false) => {
    if (selectedModeUnsupported) {
      toast.error(selectedModeUnsupportedMessage);
      return;
    }

    if (dbSettings.trade_mode === "REAL" && !forceReal) {
      setShowRealWarning(true);
      return;
    }

    if (requiresBrokerCredentials) {
      if (!isVerifiedForSelectedMode) {
         toast.error(t("toast.need_cred_for_mode", { mode: dbSettings.trade_mode, broker: activeBroker }));
         return;
      }
    }

    setShowRealWarning(false);
    setIsSaving(true);

    try {
      const payload = {
        trade_mode: dbSettings.trade_mode,
        broker_provider: dbSettings.broker_provider,
        telegram_chat_id: dbSettings.telegram_chat_id,
        telegram_enabled: dbSettings.telegram_enabled,
        strategy_type: dbSettings.strategy_type,
      };

      const res = await adminAPI.saveSettings(payload);
      applySettings(res.data);
      toast.success(t("toast.settings_saved"));
    } catch (err) {
      toast.error((err as Error).message || t("toast.settings_save_failed"));
      fetchSettings().catch(() => {
        toast.error(t("toast.sync_failed"));
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleResetBalance = async () => {
    setIsDangerActionLoading(true);
    try {
      await accountAPI.resetBalance();
      toast.success(t("toast.account_reset_done"));
      setShowResetModal(false);
      await fetchSettings();
    } catch (err) {
      toast.error((err as Error).message || t("toast.account_reset_failed"));
    } finally {
      setIsDangerActionLoading(false);
    }
  };

  const handleForceLiquidate = async () => {
    setIsDangerActionLoading(true);
    try {
      const res = await accountAPI.forceLiquidate();
      toast.success(res.data.message || t("toast.liquidate_done"));
      setShowLiquidateModal(false);
    } catch (err) {
      toast.error((err as Error).message || t("toast.liquidate_failed"));
    } finally {
      setIsDangerActionLoading(false);
    }
  };

  const handleTriggerPersonalReport = async () => {
    setIsPersonalReportSending(true);
    try {
      await reportAPI.triggerPersonalReport();
      toast.success(t("toast.report_sent"));
    } catch (err) {
      toast.error((err as Error).message || t("toast.report_failed"));
    } finally {
      setIsPersonalReportSending(false);
    }
  };

  const handleChangePassword = async () => {
    if (!oldPassword || !newPassword || !confirmNewPassword) {
      toast.error(t("toast.fill_passwords"));
      return;
    }
    if (newPassword.length < 12) {
      toast.error(t("toast.password_too_short"));
      return;
    }
    if (newPassword !== confirmNewPassword) {
      toast.error(t("toast.password_mismatch"));
      return;
    }

    setIsPasswordChanging(true);
    try {
      await authAPI.changePassword(oldPassword, newPassword);
      clearAuth();
      toast.success(t("toast.password_changed"));
      router.replace("/login");
    } catch (err) {
      toast.error((err as Error).message || t("toast.password_change_failed"));
    } finally {
      setIsPasswordChanging(false);
    }
  };

  const modeToneClasses: Record<string, string> = {
    blue: "text-blue-400 border-blue-500 bg-blue-500/5",
    amber: "text-amber-400 border-amber-500 bg-amber-500/5",
    red: "text-red-400 border-red-500 bg-red-500/5",
  };
  const modeIcons: Record<string, typeof ShieldCheck> = {
    SIMULATED: ShieldCheck,
    MOCK: Server,
    REAL: ShieldAlert,
  };
  const modeCards = dbSettings.available_trade_modes.map((mode) => ({
    ...mode,
    color: modeToneClasses[mode.tone] || modeToneClasses.blue,
    icon: modeIcons[mode.id] || Server,
    isUnsupported: !supportsTradeMode(activeBrokerOption, mode.id),
    unsupportedMessage: unsupportedTradeModeMessage(activeBrokerOption, mode.id, t),
  }));

  if (isSettingsLoading || !isInitialized || !isAuthenticated) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-zinc-950 text-white flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  const activeForm = forms[credentialBroker] || EMPTY_FORM;
  const credentialActionLabel = (() => {
    if (localVerified[credentialBroker]) {
      return credentialSaveMode === "KEY_ONLY" ? t("cred_button.saved") : t("cred_button.verified");
    }
    return credentialSaveMode === "KEY_ONLY"
      ? t("cred_button.key_only", { broker: credentialBroker })
      : t("cred_button.verify", { broker: credentialBroker });
  })();

  return (
    <div className="min-h-screen bg-zinc-950 text-white font-sans">
      <div className="max-w-4xl mx-auto p-6 mt-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-zinc-800 pb-4 mb-8 gap-4">
          <div>
            <h1 className="text-2xl font-extrabold text-zinc-100 mb-1">{t("title")}</h1>
            <p className="text-zinc-400 text-xs">{t("subtitle")}</p>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-8 items-start">
          <div className="w-full md:w-48 shrink-0 flex flex-row md:flex-col gap-1 bg-zinc-950 md:bg-transparent pb-3 md:pb-0 border-b md:border-b-0 border-zinc-900 overflow-x-auto md:overflow-x-visible">
            {[
              { id: "environment", label: "Trading", icon: Server, color: "text-blue-400" },
              { id: "telegram", label: "Telegram", icon: Send, color: "text-indigo-400" },
              { id: "danger", label: "Danger", icon: AlertTriangle, color: "text-red-500" },
            ].map((item) => {
              const Icon = item.icon;
              const isActive = subTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setSubTab(item.id as SubTab)}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-bold transition-all text-left w-full cursor-pointer whitespace-nowrap ${
                    isActive ? "bg-zinc-900 text-white" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40"
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${isActive ? item.color : "text-zinc-500"}`} />
                  {item.label}
                </button>
              );
            })}
          </div>

          <div className="flex-1 min-w-0 w-full">
            {subTab === "environment" && (
              <div className="space-y-8">
                <div className="space-y-4">
                  <div className="flex flex-col gap-1.5 pb-3 border-b border-zinc-900">
                    <h2 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                      <Server className="w-4 h-4 text-blue-400" />
                      Trading Mode
                    </h2>
                  </div>

                  {modeCards.length === 0 ? (
                    <div className="flex flex-col items-center justify-center p-6 bg-red-500/10 border border-red-500/20 rounded-xl gap-3 text-center">
                      <AlertTriangle className="w-6 h-6 text-red-500" />
                      <div>
                        <p className="text-xs font-bold text-red-400 mb-1">{t("load_error_title")}</p>
                        <p className="text-[11px] text-red-400/80">{t("load_error_hint")}</p>
                      </div>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      {modeCards.map((mode) => {
                        const Icon = mode.icon;
                        const isActive = dbSettings.trade_mode === mode.id;
                        return (
                          <button
                            key={mode.id}
                            type="button"
                            disabled={mode.isUnsupported}
                            title={mode.isUnsupported ? mode.unsupportedMessage : undefined}
                            onClick={() => setDbSettings((prev) => ({ ...prev, trade_mode: mode.id }))}
                            className={`p-4 rounded-lg border text-left transition-all ${
                              mode.isUnsupported
                                ? "cursor-not-allowed border-zinc-900 bg-zinc-900/10 opacity-45"
                                : "cursor-pointer"
                            } ${
                              isActive ? mode.color : "border-zinc-900 bg-zinc-900/10 hover:border-zinc-800"
                            }`}
                          >
                            <div className="flex justify-between items-start mb-2">
                              <span className="font-bold text-xs">{mode.label}</span>
                              <Icon className="w-4 h-4" />
                            </div>
                            <p className="text-[10px] text-zinc-500 leading-relaxed">{mode.description}</p>
                            {mode.isUnsupported && (
                              <p className="mt-2 text-[10px] font-bold text-red-400">
                                {mode.unsupportedMessage}
                              </p>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div className="space-y-4 pt-6 border-t border-zinc-900">
                  <div className="flex flex-col gap-1.5 pb-2">
                    <h2 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                      <Server className="w-4 h-4 text-emerald-400" />
                      {t("active_strategy")}
                    </h2>
                    <p className="text-[10px] text-zinc-500">{t("active_strategy_hint")}</p>
                  </div>
                  
                  <div className="relative">
                    <label className="block text-xs font-semibold text-zinc-400 mb-2">{t("selected_strategy")}</label>
                    <StrategyCatalog
                      value={dbSettings.strategy_type || "regime_switching"}
                      onSelect={(id) => setDbSettings((prev) => ({ ...prev, strategy_type: id }))}
                    />
                    <p className="mt-2 text-[10px] text-zinc-500">{t("strategy_save_hint")}</p>
                  </div>
                </div>

                <div className="space-y-4 pt-6 border-t border-zinc-900">
                  <div className="flex flex-col gap-1.5 pb-2">
                    <h2 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                      <Key className="w-4 h-4 text-amber-400" />
                      Broker Config
                    </h2>
                  </div>

                  <div className="space-y-4 animate-in fade-in slide-in-from-top-1 duration-300">
                    <div>
                      <label className="block text-xs font-semibold text-zinc-400 mb-1.5">Provider</label>
                      <div className="flex gap-2">
                        {dbSettings.available_brokers.length === 0 ? (
                          <div className="w-full py-3 rounded-lg border border-red-500/20 bg-red-500/5 text-red-400/80 text-xs text-center">
                            {t("broker_load_failed")}
                          </div>
                        ) : (
                          dbSettings.available_brokers.map((broker) => {
                            const brokerUnsupported = !supportsTradeMode(broker, dbSettings.trade_mode);
                            const isCredentialActive = credentialBroker === broker.id;
                            return (
                              <button
                                key={broker.id}
                                type="button"
                                title={brokerUnsupported ? unsupportedTradeModeMessage(broker, dbSettings.trade_mode, t) : undefined}
                                onClick={() => {
                                  setCredentialBroker(broker.id);
                                  if (!brokerUnsupported) {
                                    setDbSettings(prev => ({ ...prev, broker_provider: broker.id }));
                                  }
                                }}
                                className={`flex-1 py-3 rounded-lg border text-xs font-bold transition-all cursor-pointer ${
                                  isCredentialActive
                                    ? broker.tone === "amber"
                                      ? "border-amber-500 bg-amber-500/10 text-amber-400"
                                      : "border-blue-500 bg-blue-500/10 text-blue-400"
                                    : "border-zinc-800 bg-zinc-900/50 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-800"
                                }`}
                              >
                                {broker.label} ({broker.id})
                                {brokerUnsupported && (
                                  <span className="ml-1 text-[10px] text-red-400">{t("key_only_badge")}</span>
                                )}
                              </button>
                            );
                          })
                        )}
                      </div>
                    </div>

                    {!requiresBrokerCredentials && (
                      <div className="p-4 rounded-lg border border-blue-500/20 bg-blue-500/5 flex items-center gap-3">
                        <ShieldCheck className="w-5 h-5 text-blue-400 shrink-0" />
                        <p className="text-[11px] text-zinc-400 leading-relaxed">
                          {t("simulated_key_note")}
                        </p>
                      </div>
                    )}

                    {credentialModeUnsupported && requiresBrokerCredentials && (
                      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 flex items-start gap-3">
                        <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                        <p className="text-xs font-semibold text-amber-200 leading-relaxed">
                          {unsupportedTradeModeMessage(credentialBrokerOption, dbSettings.trade_mode, t)} {t("unsupported_key_note")}
                        </p>
                      </div>
                    )}

                    {selectedModeUnsupported && (
                      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 flex items-start gap-3">
                        <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                        <p className="text-xs font-semibold text-red-300 leading-relaxed">
                          {selectedModeUnsupportedMessage}
                        </p>
                      </div>
                    )}

                      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
                        <div className="rounded-lg border border-zinc-900 bg-zinc-900/20 p-3">
                          <p className="text-[10px] text-zinc-500 mb-1">{t("save_state")}</p>
                          <p className="text-xs font-bold text-zinc-200">
                            {activeCred?.has_credentials ? t("saved") : t("none")}
                          </p>
                        </div>
                        <div className="rounded-lg border border-zinc-900 bg-zinc-900/20 p-3">
                          <p className="text-[10px] text-zinc-500 mb-1">{t("verify_state")}</p>
                          <p className={`text-xs font-bold ${isCredentialVerifiedForSelectedMode ? "text-emerald-400" : "text-amber-400"}`}>
                            {credentialStatusLabel}
                          </p>
                        </div>
                        <div className="rounded-lg border border-zinc-900 bg-zinc-900/20 p-3">
                          <p className="text-[10px] text-zinc-500 mb-1">{t("verify_mode")}</p>
                          <p className="text-xs font-bold text-zinc-200">{activeCred?.verified_trade_mode || "-"}</p>
                        </div>
                        <div className="rounded-lg border border-zinc-900 bg-zinc-900/20 p-3">
                          <p className="text-[10px] text-zinc-500 mb-1">{t("account")}</p>
                          <p className="text-xs font-bold text-zinc-200 font-mono">
                            {activeCred?.account_no_masked || "-"}
                          </p>
                        </div>
                      </div>

                      {activeCred?.credential_error && (
                        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
                          {activeCred.credential_error}
                        </div>
                      )}

                      <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-5 space-y-4">
                        <div className="flex flex-col gap-1 border-b border-zinc-800/50 pb-3">
                          <h3 className="text-xs font-extrabold text-zinc-200 flex items-center gap-2">
                            <Key className="w-4 h-4 text-emerald-400" />
                            {t("cred_manage_title", { broker: credentialBroker })}
                          </h3>
                          <p className="text-[10px] text-zinc-500">
                            {credentialSaveMode === "KEY_ONLY"
                              ? t("cred_note_store_only")
                              : t("cred_note_verified")}
                          </p>
                        </div>
                        <div className="grid grid-cols-1 gap-3">
                        <div>
                          <label className="block text-xs font-semibold text-zinc-400 mb-1.5">APP KEY</label>
                          <input
                            type="text"
                            value={activeForm.app_key}
                            onChange={(e) => { 
                              setForms((prev) => ({ ...prev, [credentialBroker]: { ...(prev[credentialBroker] || EMPTY_FORM), app_key: e.target.value } }));
                              setLocalVerified((prev) => ({ ...prev, [credentialBroker]: false }));
                            }}
                            placeholder={activeCred?.has_credentials ? t("placeholder_overwrite") : t("placeholder_app_key")}
                            className="w-full bg-zinc-950 border border-zinc-900 rounded-lg p-3 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none font-mono text-xs transition-all"
                            autoComplete="off"
                          />
                        </div>

                        <div>
                          <label className="block text-xs font-semibold text-zinc-400 mb-1.5">APP SECRET</label>
                          <input
                            type="password"
                            value={activeForm.app_secret}
                            onChange={(e) => { 
                              setForms((prev) => ({ ...prev, [credentialBroker]: { ...(prev[credentialBroker] || EMPTY_FORM), app_secret: e.target.value } }));
                              setLocalVerified((prev) => ({ ...prev, [credentialBroker]: false }));
                            }}
                            placeholder={activeCred?.has_credentials ? t("placeholder_overwrite") : t("placeholder_app_secret")}
                            className="w-full bg-zinc-950 border border-zinc-900 rounded-lg p-3 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none font-mono text-xs transition-all"
                            autoComplete="new-password"
                          />
                        </div>

                        <div>
                          <label className="block text-xs font-semibold text-zinc-400 mb-1.5">
                            {credentialBroker === "TOSS" ? t("account_seq_optional") : "ACCOUNT NO"}
                          </label>
                          <input
                            type="text"
                            value={activeForm.account_no}
                            onChange={(e) => { 
                              setForms((prev) => ({ ...prev, [credentialBroker]: { ...(prev[credentialBroker] || EMPTY_FORM), account_no: e.target.value } }));
                              setLocalVerified((prev) => ({ ...prev, [credentialBroker]: false }));
                            }}
                            placeholder={activeCred?.has_credentials ? `${activeCred.account_no_masked || "••••••••"} ${t("placeholder_overwrite")}` : (credentialBroker === "TOSS" ? t("account_no_toss_hint") : t("placeholder_account_no"))}
                            className="w-full bg-zinc-950 border border-zinc-900 rounded-lg p-3 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none font-mono text-xs transition-all"
                            autoComplete="off"
                          />
                        </div>
                      </div>

                      <div className="flex flex-col sm:flex-row gap-2 justify-end">
                        {activeCred?.has_credentials && (
                          <button
                            type="button"
                            onClick={() => handleDeleteCredentials(credentialBroker)}
                            disabled={isCredentialDeleting || isCredentialSaving}
                            className="border border-red-500/40 text-red-300 hover:bg-red-500/10 disabled:opacity-50 px-4 py-2.5 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 cursor-pointer"
                          >
                            {isCredentialDeleting ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Trash2 className="w-3.5 h-3.5" />
                            )}
                            {t("delete_cred")}
                          </button>
                        )}
                        <button
                          onClick={() => handleVerifyCredential(credentialBroker)}
                          disabled={isCredentialSaving || isSaving || !credentialBroker}
                          className={`px-4 py-2.5 rounded-lg text-xs font-bold transition-all active:scale-95 flex items-center justify-center gap-2 cursor-pointer shadow-md ${
                            localVerified[credentialBroker]
                              ? "bg-zinc-800 text-emerald-400 border border-emerald-500/30" 
                              : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-900/30 disabled:opacity-50"
                          }`}
                        >
                          {isCredentialSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                          {credentialActionLabel}
                        </button>
                      </div>
                      </div>
                  </div>
                </div>

                <div className="flex justify-end items-center pt-6 border-t border-zinc-900">
                  <button
                    onClick={() => handleSave(false)}
                    disabled={isSaving || selectedModeUnsupported}
                    title={selectedModeUnsupported ? selectedModeUnsupportedMessage : undefined}
                    className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-lg text-xs font-bold transition-all active:scale-95 flex items-center gap-2 cursor-pointer shadow-md shadow-blue-900/30"
                  >
                    {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    {t("save_all")}
                  </button>
                </div>
              </div>
            )}

            {subTab === "telegram" && (
              <div className="space-y-6">
                <div className="flex flex-col gap-1.5 pb-4 border-b border-zinc-900">
                  <h2 className="text-base font-bold text-zinc-100 flex items-center gap-2">
                    <Send className="w-4 h-4 text-indigo-400" />
                    Telegram Bridge
                  </h2>
                </div>

                <div className="space-y-4">
                  <div className="flex justify-between items-center bg-zinc-900/30 border border-zinc-900 rounded-lg p-4">
                    <span className="text-xs font-semibold text-zinc-300">{t("telegram_link")}</span>
                    <label className="relative inline-flex items-center cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={dbSettings.telegram_enabled}
                        onChange={(e) => setDbSettings((prev) => ({ ...prev, telegram_enabled: e.target.checked }))}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-zinc-500 after:border-zinc-500 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-500"></div>
                    </label>
                  </div>

                  <div className="p-4 rounded-lg border border-indigo-500/20 bg-indigo-500/5 space-y-3">
                    <span className="text-xs font-bold text-indigo-400">{t("one_click_connect")}</span>
                    <a
                      href={
                        dbSettings.telegram_enabled && dbSettings.global_bot_username
                          ? `https://t.me/${dbSettings.global_bot_username}?start=${username}`
                          : "#"
                      }
                      onClick={(e) => {
                        if (!dbSettings.telegram_enabled) {
                          e.preventDefault();
                          toast.warning(t("toast.telegram_switch_first"));
                        }
                      }}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`inline-flex w-full items-center justify-center gap-2 px-4 py-3 rounded-lg text-xs font-black transition-all active:scale-[0.98] shadow-md ${
                        dbSettings.telegram_enabled
                          ? "bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-500/20"
                          : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                      }`}
                    >
                      <Send className="w-3.5 h-3.5" />
                      {t("official_telegram_connect")}
                    </a>
                  </div>

                  <div className="p-4 rounded-lg border border-zinc-900 bg-zinc-900/10 space-y-3">
                    <span className="text-xs font-bold text-zinc-400">{t("manual_chat_id")}</span>
                    <input
                      type="text"
                      value={dbSettings.telegram_chat_id || ""}
                      onChange={(e) => setDbSettings((prev) => ({ ...prev, telegram_chat_id: e.target.value }))}
                      placeholder="987654321"
                      disabled={!dbSettings.telegram_enabled}
                      className="w-full bg-zinc-950 border border-zinc-900 rounded-lg p-3 text-white focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 outline-none font-mono text-xs disabled:opacity-40 transition-all"
                    />
                  </div>

                  <div className="p-4 rounded-lg border border-indigo-500/20 bg-indigo-500/5 space-y-3">
                    <div className="flex flex-col gap-1">
                      <span className="text-xs font-bold text-indigo-400">{t("manual_report_send")}</span>
                      <p className="text-[10px] text-zinc-400">{t("manual_report_hint")}</p>
                    </div>
                    <button
                      onClick={handleTriggerPersonalReport}
                      disabled={!dbSettings.telegram_enabled || isPersonalReportSending}
                      className={`inline-flex w-full items-center justify-center gap-2 px-4 py-3 rounded-lg text-xs font-black transition-all active:scale-[0.98] shadow-md ${
                        dbSettings.telegram_enabled && !isPersonalReportSending
                          ? "bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-500/20"
                          : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                      }`}
                    >
                      {isPersonalReportSending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                      {t("get_report_now")}
                    </button>
                  </div>
                </div>

                <div className="flex justify-end pt-6 border-t border-zinc-900">
                  <button
                    onClick={() => handleSave(false)}
                    disabled={isSaving}
                    className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-lg text-xs font-bold transition-all active:scale-95 flex items-center gap-2 cursor-pointer shadow-md shadow-indigo-900/30"
                  >
                    {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    {t("save_telegram")}
                  </button>
                </div>
              </div>
            )}

            {subTab === "danger" && (
              <div className="space-y-6">
                <div className="flex flex-col gap-1.5 pb-4 border-b border-zinc-900">
                  <h2 className="text-base font-bold text-red-400 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-500" />
                    Danger Zone
                  </h2>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="sm:col-span-2 p-4 bg-zinc-900/20 rounded-lg border border-zinc-900">
                    <div>
                      <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                        <Key className="w-3.5 h-3.5 text-zinc-400" />
                        {t("change_password")}
                      </h3>
                      <p className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">
                        {t("change_password_hint")}
                      </p>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
                      <input
                        type="password"
                        value={oldPassword}
                        onChange={(event) => setOldPassword(event.target.value)}
                        placeholder={t("current_password")}
                        autoComplete="current-password"
                        className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-white text-xs outline-none focus:border-red-500"
                      />
                      <input
                        type="password"
                        value={newPassword}
                        onChange={(event) => setNewPassword(event.target.value)}
                        placeholder={t("new_password")}
                        autoComplete="new-password"
                        className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-white text-xs outline-none focus:border-red-500"
                      />
                      <input
                        type="password"
                        value={confirmNewPassword}
                        onChange={(event) => setConfirmNewPassword(event.target.value)}
                        placeholder={t("confirm_password")}
                        autoComplete="new-password"
                        className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-white text-xs outline-none focus:border-red-500"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={handleChangePassword}
                      disabled={isPasswordChanging}
                      className="mt-3 w-full py-2 rounded-lg bg-red-500/10 hover:bg-red-500/20 disabled:opacity-50 text-red-400 border border-red-500/30 text-xs font-bold transition-all active:scale-[0.99]"
                    >
                      {isPasswordChanging ? t("changing") : t("change_password_button")}
                    </button>
                  </div>

                  <div className="p-4 bg-zinc-900/20 rounded-lg border border-zinc-900 flex flex-col justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                        <RefreshCw className="w-3.5 h-3.5 text-zinc-400" />
                        {t("reset_sim_title")}
                      </h3>
                      <p className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">
                        {t("reset_sim_hint", { amount: dbSettings.simulated_initial_cash_krw.toLocaleString() })}
                      </p>
                    </div>
                    <div className="mt-4">
                      {dbSettings.trade_mode === "SIMULATED" ? (
                        <button
                          onClick={() => setShowResetModal(true)}
                          className="w-full py-2 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 text-xs font-bold transition-all active:scale-[0.98] cursor-pointer"
                        >
                          {t("reset_balance")}
                        </button>
                      ) : (
                        <p className="text-[10px] text-zinc-500 text-center font-semibold italic bg-zinc-950/50 py-2 rounded-lg">
                          {t("sim_only")}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="p-4 bg-zinc-900/20 rounded-lg border border-zinc-900 flex flex-col justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                        <Ban className="w-3.5 h-3.5 text-zinc-400" />
                        {t("force_liquidate_title")}
                      </h3>
                      <p className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">
                        {t("force_liquidate_hint")}
                      </p>
                    </div>
                    <div className="mt-4">
                      <button
                        onClick={() => setShowLiquidateModal(true)}
                        className="w-full py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-all active:scale-[0.98] flex items-center justify-center gap-1 cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        {t("liquidate_all")}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {showRealWarning && (
          <div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center"
            onClick={() => setShowRealWarning(false)}
          >
            <div
              className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl animate-in fade-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex flex-col items-center text-center gap-4">
                <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center">
                  <ShieldAlert className="w-7 h-7 text-red-500" />
                </div>
                <h3 className="text-lg font-extrabold text-white">{t("real_confirm_title")}</h3>
                <p className="text-xs text-red-300 font-semibold leading-relaxed">
                  {t("real_confirm_hint")}
                </p>
                <div className="flex gap-3 w-full pt-2">
                  <button
                    onClick={() => setShowRealWarning(false)}
                    className="flex-1 py-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-bold transition-all cursor-pointer"
                  >
                    {t("cancel")}
                  </button>
                  <button
                    onClick={() => handleSave(true)}
                    className="flex-1 py-2.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5"
                  >
                    <ShieldAlert className="w-3.5 h-3.5" />
                    {t("save_real")}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {showResetModal && (
          <div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center"
            onClick={() => setShowResetModal(false)}
          >
            <div
              className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl animate-in fade-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex flex-col items-center text-center gap-4">
                <div className="w-14 h-14 rounded-full bg-amber-500/10 flex items-center justify-center">
                  <RefreshCw className="w-7 h-7 text-amber-500" />
                </div>
                <h3 className="text-lg font-extrabold text-white">{t("reset_confirm_title")}</h3>
                <p className="text-xs text-red-300 font-semibold leading-relaxed">{t("reset_confirm_hint")}</p>
                <div className="flex gap-3 w-full pt-2">
                  <button
                    onClick={() => setShowResetModal(false)}
                    className="flex-1 py-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-bold transition-all cursor-pointer"
                  >
                    {t("cancel")}
                  </button>
                  <button
                    onClick={handleResetBalance}
                    disabled={isDangerActionLoading}
                    className="flex-1 py-2.5 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5"
                  >
                    {isDangerActionLoading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="w-3.5 h-3.5" />
                    )}
                    {t("reset")}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {showLiquidateModal && (
          <div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center"
            onClick={() => setShowLiquidateModal(false)}
          >
            <div
              className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl animate-in fade-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex flex-col items-center text-center gap-4">
                <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center">
                  <Ban className="w-7 h-7 text-red-500" />
                </div>
                <h3 className="text-lg font-extrabold text-white">{t("liquidate_confirm_title")}</h3>
                <p className="text-xs text-red-300 font-semibold leading-relaxed">
                  {t("liquidate_confirm_hint")}
                </p>
                <div className="flex gap-3 w-full pt-2">
                  <button
                    onClick={() => setShowLiquidateModal(false)}
                    className="flex-1 py-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-bold transition-all cursor-pointer"
                  >
                    {t("cancel")}
                  </button>
                  <button
                    onClick={handleForceLiquidate}
                    disabled={isDangerActionLoading}
                    className="flex-1 py-2.5 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5"
                  >
                    {isDangerActionLoading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="w-3.5 h-3.5" />
                    )}
                    {t("liquidate_proceed")}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
