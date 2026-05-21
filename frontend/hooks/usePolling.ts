import { useEffect, useRef } from 'react';

/**
 * 특정 주기(interval)마다 callback 함수를 실행하는 커스텀 훅입니다.
 * 컴포넌트 마운트 시 즉시 한 번 실행하며, 이전 요청이 완료되지 않은 경우 취소할 수 있는 AbortSignal을 제공합니다.
 */
export function usePolling(callback: (signal: AbortSignal) => Promise<void> | void, interval: number) {
  const savedCallback = useRef(callback);

  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    const controller = new AbortController();

    const tick = async () => {
      // 콜백에 현재 컨트롤러의 시그널을 전달
      await savedCallback.current(controller.signal);
    };
    
    // setTimeout 꼼수 대신 직접 즉시 실행
    tick();
    const id = setInterval(tick, interval);

    return () => {
      clearInterval(id);
      controller.abort(); // 언마운트 또는 interval 변경 시 진행 중인 요청 취소
    };
  }, [interval]);
}
