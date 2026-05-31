import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';

type PermissionState = 'idle' | 'granted' | 'denied' | 'unsupported';
type SttMode = 'quality' | 'mini' | 'browser' | 'clova';
type TtsMode = 'openai' | 'browser';

const OPENAI_STT_QUALITY_MODEL = 'gpt-4o-transcribe';
const OPENAI_STT_MINI_MODEL = 'gpt-4o-mini-transcribe';
const OPENAI_TTS_VOICES = [
  'alloy',
  'ash',
  'ballad',
  'coral',
  'echo',
  'fable',
  'nova',
  'onyx',
  'sage',
  'shimmer',
  'verse',
  'marin',
  'cedar'
];
const OPENAI_TTS_VOICE_STORAGE_KEY = 'miketest.openaiTtsVoice';
const BROWSER_TTS_VOICE_STORAGE_KEY = 'miketest.browserTtsVoice';

const formatTimer = (seconds: number) => {
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0');
  const ss = String(seconds % 60).padStart(2, '0');
  return `${mm}:${ss}`;
};

const getSpeechRecognition = () => window.SpeechRecognition ?? window.webkitSpeechRecognition;

const getStoredValue = (key: string, fallback = '') => {
  if (typeof window === 'undefined') {
    return fallback;
  }
  return window.localStorage.getItem(key) ?? fallback;
};

const getVoiceKey = (voice: SpeechSynthesisVoice) => `${voice.voiceURI}::${voice.name}::${voice.lang}`;

const getVoiceLabel = (voice: SpeechSynthesisVoice) => `${voice.name} (${voice.lang})`;

const isKoreanVoice = (voice: SpeechSynthesisVoice) => voice.lang === 'ko-KR' || voice.lang.toLowerCase().startsWith('ko');

const sortBrowserVoices = (voices: SpeechSynthesisVoice[]) =>
  [...voices].sort((a, b) => {
    const koreanDelta = Number(isKoreanVoice(b)) - Number(isKoreanVoice(a));
    if (koreanDelta !== 0) {
      return koreanDelta;
    }
    return `${a.lang} ${a.name}`.localeCompare(`${b.lang} ${b.name}`);
  });

