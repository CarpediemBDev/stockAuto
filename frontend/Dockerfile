# 1단계: 빌드 환경 구성
FROM node:18-alpine AS builder
WORKDIR /app

# 패키지 정보 복사 및 의존성 설치
COPY package*.json ./
RUN npm install

# 소스코드 전체 복사
COPY . .

# 빌드 타임에 백엔드 API 주소를 주입받기 위한 인수 정의
ARG NEXT_PUBLIC_API_BASE
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
ARG BACKEND_API_ORIGIN
ENV BACKEND_API_ORIGIN=$BACKEND_API_ORIGIN

# Next.js 빌드 수행
RUN npm run build

# 2단계: 가동 환경 구성
FROM node:18-alpine AS runner
WORKDIR /app

# 빌드 산출물 중 구동에 필요한 파일들만 최소한으로 복사 (용량 경량화)
COPY --from=builder /app/next.config.ts ./
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

# 구글 클라우드 런은 $PORT 환경변수를 주입하여 포트를 엽니다.
# npm run start가 포트 주입을 받도록 CMD를 구성합니다.
ENV PORT=3000
EXPOSE 3000

CMD npm run start -- -p $PORT
