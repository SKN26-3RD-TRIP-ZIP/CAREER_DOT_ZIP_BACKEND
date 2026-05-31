# miketest

간단한 React + Vite 기반 마이크 테스트 앱입니다. Chrome에서 MediaRecorder를 이용한 마이크 권한 요청, 녹음, 녹음 파일 미리 듣기 기능을 제공합니다.

## 설치

```bash
cd miketest
npm install
```
## STT 백엔드 설정

1. `.env.example`을 `.env`로 복사합니다.
2. `.env`에서 `OPENAI_API_KEY=your-openai-api-key` 값을 실제 OpenAI API 키로 변경합니다.
3. 별도 터미널에서 `npm run backend`를 실행합니다.
4. `npm run dev`로 프론트엔드를 실행한 후, 브라우저에서 `STT 변환` 버튼을 누릅니다.

## 실행

```bash
npm run dev
```

## 기능

- 마이크 권한 요청
- 녹음 시작 / 녹음 중지
- 녹음 시간 표시
- 녹음 파일 미리 듣기

## 개발 목표

이 앱은 기존 프로젝트가 없는 상태에서 음성 모의면접 기능 개발을 빠르게 시작하기 위한 테스트 환경입니다. 이후 기능을 실제 프로젝트로 옮겨가면서 백엔드 업로드, STT/TTS 연동 작업을 진행할 수 있습니다.