const audioBufferToWavBlob = (audioBuffer: AudioBuffer) => {
  const channelCount = audioBuffer.numberOfChannels;
  const sampleRate = audioBuffer.sampleRate;
  const sampleCount = audioBuffer.length;
  const bytesPerSample = 2;
  const blockAlign = channelCount * bytesPerSample;
  const buffer = new ArrayBuffer(44 + sampleCount * blockAlign);
  const view = new DataView(buffer);

  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + sampleCount * blockAlign, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channelCount, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, sampleCount * blockAlign, true);

  let offset = 44;
  for (let i = 0; i < sampleCount; i += 1) {
    for (let channel = 0; channel < channelCount; channel += 1) {
      const sample = Math.max(-1, Math.min(1, audioBuffer.getChannelData(channel)[i]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += bytesPerSample;
    }
  }

  return new Blob([buffer], { type: 'audio/wav' });
};

const parseApiError = async (response: Response) => {
  const contentType = response.headers.get('content-type');
  let errorText = await response.text();

  if (contentType?.includes('application/json')) {
    try {
      const parsed = JSON.parse(errorText);
      errorText =
        typeof parsed.error === 'string'
          ? parsed.error
          : parsed.error?.message ?? JSON.stringify(parsed);
    } catch {
      // Keep the raw response text.
    }
  }

  return errorText;
};

function App() {
  const [permission, setPermission] = useState<PermissionState>('idle');
  const [cameraPermission, setCameraPermission] = useState<PermissionState>('idle');
  const [statusMessage, setStatusMessage] = useState('마이크 권한을 요청하고 연결 상태를 확인하세요.');
  const [cameraStatus, setCameraStatus] = useState('카메라 권한을 요청하면 미리보기를 확인할 수 있습니다.');
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [cameraEnabled, setCameraEnabled] = useState(false);
  const [recorder, setRecorder] = useState<MediaRecorder | null>(null);
  const [recording, setRecording] = useState(false);
  const [recordedUrl, setRecordedUrl] = useState<string | null>(null);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [sttMode, setSttMode] = useState<SttMode>('quality');
  const [ttsMode, setTtsMode] = useState<TtsMode>('openai');
  const [openAiQualityText, setOpenAiQualityText] = useState('');
  const [openAiMiniText, setOpenAiMiniText] = useState('');
  const [browserText, setBrowserText] = useState('');
  const [clovaText, setClovaText] = useState('');
  const [finalText, setFinalText] = useState('');
  const [questionText, setQuestionText] = useState('자기소개를 1분 이내로 해 주세요.');
  const [sttLoading, setSttLoading] = useState(false);
  const [sttError, setSttError] = useState<string | null>(null);
  const [browserSttError, setBrowserSttError] = useState<string | null>(null);
  const [ttsLoading, setTtsLoading] = useState(false);
  const [ttsError, setTtsError] = useState<string | null>(null);
  const [ttsAudioUrl, setTtsAudioUrl] = useState<string | null>(null);
  const [timer, setTimer] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [cameraDeviceCount, setCameraDeviceCount] = useState<number | null>(null);
  const [browserVoices, setBrowserVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedOpenAiVoice, setSelectedOpenAiVoice] = useState(() =>
    getStoredValue(OPENAI_TTS_VOICE_STORAGE_KEY, 'alloy')
  );
  const [selectedBrowserVoiceKey, setSelectedBrowserVoiceKey] = useState(() =>
    getStoredValue(BROWSER_TTS_VOICE_STORAGE_KEY)
  );
  const [lastTtsMethod, setLastTtsMethod] = useState<TtsMode>('openai');
  const chunksRef = useRef<Blob[]>([]);
  const intervalRef = useRef<number | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const waveformCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const browserFinalTranscriptRef = useRef('');

  const hasMedia = useMemo(() => permission === 'granted' && mediaStream !== null, [permission, mediaStream]);
  const hasCamera = useMemo(() => cameraPermission === 'granted' && cameraStream !== null, [cameraPermission, cameraStream]);
  const canUseBrowserStt = typeof window !== 'undefined' && Boolean(getSpeechRecognition());
  const canUseBrowserTts = typeof window !== 'undefined' && 'speechSynthesis' in window;
  const readableQuestion = questionText.trim();
  const sortedBrowserVoices = useMemo(() => sortBrowserVoices(browserVoices), [browserVoices]);
  const selectedBrowserVoice = useMemo(
    () => sortedBrowserVoices.find((voice) => getVoiceKey(voice) === selectedBrowserVoiceKey) ?? null,
    [selectedBrowserVoiceKey, sortedBrowserVoices]
  );

  useEffect(() => {
    if (!canUseBrowserTts) {
      return;
    }

    const loadVoices = () => setBrowserVoices(window.speechSynthesis.getVoices());
    loadVoices();
    window.speechSynthesis.addEventListener('voiceschanged', loadVoices);

    return () => {
      window.speechSynthesis.removeEventListener('voiceschanged', loadVoices);
      window.speechSynthesis.cancel();
    };
  }, [canUseBrowserTts]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const safeVoice = OPENAI_TTS_VOICES.includes(selectedOpenAiVoice) ? selectedOpenAiVoice : 'alloy';
    if (safeVoice !== selectedOpenAiVoice) {
      setSelectedOpenAiVoice(safeVoice);
      return;
    }
    window.localStorage.setItem(OPENAI_TTS_VOICE_STORAGE_KEY, safeVoice);
  }, [selectedOpenAiVoice]);

  useEffect(() => {
    if (!sortedBrowserVoices.length) {
      return;
    }

    const selectedVoiceExists = sortedBrowserVoices.some((voice) => getVoiceKey(voice) === selectedBrowserVoiceKey);
    if (!selectedBrowserVoiceKey || !selectedVoiceExists) {
      const preferredVoice = sortedBrowserVoices.find(isKoreanVoice) ?? sortedBrowserVoices[0];
      setSelectedBrowserVoiceKey(getVoiceKey(preferredVoice));
    }
  }, [selectedBrowserVoiceKey, sortedBrowserVoices]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    if (selectedBrowserVoiceKey) {
      window.localStorage.setItem(BROWSER_TTS_VOICE_STORAGE_KEY, selectedBrowserVoiceKey);
    }
  }, [selectedBrowserVoiceKey]);

  useEffect(() => {
    return () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
      }
      if (mediaStream) {
        mediaStream.getTracks().forEach((track) => track.stop());
      }
      if (cameraStream) {
        cameraStream.getTracks().forEach((track) => track.stop());
      }
      recognitionRef.current?.abort();
      window.speechSynthesis?.cancel();
    };
  }, [mediaStream, cameraStream]);

  useEffect(() => {
    return () => {
      if (ttsAudioUrl) {
        URL.revokeObjectURL(ttsAudioUrl);
      }
    };
  }, [ttsAudioUrl]);

  useEffect(() => {
    if (!recording) {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    intervalRef.current = window.setInterval(() => {
      setTimer((current) => current + 1);
    }, 1000);

    return () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
      }
    };
  }, [recording]);

  useEffect(() => {
    if (videoRef.current && cameraStream) {
      videoRef.current.srcObject = cameraStream;
    }
  }, [cameraStream]);

  const requestMicrophone = async (): Promise<MediaStream | null> => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setPermission('unsupported');
      setStatusMessage('현재 브라우저에서 마이크 기능을 지원하지 않습니다. Chrome에서 실행해 주세요.');
      return null;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setMediaStream(stream);
      setPermission('granted');
      setStatusMessage('마이크 연결 성공. 녹음을 시작할 수 있습니다.');
      setError(null);
      await startWaveform(stream);
      return stream;
    } catch {
      setPermission('denied');
      setStatusMessage('마이크 권한이 필요합니다. 브라우저 권한 요청을 허용해 주세요.');
      setError('마이크 권한을 사용할 수 없습니다.');
    }
    return null;
  };

  const requestCamera = async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setCameraPermission('unsupported');
      setCameraStatus('현재 브라우저에서 카메라 기능을 지원하지 않습니다.');
      return;
    }

    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      setCameraDeviceCount(devices.filter((device) => device.kind === 'videoinput').length);

      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      setCameraStream(stream);
      setCameraPermission('granted');
      setCameraStatus('카메라 연결 성공. 아래에서 미리보기를 확인하세요.');
      setCameraEnabled(true);
      setCameraError(null);
    } catch (err) {
      const errorName = err instanceof DOMException ? err.name : 'UnknownError';
      setCameraPermission('denied');
      setCameraError(`카메라 권한을 사용할 수 없습니다. 브라우저 오류: ${errorName}`);
      setCameraStatus('카메라 권한이 필요합니다. 브라우저 권한 요청을 허용해 주세요.');
    }
  };

  const stopCamera = () => {
    if (cameraStream) {
      cameraStream.getTracks().forEach((track) => track.stop());
    }
    setCameraStream(null);
    setCameraEnabled(false);
    setCameraPermission('idle');
    setCameraError(null);
    setCameraDeviceCount(null);
    setCameraStatus('카메라 미리보기가 종료되었습니다.');
  };

  const startBrowserRecognition = () => {
    if (sttMode !== 'browser') {
      return;
    }

    const Recognition = getSpeechRecognition();
    if (!Recognition) {
      setBrowserSttError('현재 브라우저에서 브라우저 내장 음성 인식을 지원하지 않습니다.');
      return;
    }

    browserFinalTranscriptRef.current = '';
    setBrowserText('');
    setBrowserSttError(null);

    const recognition = new Recognition();
    recognition.lang = 'ko-KR';
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onresult = (event) => {
      let interimTranscript = '';

      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const transcript = event.results[index][0]?.transcript ?? '';
        if (event.results[index].isFinal) {
          browserFinalTranscriptRef.current += `${transcript} `;
        } else {
          interimTranscript += transcript;
        }
      }

      setBrowserText(`${browserFinalTranscriptRef.current}${interimTranscript}`.trim());
    };

    recognition.onerror = (event) => {
      if (event.error === 'no-speech' || event.error === 'aborted') {
        return;
      }
      setBrowserSttError(`브라우저 STT 오류: ${event.error}`);
    };

    recognition.onend = () => {
      setBrowserText((current) => current || browserFinalTranscriptRef.current.trim());
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const stopBrowserRecognition = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
  };

  const handleStartRecording = async () => {
    let activeStream = mediaStream;

    if (!activeStream) {
      activeStream = await requestMicrophone();
      if (!activeStream) {
        return;
      }
    }

    try {
      const localChunks: Blob[] = [];
      const mediaRecorder = new MediaRecorder(activeStream, { mimeType: 'audio/webm' });

      if (recordedUrl) {
        URL.revokeObjectURL(recordedUrl);
      }
      setRecordedUrl(null);
      setRecordedBlob(null);
      setOpenAiQualityText('');
      setOpenAiMiniText('');
      setBrowserText('');
      setClovaText('');
      setFinalText('');
      setSttError(null);
      setBrowserSttError(null);

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          localChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(localChunks, { type: 'audio/webm' });
        const url = URL.createObjectURL(blob);
        setRecordedUrl(url);
        setRecordedBlob(blob);
        chunksRef.current = localChunks;
      };

      startBrowserRecognition();
      mediaRecorder.start();
      setRecorder(mediaRecorder);
      setRecording(true);
      setTimer(0);
      setStatusMessage('녹음 중입니다. 중지 버튼을 눌러 녹음을 완료하세요.');
      setError(null);
    } catch {
      setError('녹음기를 시작하는 동안 오류가 발생했습니다.');
    }
  };

  const handleStopRecording = () => {
    if (!recorder) {
      setError('현재 녹음 중이 아닙니다.');
      return;
    }

    if (recorder.state !== 'inactive') {
      recorder.stop();
    }

    stopBrowserRecognition();
    setRecording(false);
    setStatusMessage('녹음이 중지되었습니다. 아래에서 재생하고 STT 결과를 비교하세요.');
    stopWaveform();
  };

  const requestOpenAiStt = async (model: string) => {
    if (!recordedBlob) {
      throw new Error('녹음 파일이 없습니다. 먼저 녹음을 진행하세요.');
    }

    const formData = new FormData();
    formData.append('audio', recordedBlob, 'voice.webm');
    formData.append('model', model);

    const response = await fetch('/api/stt', {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      throw new Error(await parseApiError(response));
    }

    const data = await response.json();
    return typeof data.text === 'string' ? data.text : '';
  };

  const requestClovaStt = async () => {
    if (!recordedBlob) {
      throw new Error('녹음 파일이 없습니다. 먼저 녹음을 진행하세요.');
    }

    let wavBlob: Blob;
    try {
      const arrayBuffer = await recordedBlob.arrayBuffer();
      const audioContext = new AudioContext();
      const decodedAudio = await audioContext.decodeAudioData(arrayBuffer.slice(0));
      wavBlob = audioBufferToWavBlob(decodedAudio);
      await audioContext.close();
    } catch (error) {
      throw new Error('오디오 파일 변환 실패: CLOVA Speech Domain 요청용 WAV 변환에 실패했습니다.');
    }

    const formData = new FormData();
    formData.append('audio', wavBlob, 'voice.wav');

    const response = await fetch('/api/clova/stt', {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      throw new Error(await parseApiError(response));
    }

    const data = await response.json();
    return typeof data.text === 'string' ? data.text : '';
  };

  const convertToText = async () => {
    if (!recordedBlob) {
      setSttError('녹음 파일이 없습니다. 먼저 녹음을 진행하세요.');
      return;
    }

    setSttLoading(true);
    setSttError(null);

    try {
      if (sttMode === 'browser') {
        const browserResult = browserText.trim();
        setFinalText(browserResult);
        setStatusMessage('브라우저 STT 결과를 최종 답변으로 가져왔습니다.');
        return;
      }

      if (sttMode === 'clova') {
        const clovaResult = await requestClovaStt();
        setClovaText(clovaResult);
        setFinalText(clovaResult || browserText);
        setStatusMessage('CLOVA STT 변환이 완료되었습니다.');
        return;
      }

      const model = sttMode === 'quality' ? OPENAI_STT_QUALITY_MODEL : OPENAI_STT_MINI_MODEL;
      const openAiResult = await requestOpenAiStt(model);

      if (sttMode === 'quality') {
        setOpenAiQualityText(openAiResult);
      } else {
        setOpenAiMiniText(openAiResult);
      }

      setFinalText(openAiResult || browserText);
      setStatusMessage('OpenAI STT 변환이 완료되었습니다.');
    } catch (err) {
      const message = err instanceof Error ? err.message : '알 수 없는 오류';
      setSttError(`STT 변환 실패: ${message}`);
    } finally {
      setSttLoading(false);
    }
  };

  const playOpenAiTts = async () => {
    if (!readableQuestion) {
      setTtsError('읽을 질문 텍스트가 없습니다.');
      return;
    }

    setTtsLoading(true);
    setTtsError(null);
    setLastTtsMethod('openai');

    try {
      const response = await fetch('/api/tts', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ text: readableQuestion, voice: selectedOpenAiVoice })
      });

      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }

      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      setTtsAudioUrl((previousUrl) => {
        if (previousUrl) {
          URL.revokeObjectURL(previousUrl);
        }
        return audioUrl;
      });

      const audio = new Audio(audioUrl);
      await audio.play();
    } catch (err) {
      const message = err instanceof Error ? err.message : '알 수 없는 오류';
      setTtsError(`OpenAI TTS 실패: ${message}`);
    } finally {
      setTtsLoading(false);
    }
  };

  const playBrowserTts = () => {
    if (!canUseBrowserTts) {
      setTtsError('현재 브라우저에서 브라우저 내장 TTS를 사용할 수 없습니다.');
      return;
    }
    if (!readableQuestion) {
      setTtsError('읽을 질문 텍스트가 없습니다.');
      return;
    }
    if (!sortedBrowserVoices.length) {
      setTtsError('사용 가능한 브라우저 음성을 찾을 수 없습니다.');
      return;
    }

    window.speechSynthesis.cancel();
    setTtsError(null);
    setLastTtsMethod('browser');

    const utterance = new SpeechSynthesisUtterance(readableQuestion);
    const koVoice = sortedBrowserVoices.find(isKoreanVoice);
    const voiceToUse = selectedBrowserVoice ?? koVoice ?? sortedBrowserVoices[0];

    if (voiceToUse) {
      utterance.voice = voiceToUse;
      utterance.lang = voiceToUse.lang;
    } else {
      utterance.lang = 'ko-KR';
    }

    utterance.onerror = () => {
      setTtsError('브라우저 TTS 재생 중 오류가 발생했습니다.');
    };

    window.speechSynthesis.speak(utterance);
  };

  const handlePlaySelectedTts = () => {
    if (ttsMode === 'openai') {
      void playOpenAiTts();
      return;
    }
    playBrowserTts();
  };

  const handleReplayTts = () => {
    if (lastTtsMethod === 'openai') {
      void playOpenAiTts();
      return;
    }
    playBrowserTts();
  };

  const handleFinalTextChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    setFinalText(event.target.value);
  };

  const handleSaveText = () => {
    if (!finalText.trim()) {
      setSttError('최종 답변 텍스트가 비어 있습니다.');
      return;
    }
    setStatusMessage('최종 답변 텍스트가 저장되었습니다.');
  };

  const handleReset = () => {
    if (recording && recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
    stopBrowserRecognition();
    setRecordedUrl((previousUrl) => {
      if (previousUrl) {
        URL.revokeObjectURL(previousUrl);
      }
      return null;
    });
    setRecordedBlob(null);
    setOpenAiQualityText('');
    setOpenAiMiniText('');
    setBrowserText('');
    setClovaText('');
    setFinalText('');
    setSttError(null);
    setBrowserSttError(null);
    setTtsError(null);
    setTtsAudioUrl((previousUrl) => {
      if (previousUrl) {
        URL.revokeObjectURL(previousUrl);
      }
      return null;
    });
    setTimer(0);
    setRecording(false);
    setStatusMessage('새로운 테스트 녹음을 시작하세요.');
    setError(null);
    chunksRef.current = [];
    stopWaveform();
  };

  const stopWaveform = () => {
    if (animationRef.current !== null) {
      window.cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    if (analyserRef.current) {
      analyserRef.current.disconnect();
      analyserRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.suspend();
    }
  };

  const drawWaveform = () => {
    const canvas = waveformCanvasRef.current;
    const analyser = analyserRef.current;
    if (!canvas || !analyser) {
      return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return;
    }

    const width = canvas.width;
    const height = canvas.height;
    const dataArray = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(dataArray);

    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(0, 0, width, height);

    ctx.lineWidth = 2;
    ctx.strokeStyle = '#0f172a';
    ctx.beginPath();

    const sliceWidth = width / dataArray.length;
    let x = 0;

    for (let i = 0; i < dataArray.length; i += 1) {
      const v = dataArray[i] / 128.0;
      const y = (v * height) / 2;

      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }

      x += sliceWidth;
    }

    ctx.lineTo(width, height / 2);
    ctx.stroke();

    animationRef.current = window.requestAnimationFrame(drawWaveform);
  };

  const startWaveform = async (stream: MediaStream) => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext();
    }

    await audioContextRef.current.resume();
    const source = audioContextRef.current.createMediaStreamSource(stream);
    const analyser = audioContextRef.current.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);

    analyserRef.current = analyser;
    if (animationRef.current !== null) {
      window.cancelAnimationFrame(animationRef.current);
    }
    drawWaveform();
  };

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10 text-slate-900">
      <div className="mx-auto w-full max-w-5xl">
        <header>
          <h1 className="text-3xl font-semibold text-slate-950">OpenAI / Browser 음성 비교 테스트</h1>
          <p className="mt-3 text-slate-600">
            기존 OpenAI STT/TTS 흐름을 유지하면서 Chrome 내장 Web Speech API 결과를 함께 비교합니다.
          </p>
        </header>

        <section className="mt-8 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h2 className="text-lg font-semibold text-slate-950">STT 방식 선택</h2>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  ['quality', 'gpt-4o STT'],
                  ['mini', 'gpt-4o mini STT'],
                  ['clova', 'CLOVA STT'],
                  ['browser', 'Browser STT']
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={`rounded-lg border px-4 py-3 text-sm font-semibold transition ${
                      sttMode === value
                        ? 'border-slate-950 bg-slate-950 text-white'
                        : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                    }`}
                    onClick={() => setSttMode(value as SttMode)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {!canUseBrowserStt ? (
                <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                  현재 브라우저에서 브라우저 내장 음성 인식을 지원하지 않습니다.
                </p>
              ) : null}
            </div>

            <div>
              <h2 className="text-lg font-semibold text-slate-950">TTS 방식 선택</h2>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                {[
                  ['openai', 'OpenAI TTS'],
                  ['browser', 'Browser TTS']
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={`rounded-lg border px-4 py-3 text-sm font-semibold transition ${
                      ttsMode === value
                        ? 'border-slate-950 bg-slate-950 text-white'
                        : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                    }`}
                    onClick={() => setTtsMode(value as TtsMode)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {!canUseBrowserTts ? (
                <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                  현재 브라우저에서 브라우저 내장 TTS를 사용할 수 없습니다.
                </p>
              ) : null}
            </div>
          </div>
        </section>

        <section className="mt-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-950">1. 마이크 테스트</h2>
              <p className="mt-2 text-sm text-slate-600">Chrome에서 마이크 권한을 요청하고 녹음을 준비합니다.</p>
            </div>
            <button
              type="button"
              className="rounded-lg bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-700"
              onClick={requestMicrophone}
            >
              마이크 권한 요청
            </button>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-2">
            <div className="rounded-lg bg-slate-50 p-4">
              <p className="text-sm text-slate-500">마이크 상태</p>
              <p className="mt-2 font-semibold text-slate-900">
                {permission === 'idle' ? '대기 중' : permission === 'granted' ? '허용됨' : permission === 'denied' ? '거부됨' : '미지원'}
              </p>
            </div>
            <div className="rounded-lg bg-slate-50 p-4">
              <p className="text-sm text-slate-500">상태 메시지</p>
              <p className="mt-2 font-semibold text-slate-900">{statusMessage}</p>
            </div>
          </div>

          {error ? <p className="mt-4 rounded-lg bg-rose-50 p-4 text-sm text-rose-700">{error}</p> : null}
        </section>

        <section className="mt-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-950">2. 테스트 녹음</h2>
              <p className="mt-2 text-sm text-slate-600">MediaRecorder 녹음과 Browser STT 인식을 동시에 실행할 수 있습니다.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-lg bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleStartRecording}
                disabled={recording}
              >
                녹음 시작
              </button>
              <button
                type="button"
                className="rounded-lg bg-amber-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleStopRecording}
                disabled={!recording}
              >
                녹음 중지
              </button>
              <button
                type="button"
                className="rounded-lg bg-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-300"
                onClick={handleReset}
              >
                리셋
              </button>
            </div>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <div className="rounded-lg bg-slate-50 p-4">
              <p className="text-sm text-slate-500">녹음 가능 여부</p>
              <p className="mt-2 font-semibold text-slate-900">{hasMedia ? '가능' : '불가능'}</p>
            </div>
            <div className="rounded-lg bg-slate-50 p-4">
              <p className="text-sm text-slate-500">녹음 상태</p>
              <p className="mt-2 font-semibold text-slate-900">{recording ? '녹음 중' : '대기 중'}</p>
            </div>
            <div className="rounded-lg bg-slate-50 p-4">
              <p className="text-sm text-slate-500">녹음 시간</p>
              <p className="mt-2 font-semibold text-slate-900">{formatTimer(timer)}</p>
            </div>
          </div>

          <div className="mt-5 rounded-lg bg-slate-50 p-4">
            <p className="text-sm text-slate-500">오디오 파형</p>
            <canvas ref={waveformCanvasRef} className="mt-3 h-32 w-full rounded-lg bg-white" width={900} height={180} />
          </div>

          <div className="mt-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <p className="text-sm text-slate-600">
              {sttMode === 'browser'
                ? 'Browser STT 결과를 최종 답변으로 가져옵니다.'
                : sttMode === 'clova'
                  ? '녹음 파일을 CLOVA STT API로 전송해 변환합니다.'
                : `녹음 파일을 ${sttMode === 'quality' ? OPENAI_STT_QUALITY_MODEL : OPENAI_STT_MINI_MODEL} 모델로 변환합니다.`}
            </p>
            <button
              type="button"
              className="rounded-lg bg-emerald-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={convertToText}
              disabled={!recordedBlob || sttLoading}
            >
              {sttLoading ? '변환 중...' : 'STT 결과 가져오기'}
            </button>
          </div>

          {sttError ? <div className="mt-4 rounded-lg bg-rose-50 p-4 text-sm text-rose-700">{sttError}</div> : null}
          {browserSttError ? <div className="mt-4 rounded-lg bg-amber-50 p-4 text-sm text-amber-800">{browserSttError}</div> : null}

          {recordedUrl ? (
            <div className="mt-5 rounded-lg border border-slate-200 p-4">
              <p className="text-sm font-semibold text-slate-900">녹음 파일 미리듣기</p>
              <audio className="mt-3 w-full" controls src={recordedUrl} />
            </div>
          ) : null}
        </section>

        <section className="mt-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-950">3. STT 결과 비교</h2>
              <p className="mt-2 text-sm text-slate-600">같은 녹음에 대한 OpenAI STT와 Browser STT 결과를 나란히 확인합니다.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => setFinalText(openAiQualityText)}
                disabled={!openAiQualityText}
              >
                gpt-4o 결과 사용
              </button>
              <button
                type="button"
                className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => setFinalText(openAiMiniText)}
                disabled={!openAiMiniText}
              >
                mini 결과 사용
              </button>
              <button
                type="button"
                className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => setFinalText(browserText)}
                disabled={!browserText}
              >
                Browser 결과 사용
              </button>
              <button
                type="button"
                className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => setFinalText(clovaText)}
                disabled={!clovaText}
              >
                CLOVA 결과 사용
              </button>
            </div>
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-4">
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="text-sm font-semibold text-slate-950">OpenAI STT 고품질</p>
              <p className="mt-1 text-xs text-slate-500">gpt-4o-transcribe</p>
              <p className="mt-3 min-h-24 whitespace-pre-wrap text-sm text-slate-700">
                {openAiQualityText || 'gpt-4o-transcribe 변환 전입니다.'}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="text-sm font-semibold text-slate-950">OpenAI STT mini</p>
              <p className="mt-1 text-xs text-slate-500">gpt-4o-mini-transcribe</p>
              <p className="mt-3 min-h-24 whitespace-pre-wrap text-sm text-slate-700">
                {openAiMiniText || 'gpt-4o-mini-transcribe 변환 전입니다.'}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="text-sm font-semibold text-slate-950">Browser STT 결과</p>
              <p className="mt-3 min-h-24 whitespace-pre-wrap text-sm text-slate-700">
                {browserText || '녹음 중 Browser STT 결과가 여기에 표시됩니다.'}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="text-sm font-semibold text-slate-950">CLOVA STT 결과</p>
              <p className="mt-3 min-h-24 whitespace-pre-wrap text-sm text-slate-700">
                {clovaText || 'CLOVA STT 변환 전입니다.'}
              </p>
            </div>
          </div>

          <label className="mt-5 block">
            <span className="text-sm font-semibold text-slate-950">최종 답변 선택 또는 수정</span>
            <textarea
              className="mt-3 h-40 w-full rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-900 outline-none transition focus:border-slate-400"
              value={finalText}
              onChange={handleFinalTextChange}
              placeholder="최종 답변으로 저장할 텍스트를 입력하거나 STT 결과를 선택하세요."
            />
          </label>

          <button
            type="button"
            className="mt-3 rounded-lg bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-700"
            onClick={handleSaveText}
          >
            최종 답변 저장
          </button>
        </section>

        <section className="mt-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-950">4. TTS 비교</h2>
          <label className="mt-4 block">
            <span className="text-sm font-semibold text-slate-950">AI 질문 텍스트</span>
            <textarea
              className="mt-3 h-24 w-full rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-900 outline-none transition focus:border-slate-400"
              value={questionText}
              onChange={(event) => setQuestionText(event.target.value)}
            />
          </label>

          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="text-sm font-semibold text-slate-950">OpenAI voice</span>
              <select
                className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-400"
                value={selectedOpenAiVoice}
                onChange={(event) => setSelectedOpenAiVoice(event.target.value)}
              >
                {OPENAI_TTS_VOICES.map((voice) => (
                  <option key={voice} value={voice}>
                    {voice}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-sm font-semibold text-slate-950">Browser voice</span>
              <select
                className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-400 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                value={selectedBrowserVoiceKey}
                onChange={(event) => setSelectedBrowserVoiceKey(event.target.value)}
                disabled={!canUseBrowserTts || sortedBrowserVoices.length === 0}
              >
                {sortedBrowserVoices.length === 0 ? (
                  <option value="">사용 가능한 브라우저 음성이 없습니다</option>
                ) : (
                  sortedBrowserVoices.map((voice) => (
                    <option key={getVoiceKey(voice)} value={getVoiceKey(voice)}>
                      {getVoiceLabel(voice)}
                    </option>
                  ))
                )}
              </select>
            </label>
          </div>

          {ttsMode === 'browser' && !canUseBrowserTts ? (
            <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
              현재 브라우저에서 브라우저 내장 TTS를 사용할 수 없습니다.
            </p>
          ) : null}
          {ttsMode === 'browser' && canUseBrowserTts && sortedBrowserVoices.length === 0 ? (
            <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
              사용 가능한 브라우저 음성을 찾을 수 없습니다.
            </p>
          ) : null}

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-lg bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={playOpenAiTts}
              disabled={!readableQuestion || ttsLoading}
            >
              {ttsLoading && lastTtsMethod === 'openai' ? '읽는 중...' : 'OpenAI TTS로 듣기'}
            </button>
            <button
              type="button"
              className="rounded-lg bg-cyan-700 px-5 py-3 text-sm font-semibold text-white transition hover:bg-cyan-600 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={playBrowserTts}
              disabled={!readableQuestion || !canUseBrowserTts || sortedBrowserVoices.length === 0}
            >
              Browser TTS로 듣기
            </button>
            <button
              type="button"
              className="rounded-lg bg-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={handlePlaySelectedTts}
              disabled={
                !readableQuestion ||
                ttsLoading ||
                (ttsMode === 'browser' && (!canUseBrowserTts || sortedBrowserVoices.length === 0))
              }
            >
              선택 방식으로 듣기
            </button>
            <button
              type="button"
              className="rounded-lg bg-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={handleReplayTts}
              disabled={
                !readableQuestion ||
                ttsLoading ||
                (lastTtsMethod === 'browser' && (!canUseBrowserTts || sortedBrowserVoices.length === 0))
              }
            >
              다시 듣기
            </button>
          </div>

          {ttsError ? <div className="mt-4 rounded-lg bg-rose-50 p-4 text-sm text-rose-700">{ttsError}</div> : null}
          {ttsAudioUrl ? (
            <div className="mt-4 rounded-lg bg-slate-50 p-4">
              <p className="text-sm font-semibold text-slate-900">OpenAI TTS 미리듣기</p>
              <audio className="mt-3 w-full" controls src={ttsAudioUrl} />
            </div>
          ) : null}
        </section>

        <section className="mt-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-950">5. 비교 요약</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="font-semibold text-slate-950">OpenAI STT</p>
              <dl className="mt-3 space-y-2 text-sm text-slate-700">
                <div><dt className="font-semibold text-slate-900">처리 방식</dt><dd>서버 API 기반</dd></div>
                <div><dt className="font-semibold text-slate-900">비용 여부</dt><dd>비용 발생</dd></div>
                <div><dt className="font-semibold text-slate-900">장점</dt><dd>녹음 파일 기준으로 재처리 가능, 정확도와 안정성 우선</dd></div>
                <div><dt className="font-semibold text-slate-900">주의점</dt><dd>백엔드 OpenAI API 키와 네트워크 요청 필요</dd></div>
              </dl>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="font-semibold text-slate-950">Browser STT</p>
              <dl className="mt-3 space-y-2 text-sm text-slate-700">
                <div><dt className="font-semibold text-slate-900">처리 방식</dt><dd>브라우저 내장 기능</dd></div>
                <div><dt className="font-semibold text-slate-900">비용 여부</dt><dd>별도 API 비용 없음</dd></div>
                <div><dt className="font-semibold text-slate-900">장점</dt><dd>프론트엔드에서 바로 실행, API 키 불필요</dd></div>
                <div><dt className="font-semibold text-slate-900">주의점</dt><dd>Chrome 환경 의존, 녹음 파일 저장 흐름과 STT 인식 흐름이 분리됨</dd></div>
              </dl>
            </div>
          </div>
        </section>

        <section className="mt-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-950">카메라 연결 확인</h2>
              <p className="mt-2 text-sm text-slate-600">기존 테스트용 카메라 미리보기 기능입니다.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-lg bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-700"
                onClick={requestCamera}
              >
                카메라 권한 요청
              </button>
              <button
                type="button"
                className="rounded-lg bg-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={stopCamera}
                disabled={!cameraEnabled}
              >
                카메라 종료
              </button>
            </div>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-2">
            <div className="rounded-lg bg-slate-50 p-4">
              <p className="text-sm text-slate-500">카메라 상태</p>
              <p className="mt-2 font-semibold text-slate-900">
                {cameraPermission === 'idle'
                  ? '대기 중'
                  : cameraPermission === 'granted'
                    ? '허용됨'
                    : cameraPermission === 'denied'
                      ? '거부됨'
                      : '미지원'}
              </p>
            </div>
            <div className="rounded-lg bg-slate-50 p-4">
              <p className="text-sm text-slate-500">카메라 메시지</p>
              <p className="mt-2 font-semibold text-slate-900">{cameraStatus}</p>
            </div>
          </div>

          {cameraDeviceCount !== null ? (
            <p className="mt-4 text-sm text-slate-500">감지된 카메라 장치 수: {cameraDeviceCount}</p>
          ) : null}
          {cameraError ? <p className="mt-4 rounded-lg bg-rose-50 p-4 text-sm text-rose-700">{cameraError}</p> : null}
          {hasCamera ? (
            <video ref={videoRef} className="mt-5 h-72 w-full rounded-lg bg-slate-950 object-cover" autoPlay muted playsInline />
          ) : null}
        </section>
      </div>
    </div>
  );
}

export default App;
