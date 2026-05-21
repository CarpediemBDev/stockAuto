"use client";

import { useState, useEffect } from "react";
import NavBar from "@/components/NavBar";
import { toast } from "sonner";
import { AlertTriangle, Server, ShieldCheck, ShieldAlert, Key, Save, Loader2 } from "lucide-react";

interface SystemSettings {
  trade_mode: string;
  broker_provider: string;
  kis_app_key: string;
  kis_app_secret: string;
  kis_account_no: string;
}

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<SystemSettings>({
    trade_mode: "SIMULATED",
    broker_provider: "KIS",
    kis_app_key: "",
    kis_app_secret: "",
    kis_account_no: "",
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [showRealWarning, setShowRealWarning] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/v1/admin");
      if (res.ok) {
        const data = await res.json();
        setSettings({
          trade_mode: data.trade_mode || "SIMULATED",
          broker_provider: data.broker_provider || "KIS",
          kis_app_key: data.kis_app_key || "",
          kis_app_secret: data.kis_app_secret || "",
          kis_account_no: data.kis_account_no || "",
        });
      }
    } catch (error) {
      toast.error("Failed to load settings.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async (forceReal = false) => {
    if (settings.trade_mode === "REAL" && !forceReal) {
      setShowRealWarning(true);
      return;
    }
    
    setShowRealWarning(false);
    setIsSaving(true);
    
    try {
      const res = await fetch("http://localhost:8000/api/v1/admin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      
      if (res.ok) {
        toast.success("Settings saved! The system has been hot-reloaded.");
        await fetchSettings();
      } else {
        toast.error("Failed to save settings.");
      }
    } catch (error) {
      toast.error("Network error while saving settings.");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-900 text-white font-sans flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white font-sans">
      <NavBar />
      
      <div className="max-w-4xl mx-auto p-6 mt-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">System Administration</h1>
          <p className="text-gray-400">Configure global trading engine settings and broker API connections.</p>
        </div>

        {/* Trade Mode Selection */}
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-6 mb-6 shadow-lg">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Server className="w-5 h-5 text-blue-400" />
            Trading Mode
          </h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* SIMULATED */}
            <div 
              onClick={() => setSettings({ ...settings, trade_mode: "SIMULATED" })}
              className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                settings.trade_mode === "SIMULATED" 
                  ? "border-blue-500 bg-blue-500/10" 
                  : "border-gray-700 hover:border-gray-600 bg-gray-900"
              }`}
            >
              <div className="flex justify-between items-start mb-2">
                <span className="font-bold text-blue-400">SIMULATED</span>
                <ShieldCheck className="w-5 h-5 text-blue-400" />
              </div>
              <p className="text-sm text-gray-400">Paper trading using live data. Safe. No API keys required.</p>
            </div>

            {/* MOCK */}
            <div 
              onClick={() => setSettings({ ...settings, trade_mode: "MOCK" })}
              className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                settings.trade_mode === "MOCK" 
                  ? "border-orange-500 bg-orange-500/10" 
                  : "border-gray-700 hover:border-gray-600 bg-gray-900"
              }`}
            >
              <div className="flex justify-between items-start mb-2">
                <span className="font-bold text-orange-400">MOCK</span>
                <Server className="w-5 h-5 text-orange-400" />
              </div>
              <p className="text-sm text-gray-400">Virtual trading via broker's mock server. Requires Mock API keys.</p>
            </div>

            {/* REAL */}
            <div 
              onClick={() => setSettings({ ...settings, trade_mode: "REAL" })}
              className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                settings.trade_mode === "REAL" 
                  ? "border-red-500 bg-red-500/10" 
                  : "border-gray-700 hover:border-gray-600 bg-gray-900"
              }`}
            >
              <div className="flex justify-between items-start mb-2">
                <span className="font-bold text-red-500">REAL</span>
                <ShieldAlert className="w-5 h-5 text-red-500" />
              </div>
              <p className="text-sm text-gray-400">Live trading with real money. Requires valid Real API keys.</p>
            </div>
          </div>
        </div>

        {/* API Credentials */}
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-6 mb-6 shadow-lg">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Key className="w-5 h-5 text-yellow-400" />
            Broker Configuration
          </h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Provider</label>
              <select 
                value={settings.broker_provider}
                onChange={(e) => setSettings({ ...settings, broker_provider: e.target.value })}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg p-2.5 text-white focus:ring-2 focus:ring-blue-500 outline-none"
              >
                <option value="KIS">Korea Investment & Securities (KIS)</option>
                <option value="TOSS" disabled>Toss Securities (Coming Soon)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">APP KEY</label>
              <input 
                type="text" 
                value={settings.kis_app_key || ""}
                onChange={(e) => setSettings({ ...settings, kis_app_key: e.target.value })}
                placeholder="Enter your API Key"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg p-2.5 text-white focus:ring-2 focus:ring-blue-500 outline-none font-mono text-sm"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">APP SECRET</label>
              <input 
                type="password" 
                value={settings.kis_app_secret || ""}
                onChange={(e) => setSettings({ ...settings, kis_app_secret: e.target.value })}
                placeholder="Enter your API Secret"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg p-2.5 text-white focus:ring-2 focus:ring-blue-500 outline-none font-mono text-sm"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">ACCOUNT NO</label>
              <input 
                type="text" 
                value={settings.kis_account_no || ""}
                onChange={(e) => setSettings({ ...settings, kis_account_no: e.target.value })}
                placeholder="e.g. 12345678-01"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg p-2.5 text-white focus:ring-2 focus:ring-blue-500 outline-none font-mono text-sm"
              />
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex justify-end gap-4">
          <button 
            onClick={() => handleSave(false)}
            disabled={isSaving}
            className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-6 rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {isSaving ? <Loader2 className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
            Save & Hot Reload
          </button>
        </div>
      </div>

      {/* Real Mode Warning Modal */}
      {showRealWarning && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 px-4">
          <div className="bg-gray-800 border border-red-500/30 rounded-xl p-6 max-w-md w-full shadow-2xl">
            <div className="flex items-center gap-3 mb-4 text-red-500">
              <AlertTriangle className="w-8 h-8" />
              <h3 className="text-xl font-bold">DANGER: REAL MODE</h3>
            </div>
            <p className="text-gray-300 mb-6">
              You are about to switch the trading engine to <strong className="text-red-400">REAL</strong> mode. 
              The system will execute trades with <strong className="text-red-400">real money</strong> using the provided API keys.
              Are you absolutely sure you want to proceed?
            </p>
            <div className="flex justify-end gap-3">
              <button 
                onClick={() => setShowRealWarning(false)}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={() => handleSave(true)}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors font-medium"
              >
                Yes, Enable Real Trading
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
