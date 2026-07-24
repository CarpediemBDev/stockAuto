import {getRequestConfig} from 'next-intl/server';
import {cookies, headers} from 'next/headers';

// 딕셔너리는 정적 import로 번들에 포함시킨다.
// 예전에는 fs.readFileSync(process.cwd()/../locales/*.json)로 런타임에 읽었는데,
// next.config의 output:"standalone"에서는 서버 cwd가 .next/standalone이라
// '..'가 .next를 가리켜 항상 ENOENT로 실패했다. 그 결과 messages가 빈 객체가 되어
// 화면에 번역문 대신 'nav.trading' 같은 키 경로가 그대로 노출됐다.
// 정적 import는 빌드 시점에 번들되므로 standalone 산출물에서도 항상 동작한다.
import en from '../locales/en.json';
import ko from '../locales/ko.json';

const MESSAGES: Record<string, typeof ko> = {ko, en};
const DEFAULT_LOCALE = 'ko';

export default getRequestConfig(async () => {
  // 1. 브라우저에서 'NEXT_LOCALE' 쿠키를 읽어옵니다.
  const cookieStore = await cookies();
  let locale = cookieStore.get('NEXT_LOCALE')?.value;

  // 2. 쿠키가 없다면(첫 방문) 브라우저의 접속 지역/언어(Accept-Language)를 확인합니다.
  if (!locale) {
    const headersList = await headers();
    const acceptLanguage = headersList.get('accept-language') || '';

    // 한국어 브라우저면 'ko', 그 외 모든 국가 접속자는 기본값 'en' 배정
    if (acceptLanguage.toLowerCase().includes('ko')) {
      locale = 'ko';
    } else {
      locale = 'en';
    }
  }

  // 3. 지원하지 않는 로케일 쿠키가 들어와도 키가 노출되지 않도록 ko로 강등한다.
  if (!MESSAGES[locale]) {
    locale = DEFAULT_LOCALE;
  }

  return {
    locale,
    messages: MESSAGES[locale]
  };
});
