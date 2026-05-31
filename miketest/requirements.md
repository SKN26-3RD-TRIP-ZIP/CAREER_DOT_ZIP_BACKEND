# miketest 요구사항

## 구현 목표

- Chrome에서 마이크 권한을 요청하고 연결 상태를 확인한다.
- 테스트 녹음 기능을 구현한다.
- 녹음 중지 후 생성된 오디오 파일을 재생할 수 있다.
- 녹음 시간을 표시한다.
- 향후 Django 백엔드 업로드, OpenAI STT/TTS 연동을 위한 준비 테스트 환경으로 활용한다.

## 환경

- React
- Vite
- TypeScript
- Tailwind CSS

## 실행 방법

1. `cd miketest`
2. `npm install`
3. `npm run dev`

## 확장 계획

1. 현재 앱에서 녹음 파일 생성과 미리듣기를 확인한다.
2. Django 백엔드 API를 추가하고 녹음 파일 업로드 기능 확장.
3. OpenAI STT 및 TTS 엔드포인트를 구현하고 프론트엔드와 연결.
