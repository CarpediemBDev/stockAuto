import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';

export type TimezoneOption = {
  id: string;
  label: string;
  timeZone: string | undefined; // undefined means local browser time
  abbr: string;
};

// label은 useTimezone() 훅이 timezone.* 키로 항상 재번역하므로 표시에 쓰이지 않는다.
// (영속 store·비-훅 직접 소비 시의 폴백용 영어 문자열)
export const TIMEZONE_OPTIONS: TimezoneOption[] = [
  { id: 'local', label: 'Local Device Time', timeZone: undefined, abbr: 'LCL' },
  { id: 'seoul', label: 'Korea Standard Time (KST)', timeZone: 'Asia/Seoul', abbr: 'KST' },
  { id: 'new_york', label: 'US Eastern Time (EST)', timeZone: 'America/New_York', abbr: 'EST' },
  { id: 'utc', label: 'Coordinated Universal Time (UTC)', timeZone: 'UTC', abbr: 'UTC' },
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
  const t = useTranslations('timezone');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setMounted(true);
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  const browserAbbr = mounted ? getBrowserTimezoneAbbr() : 'LCL';

  // id 기준으로 항상 재번역한다(영속된 라벨·정적 폴백 대신 현재 로케일 반영).
  const labelFor = (id: string, abbr: string): string =>
    id === 'local'
      ? (mounted ? t('local_with_abbr', { abbr }) : t('local'))
      : t(id);

  // Create local options array with dynamically resolved label and abbr for dropdown UI
  const timezoneOptions = TIMEZONE_OPTIONS.map((opt) => {
    const abbr = opt.id === 'local' ? browserAbbr : opt.abbr;
    return { ...opt, label: labelFor(opt.id, abbr), abbr };
  });

  // mounted가 false일 때는 무조건 첫 번째 기본 옵션(local)으로 고정하여 Hydration Mismatch를 차단
  const resolvedTimezone = mounted
    ? (selectedTimezone.id === 'local'
      ? {
          ...selectedTimezone,
          label: labelFor('local', browserAbbr),
          abbr: browserAbbr,
        }
      : { ...selectedTimezone, label: labelFor(selectedTimezone.id, selectedTimezone.abbr) })
    : {
        ...TIMEZONE_OPTIONS[0],
        label: labelFor('local', 'LCL'),
        abbr: 'LCL',
      };

  return {
    selectedTimezone: resolvedTimezone,
    timezoneOptions,
    setTimezone,
    mounted,
  };
}
