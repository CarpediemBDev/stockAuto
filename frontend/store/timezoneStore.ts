import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type TimezoneOption = {
  id: string;
  label: string;
  timeZone: string | undefined; // undefined means local browser time
  abbr: string;
};

export const TIMEZONE_OPTIONS: TimezoneOption[] = [
  { id: 'local', label: '접속 기기 시간 (Auto)', timeZone: undefined, abbr: 'Auto' },
  { id: 'seoul', label: '한국 표준시 (KST)', timeZone: 'Asia/Seoul', abbr: 'KST' },
  { id: 'new_york', label: '미동부 표준시 (EST)', timeZone: 'America/New_York', abbr: 'EST' },
  { id: 'utc', label: '협정 세계시 (UTC)', timeZone: 'UTC', abbr: 'UTC' },
];

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
