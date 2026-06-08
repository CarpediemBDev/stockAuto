import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { useState, useEffect } from 'react';

export type TimezoneOption = {
  id: string;
  label: string;
  timeZone: string | undefined; // undefined means local browser time
  abbr: string;
};

export const TIMEZONE_OPTIONS: TimezoneOption[] = [
  { id: 'local', label: '접속 기기 시간', timeZone: undefined, abbr: 'LCL' },
  { id: 'seoul', label: '한국 표준시 (KST)', timeZone: 'Asia/Seoul', abbr: 'KST' },
  { id: 'new_york', label: '미동부 표준시 (EST)', timeZone: 'America/New_York', abbr: 'EST' },
  { id: 'utc', label: '협정 세계시 (UTC)', timeZone: 'UTC', abbr: 'UTC' },
];

export const getBrowserTimezoneAbbr = (): string => {
  if (typeof window === 'undefined') return 'LCL';
  try {
    const parts = new Intl.DateTimeFormat('en-US', { timeZoneName: 'short' }).formatToParts(new Date());
    return parts.find((p) => p.type === 'timeZoneName')?.value || 'LCL';
  } catch {
    return 'LCL';
  }
};

interface TimezoneState {
  selectedTimezone: TimezoneOption;
  setTimezone: (id: string) => void;
}

export const useTimezoneStore = create<TimezoneState>()(
  persist(
    (set) => ({
      selectedTimezone: TIMEZONE_OPTIONS[0], // default to local
      setTimezone: (id: string) => {
        const option = TIMEZONE_OPTIONS.find((opt) => opt.id === id);
        if (option) {
          set({ selectedTimezone: option });
        }
      },
    }),
    {
      name: 'stockauto-timezone-storage', // localStorage key
    }
  )
);

export function useTimezone() {
  const { selectedTimezone, setTimezone } = useTimezoneStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setMounted(true);
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  const browserAbbr = mounted ? getBrowserTimezoneAbbr() : 'LCL';

  // Create local options array with dynamically resolved label and abbr for dropdown UI
  const timezoneOptions = TIMEZONE_OPTIONS.map((opt) => {
    if (opt.id === 'local') {
      return {
        ...opt,
        label: mounted ? `접속 기기 시간 (${browserAbbr})` : '접속 기기 시간',
        abbr: browserAbbr,
      };
    }
    return opt;
  });

  const resolvedTimezone = selectedTimezone.id === 'local'
    ? {
        ...selectedTimezone,
        label: mounted ? `접속 기기 시간 (${browserAbbr})` : '접속 기기 시간',
        abbr: browserAbbr,
      }
    : selectedTimezone;

  return {
    selectedTimezone: resolvedTimezone,
    timezoneOptions,
    setTimezone,
    mounted,
  };
}
