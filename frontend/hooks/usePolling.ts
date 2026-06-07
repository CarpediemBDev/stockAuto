import { useEffect, useRef } from 'react';

/**
 * 특정 주기(interval)마다 callback 함수를 실행하는 커스텀 훅입니다.
 * 컴포넌트 마운트 시 즉시 한 번 실행하며, 이전 요청이 완료되지 않은 경우 취소할 수 있는 AbortSignal을 제공합니다.
 * (중첩 방지: setInterval 대신 재귀적 setTimeout을 사용하여 이전 요청이 끝난 뒤에만 다음 대기열을 시작합니다)
 */
export function usePolling(callback: (signal: AbortSignal) => Promise<void> | void, interval: number) {
  const savedCallback = useRef(callback);

  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    const controller = new AbortController();
    let timeoutId: NodeJS.Timeout;

    const tick = async () => {
      if (controller.signal.aborted) return;
      
      try {
        // 콜백에 현재 컨트롤러의 시그널을 전달
        await savedCallback.current(controller.signal);
      } finally {
        if (!controller.signal.aborted) {
          // 요청 완료 후 interval 만큼 대기 후 다시 tick 호출 (중첩 원천 차단)
          timeoutId = setTimeout(tick, interval);
        }
      }
    };
    
    // 즉시 실행
    tick();

    return () => {
      controller.abort(); // 언마운트 또는 interval 변경 시 진행 중인 요청 취소
      if (timeoutId) {
        clearTimeout(timeoutId); // 대기 중인 다음 실행 예약 취소
      }
    };
  }, [interval]);
}
