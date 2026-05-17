"use client";


import { Play, Square, Activity } from "lucide-react";
import { cn } from "@/lib/utils";

interface BotControlProps {
  isRunning: boolean;
  onToggle: () => void;
}

export function BotControl({ isRunning, onToggle }: BotControlProps) {
  return (
    <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl p-6 flex items-center justify-between shadow-2xl">
      <div className="flex items-center gap-4">
        <div className={cn("p-3 rounded-full flex items-center justify-center transition-colors duration-500", isRunning ? "bg-emerald-500/20 text-emerald-400" : "bg-zinc-800 text-zinc-400")}>
          <Activity size={24} className={cn(isRunning && "animate-pulse")} />
        </div>
        <div>
          <h2 className="text-xl font-bold text-white">Trading Engine</h2>
          <p className="text-sm text-zinc-400">
            Status: {isRunning ? <span className="text-emerald-400 font-medium">Running</span> : <span className="text-zinc-500 font-medium">Stopped</span>}
          </p>
        </div>
      </div>
      
      <button
        onClick={onToggle}
        className={cn(
          "flex items-center gap-2 px-6 py-3 rounded-xl font-semibold transition-all duration-300",
          isRunning 
            ? "bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20" 
            : "bg-emerald-500 text-zinc-950 hover:bg-emerald-400 shadow-[0_0_20px_rgba(16,185,129,0.3)]"
        )}
      >
        {isRunning ? (
          <>
            <Square size={18} fill="currentColor" />
            Stop Engine
          </>
        ) : (
          <>
            <Play size={18} fill="currentColor" />
            Start Engine
          </>
        )}
      </button>
    </div>
  );
}
