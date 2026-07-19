import {getRequestConfig} from 'next-intl/server';
import {cookies, headers} from 'next/headers';
import fs from 'fs';
import path from 'path';

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

  // 3. 프로젝트 최상단의 locales 디렉토리 경로 계산(루트에 존재)
  const rootDir = path.resolve(process.cwd(), '..');
  const filePath = path.join(rootDir, 'locales', `${locale}.json`);
  
  let messages = {};
  try {
    const fileContents = fs.readFileSync(filePath, 'utf8');
    messages = JSON.parse(fileContents);
  } catch (error) {
    console.error(`[next-intl] Failed to load messages for locale: ${locale}`, error);
    // fallback to ko
    try {
      const fallbackPath = path.join(rootDir, 'locales', 'ko.json');
      messages = JSON.parse(fs.readFileSync(fallbackPath, 'utf8'));
    } catch (e) {
      console.error('[next-intl] Failed to load fallback messages', e);
    }
  }

  return {
    locale,
    messages
  };
});
