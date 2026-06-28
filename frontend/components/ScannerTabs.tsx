'use client';

import { cn } from '@/lib/utils';

export type ScannerTab = '15m' | 'swing' | 'after-hours';

interface ScannerTabsProps {
  activeTab: ScannerTab;
  setActiveTab?: (tab: ScannerTab) => void;
  className?: string;
}

const TABS: Array<{
  id: ScannerTab;
  label: string;
  color: string;
}> = [
  { id: '15m', label: '15m 단타', color: 'bg-amber-500 border-amber-500 text-amber-400' },
  { id: 'swing', label: '내일 돌파 스윙', color: 'bg-indigo-500 border-indigo-500 text-indigo-400' },
  { id: 'after-hours', label: '에프터장 후보', color: 'bg-emerald-500 border-emerald-500 text-emerald-400' },
];

export function ScannerTabs({ activeTab, setActiveTab, className }: ScannerTabsProps) {
  return (
    <div className={cn('flex border-b border-zinc-800/80 bg-zinc-900/20 px-5 pt-3 gap-6 overflow-x-auto', className)}>
      {TABS.map((tab) => {
        const isActive = activeTab === tab.id;
        const [, borderClass, textClass] = tab.color.split(' ');
        return (
          <button
            key={tab.id}
            onClick={() => setActiveTab?.(tab.id)}
            className={cn(
              'pb-3 text-xs font-bold transition-all duration-300 flex items-center gap-2 cursor-pointer border-b-2 whitespace-nowrap',
              isActive ? `${borderClass} ${textClass} font-extrabold` : 'border-transparent text-zinc-500 hover:text-zinc-300'
            )}
          >
            <span className={cn('w-1.5 h-1.5 rounded-full', tab.color.split(' ')[0], isActive && 'animate-pulse')} />
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
