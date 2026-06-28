import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';

type PermissionState = 'idle' | 'granted' | 'denied' | 'unsupported';
type SttMode = 'quality' | 'mini' | 'whisper' | 'browser' | 'clova';
type TtsMode = 'openai' | 'browser';
type MicInputStatus = 'none' | 'low' | 'normal';
type QuestionType = 'technical' | 'general';

type WhisperWordTimestamp = {
  word: string;
  start: number;
  end: number;
};

type OpenAiSttResult = {
  text: string;
  words?: WhisperWordTimestamp[];
  duration?: number;
};

type SilenceSegment = {
  start: number;
  end: number;
  duration: number;
};

type SpeechSegment = SilenceSegment;

type VadAnalysisResult = {
  audioDuration: number;
  firstSpeechStartSec: number | null;
  trailingSilenceSec: number;
  actualSpeechDuration: number;
  totalPauseDuration: number;
  pauseCount: number;
  longPauseCount: number;
  speechSegments: SpeechSegment[];
  silenceSegments: SilenceSegment[];
  settings: {
    frameMs: number;
    threshold: number;
    minSpeechSec: number;
    mergeGapSec: number;
    minPauseSec: number;
    longPauseSec: number;
  };
};

type TechnicalCorrectionResult = {
  questionType: QuestionType;
  normalizedText: string;
  replacements: Array<{
    before: string;
    after: string;
  }>;
  warnings: string[];
  fallback: boolean;
  skipped: boolean;
  model: string | null;
  processingMs: number;
};

type ComparisonResult = {
  questionType: QuestionType;
  technicalCorrection: TechnicalCorrectionResult;
  whisper: {
    text: string;
    sttMs: number;
    totalMs: number;
    audioDuration: number;
    words: Array<WhisperWordTimestamp & { duration: number; gapToNext: number }>;
    totalPauseDuration: number;
    pauseCount: number;
    longPauseCount: number;
    fillers: Record<string, number>;
  };
  gpt4oVad: {
    text: string;
    sttMs: number;
    vadMs: number;
    totalMs: number;
    audioDuration: number;
    firstSpeechStartSec: number | null;
    trailingSilenceSec: number;
    actualSpeechDuration: number;
    totalPauseDuration: number;
    pauseCount: number;
    longPauseCount: number;
    speechSegments: SpeechSegment[];
    silenceSegments: SilenceSegment[];
    fillers: Record<string, number>;
    settings: VadAnalysisResult['settings'];
  };
};

type AnalysisMethod = 'whisper_timestamp' | 'gpt4o_vad';

type FillerPosition = {
  word: string;
  start: number;
  end: number;
  index: number;
};

type NormalizedVoiceAnalysisPayload = {
  session_id: string | null;
  question_id: string | null;
  audio_url: string | null;
  question_ended_at: string | null;
  answer_started_at: string | null;
  answer_ended_at: string | null;
  question_to_first_speech_sec: number | null;
  stt_text: string;
  audio_duration_sec: number;
  analysis_method: AnalysisMethod;
  first_speech_start_sec: number | null;
  speech_duration_sec: number | null;
  total_pause_duration_sec: number;
  pause_count: number;
  long_pause_count: number;
  speech_segments: SpeechSegment[];
  silence_segments: SilenceSegment[];
  trailing_silence_sec: number | null;
  filler_words: {
    counts: Record<string, number>;
    positions: FillerPosition[] | null;
  };
  processing_time_ms: {
    stt: number;
    analysis: number | null;
    total: number;
  };
  whisper_words?: Array<WhisperWordTimestamp & { duration: number; gapToNext: number }>;
  vad?: {
    settings: VadAnalysisResult['settings'];
  };
};

const OPENAI_STT_QUALITY_MODEL = 'gpt-4o-transcribe';
const OPENAI_STT_MINI_MODEL = 'gpt-4o-mini-transcribe';
const OPENAI_STT_WHISPER_MODEL = 'whisper-1';
const VAD_SETTINGS = {
  frameMs: 20,
  minSpeechSec: 0.15,
  mergeGapSec: 0.18,
  minPauseSec: 0.5,
  longPauseSec: 3
};
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

const microphoneConstraints: MediaTrackConstraints = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
  channelCount: 1
};

const getAudioConstraints = (deviceId = ''): MediaStreamConstraints => ({
  audio: {
    ...microphoneConstraints,
    ...(deviceId ? { deviceId: { exact: deviceId } } : {})
  }
});

const formatSeconds = (seconds: number) => `${seconds.toFixed(2)}초`;
const formatMilliseconds = (milliseconds: number) => `${(milliseconds / 1000).toFixed(2)}초`;

const getFillerCounts = (text: string) => {
  const fillerWords = ['음', '어', '아'];
  return fillerWords.reduce<Record<string, number>>((counts, filler) => {
    const matches = text.match(new RegExp(filler, 'g'));
    counts[filler] = matches?.length ?? 0;
    return counts;
  }, {});
};

const getTotalFillerCount = (fillers: Record<string, number>) =>
  Object.values(fillers).reduce((sum, count) => sum + count, 0);

const getFillerPositionsFromWords = (words: Array<WhisperWordTimestamp & { duration: number; gapToNext: number }>) =>
  words.reduce<FillerPosition[]>((positions, item, index) => {
    const normalizedWord = item.word.trim();
    if (['음', '어', '아'].includes(normalizedWord)) {
      positions.push({
        word: normalizedWord,
        start: item.start,
        end: item.end,
        index
      });
    }
    return positions;
  }, []);

const getQuestionToFirstSpeechSec = (
  questionEndedAt: string | null,
  answerStartedAt: string | null,
  firstSpeechStartSec: number | null
) => {
  if (!questionEndedAt || !answerStartedAt || firstSpeechStartSec === null) {
    return null;
  }

  const questionEndedMs = Date.parse(questionEndedAt);
  const answerStartedMs = Date.parse(answerStartedAt);
  if (Number.isNaN(questionEndedMs) || Number.isNaN(answerStartedMs)) {
    return null;
  }

  return Math.max(0, (answerStartedMs - questionEndedMs) / 1000 + firstSpeechStartSec);
};

const buildWhisperTimestampPayload = ({
  result,
  questionEndedAt,
  answerStartedAt,
  answerEndedAt
}: {
  result: ComparisonResult['whisper'];
  questionEndedAt: string | null;
  answerStartedAt: string | null;
  answerEndedAt: string | null;
}): NormalizedVoiceAnalysisPayload => {
  const firstWord = result.words[0] ?? null;

  return {
    session_id: null,
    question_id: null,
    audio_url: null,
    question_ended_at: questionEndedAt,
    answer_started_at: answerStartedAt,
    answer_ended_at: answerEndedAt,
    question_to_first_speech_sec: getQuestionToFirstSpeechSec(questionEndedAt, answerStartedAt, firstWord?.start ?? null),
    stt_text: result.text,
    audio_duration_sec: result.audioDuration,
    analysis_method: 'whisper_timestamp',
    first_speech_start_sec: firstWord?.start ?? null,
    speech_duration_sec: null,
    total_pause_duration_sec: result.totalPauseDuration,
    pause_count: result.pauseCount,
    long_pause_count: result.longPauseCount,
    speech_segments: [],
    silence_segments: [],
    trailing_silence_sec: null,
    filler_words: {
      counts: result.fillers,
      positions: getFillerPositionsFromWords(result.words)
    },
    processing_time_ms: {
      stt: result.sttMs,
      analysis: null,
      total: result.totalMs
    },
    whisper_words: result.words
  };
};

const buildGpt4oVadPayload = ({
  result,
  questionEndedAt,
  answerStartedAt,
  answerEndedAt
}: {
  result: ComparisonResult['gpt4oVad'];
  questionEndedAt: string | null;
  answerStartedAt: string | null;
  answerEndedAt: string | null;
}): NormalizedVoiceAnalysisPayload => ({
  session_id: null,
  question_id: null,
  audio_url: null,
  question_ended_at: questionEndedAt,
  answer_started_at: answerStartedAt,
  answer_ended_at: answerEndedAt,
  question_to_first_speech_sec: getQuestionToFirstSpeechSec(questionEndedAt, answerStartedAt, result.firstSpeechStartSec),
  stt_text: result.text,
  audio_duration_sec: result.audioDuration,
  analysis_method: 'gpt4o_vad',
  first_speech_start_sec: result.firstSpeechStartSec,
  speech_duration_sec: result.actualSpeechDuration,
  total_pause_duration_sec: result.totalPauseDuration,
  pause_count: result.pauseCount,
  long_pause_count: result.longPauseCount,
  speech_segments: result.speechSegments,
  silence_segments: result.silenceSegments,
  trailing_silence_sec: result.trailingSilenceSec,
  filler_words: {
    counts: result.fillers,
    positions: null
  },
  processing_time_ms: {
    stt: result.sttMs,
    analysis: result.vadMs,
    total: result.totalMs
  },
  vad: {
    settings: result.settings
  }
});

const getMicPermissionLabel = (permission: PermissionState) => {
  if (permission === 'granted') {
    return '허용됨';
  }
  if (permission === 'denied') {
    return '거부됨';
  }
  if (permission === 'unsupported') {
    return '마이크 장치 없음';
  }
  return '확인 중';
};

const getMicInputLabel = (status: MicInputStatus) => {
  if (status === 'normal') {
    return '정상';
  }
  if (status === 'low') {
    return '음량이 너무 작음';
  }
  return '입력 없음';
};

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
  const [micLevel, setMicLevel] = useState(0);
  const [micInputStatus, setMicInputStatus] = useState<MicInputStatus>('none');
  const [audioInputDevices, setAudioInputDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedAudioInputId, setSelectedAudioInputId] = useState('');
  const [micTestActive, setMicTestActive] = useState(false);
  const [micReadyForInterview, setMicReadyForInterview] = useState(false);
  const [interviewStartMessage, setInterviewStartMessage] = useState('');
  const [sttMode, setSttMode] = useState<SttMode>('quality');
  const [ttsMode, setTtsMode] = useState<TtsMode>('openai');
  const [openAiQualityText, setOpenAiQualityText] = useState('');
  const [openAiMiniText, setOpenAiMiniText] = useState('');
  const [openAiWhisperText, setOpenAiWhisperText] = useState('');
  const [whisperWords, setWhisperWords] = useState<WhisperWordTimestamp[]>([]);
  const [whisperDuration, setWhisperDuration] = useState<number | null>(null);
  const [activeTimestampSource, setActiveTimestampSource] = useState<'whisper' | null>(null);
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
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [comparisonResult, setComparisonResult] = useState<ComparisonResult | null>(null);
  const [questionType, setQuestionType] = useState<QuestionType>('technical');
  const [questionEndedAt] = useState<string | null>(null);
  const [answerStartedAt, setAnswerStartedAt] = useState<string | null>(null);
  const [answerEndedAt, setAnswerEndedAt] = useState<string | null>(null);
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
  const voiceTestSectionRef = useRef<HTMLElement | null>(null);
  const waveformCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const browserFinalTranscriptRef = useRef('');
  const smoothedMicLevelRef = useRef(0);
  const micStatusRef = useRef<MicInputStatus>('none');
  const micStatusHoldUntilRef = useRef(0);
  const micReadyStartedAtRef = useRef<number | null>(null);

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
  const whisperTimestampRows = useMemo(
    () =>
      whisperWords.map((item, index) => {
        const nextWord = whisperWords[index + 1];
        const gapToNext = nextWord ? Math.max(0, nextWord.start - item.end) : 0;
        return {
          ...item,
          duration: Math.max(0, item.end - item.start),
          gapToNext
        };
      }),
    [whisperWords]
  );
  const whisperTimestampSummary = useMemo(() => {
    const totalGap = whisperTimestampRows.reduce((sum, item) => sum + item.gapToNext, 0);
    const longGapCount = whisperTimestampRows.filter((item) => item.gapToNext >= 3).length;
    const fallbackDuration =
      whisperWords.length > 0 ? Math.max(0, whisperWords[whisperWords.length - 1].end - whisperWords[0].start) : 0;

    return {
      answerDuration: whisperDuration ?? fallbackDuration,
      totalGap,
      longGapCount
    };
  }, [whisperDuration, whisperTimestampRows, whisperWords]);
  const showWhisperTimestamps = activeTimestampSource === 'whisper' && whisperTimestampRows.length > 0;
  const canStartInterview = micReadyForInterview;
  const normalizedAnalysisPayloads = useMemo(() => {
    if (!comparisonResult) {
      return null;
    }

    return {
      question_type: comparisonResult.questionType,
      technical_term_correction: comparisonResult.technicalCorrection,
      whisper_timestamp: buildWhisperTimestampPayload({
        result: comparisonResult.whisper,
        questionEndedAt,
        answerStartedAt,
        answerEndedAt
      }),
      gpt4o_vad: buildGpt4oVadPayload({
        result: comparisonResult.gpt4oVad,
        questionEndedAt,
        answerStartedAt,
        answerEndedAt
      })
    };
  }, [answerEndedAt, answerStartedAt, comparisonResult, questionEndedAt]);

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

  const loadAudioInputDevices = async () => {
    if (!navigator.mediaDevices?.enumerateDevices) {
      return;
    }

    const devices = await navigator.mediaDevices.enumerateDevices();
    const audioInputs = devices.filter((device) => device.kind === 'audioinput');
    setAudioInputDevices(audioInputs);
    setSelectedAudioInputId((current) => {
      if (current && audioInputs.some((device) => device.deviceId === current)) {
        return current;
      }
      return audioInputs[0]?.deviceId ?? '';
    });
  };

  const requestMicrophonePermission = async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setPermission('unsupported');
      setStatusMessage('현재 브라우저에서 마이크 기능을 지원하지 않습니다. Chrome에서 실행해 주세요.');
      setError('현재 브라우저에서 마이크 기능을 지원하지 않습니다.');
      return;
    }

    try {
      const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      permissionStream.getTracks().forEach((track) => track.stop());
      setPermission('granted');
      setStatusMessage('마이크 권한이 허용되었습니다. 입력 장치를 선택한 뒤 테스트를 시작하세요.');
      setError(null);
      await loadAudioInputDevices();
    } catch (err) {
      const errorName = err instanceof DOMException ? err.name : 'UnknownError';
      if (errorName === 'NotFoundError' || errorName === 'DevicesNotFoundError') {
        setPermission('unsupported');
        setStatusMessage('마이크 장치를 찾을 수 없습니다. 장치 연결 상태를 확인해 주세요.');
        setError('마이크 장치가 감지되지 않았습니다.');
      } else {
        setPermission('denied');
        setStatusMessage('마이크 권한이 필요합니다. 브라우저 권한 요청을 허용해 주세요.');
        setError('마이크 권한을 사용할 수 없습니다.');
      }
      setMicLevel(0);
      setMicInputStatus('none');
      setMicTestActive(false);
      setMicReadyForInterview(false);
      micReadyStartedAtRef.current = null;
    }
  };

  const startMicrophoneTest = async () => {
    if (permission !== 'granted') {
      await requestMicrophonePermission();
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setPermission('unsupported');
      setStatusMessage('현재 브라우저에서 마이크 기능을 지원하지 않습니다. Chrome에서 실행해 주세요.');
      setError('현재 브라우저에서 마이크 기능을 지원하지 않습니다.');
      return;
    }

    try {
      stopWaveform();
      if (mediaStream) {
        mediaStream.getTracks().forEach((track) => track.stop());
      }

      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia(getAudioConstraints(selectedAudioInputId));
      } catch {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      }

      setMediaStream(stream);
      setPermission('granted');
      setMicTestActive(true);
      setMicLevel(0);
      setMicInputStatus('none');
      setMicReadyForInterview(false);
      smoothedMicLevelRef.current = 0;
      micStatusRef.current = 'none';
      micStatusHoldUntilRef.current = 0;
      micReadyStartedAtRef.current = null;
      setStatusMessage('마이크 테스트 중입니다. 평소 답변하듯 2~3초 정도 말해 보세요.');
      setError(null);
      await loadAudioInputDevices();
      await startWaveform(stream);
    } catch (err) {
      const errorName = err instanceof DOMException ? err.name : 'UnknownError';
      if (errorName === 'NotFoundError' || errorName === 'DevicesNotFoundError') {
        setPermission('unsupported');
        setStatusMessage('마이크 장치를 찾을 수 없습니다. 장치 연결 상태를 확인해 주세요.');
        setError('마이크 장치가 감지되지 않았습니다.');
      } else {
        setPermission('denied');
        setStatusMessage('마이크 권한이 필요합니다. 브라우저 권한 요청을 허용해 주세요.');
        setError('마이크 권한을 사용할 수 없습니다.');
      }
      setMicTestActive(false);
      setMicLevel(0);
      setMicInputStatus('none');
      setMicReadyForInterview(false);
      micReadyStartedAtRef.current = null;
    }
  };

  const requestMicrophone = async (): Promise<MediaStream | null> => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setPermission('unsupported');
      setStatusMessage('현재 브라우저에서 마이크 기능을 지원하지 않습니다. Chrome에서 실행해 주세요.');
      return null;
    }

    try {
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia(getAudioConstraints(selectedAudioInputId));
      } catch {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
      const audioSettings = stream.getAudioTracks()[0]?.getSettings();
      const appliedSettings = [
        audioSettings?.sampleRate ? `${audioSettings.sampleRate}Hz` : null,
        audioSettings?.channelCount ? `${audioSettings.channelCount}ch` : null
      ]
        .filter(Boolean)
        .join(', ');
      setMediaStream(stream);
      setPermission('granted');
      setStatusMessage(`마이크 연결 성공. 노이즈 억제/에코 제거 옵션을 요청했습니다.${appliedSettings ? ` (${appliedSettings})` : ''}`);
      setError(null);
      await startWaveform(stream);
      return stream;
    } catch (err) {
      const errorName = err instanceof DOMException ? err.name : 'UnknownError';
      if (errorName === 'NotFoundError' || errorName === 'DevicesNotFoundError') {
        setPermission('unsupported');
        setStatusMessage('마이크 장치를 찾을 수 없습니다. 장치 연결 상태를 확인해 주세요.');
        setError('마이크 장치가 감지되지 않았습니다.');
      } else {
        setPermission('denied');
        setStatusMessage('마이크 권한이 필요합니다. 브라우저 권한 요청을 허용해 주세요.');
        setError('마이크 권한을 사용할 수 없습니다.');
      }
      setMicLevel(0);
      setMicInputStatus('none');
      setMicReadyForInterview(false);
      micReadyStartedAtRef.current = null;
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
      setOpenAiWhisperText('');
      setWhisperWords([]);
      setWhisperDuration(null);
      setActiveTimestampSource(null);
      setBrowserText('');
      setClovaText('');
      setFinalText('');
      setSttError(null);
      setBrowserSttError(null);
      setComparisonError(null);
      setComparisonResult(null);
      setAnswerStartedAt(null);
      setAnswerEndedAt(null);

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
      setAnswerStartedAt(new Date().toISOString());
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

    setAnswerEndedAt(new Date().toISOString());
    stopBrowserRecognition();
    setRecording(false);
    setStatusMessage('녹음이 중지되었습니다. 아래에서 재생하고 STT 결과를 비교하세요.');
    stopWaveform();
  };

  const requestOpenAiStt = async (model: string): Promise<OpenAiSttResult> => {
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
    return {
      text: typeof data.text === 'string' ? data.text : '',
      duration: typeof data.duration === 'number' ? data.duration : undefined,
      words: Array.isArray(data.words)
        ? data.words
            .map((item: Partial<WhisperWordTimestamp>) => ({
              word: typeof item.word === 'string' ? item.word : '',
              start: typeof item.start === 'number' ? item.start : 0,
              end: typeof item.end === 'number' ? item.end : 0
            }))
            .filter((item: WhisperWordTimestamp) => item.word)
        : []
    };
  };

  const requestTechnicalTermCorrection = async (
    text: string,
    currentQuestionType: QuestionType
  ): Promise<TechnicalCorrectionResult> => {
    const startedAt = performance.now();

    try {
      const response = await fetch('/api/normalize-technical-terms', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          text,
          questionType: currentQuestionType
        })
      });

      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }

      const data = await response.json();
      const replacements = Array.isArray(data.replacements)
        ? data.replacements
            .map((item: { before?: unknown; after?: unknown }) => ({
              before: typeof item.before === 'string' ? item.before : '',
              after: typeof item.after === 'string' ? item.after : ''
            }))
            .filter((item: { before: string; after: string }) => item.before || item.after)
        : [];

      return {
        questionType: data.question_type === 'technical' ? 'technical' : 'general',
        normalizedText: typeof data.normalized_text === 'string' ? data.normalized_text : text,
        replacements,
        warnings: Array.isArray(data.warnings)
          ? data.warnings.filter((item: unknown): item is string => typeof item === 'string')
          : [],
        fallback: Boolean(data.fallback),
        skipped: Boolean(data.skipped),
        model: typeof data.model === 'string' ? data.model : null,
        processingMs:
          typeof data.processing_time_ms === 'number'
            ? data.processing_time_ms
            : performance.now() - startedAt
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown correction error';
      return {
        questionType: currentQuestionType,
        normalizedText: text,
        replacements: [],
        warnings: [`Correction fallback: ${message}`],
        fallback: true,
        skipped: false,
        model: null,
        processingMs: performance.now() - startedAt
      };
    }
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

  const analyzeVadFromBlob = async (audioBlob: Blob): Promise<VadAnalysisResult> => {
    const arrayBuffer = await audioBlob.arrayBuffer();
    const audioContext = new AudioContext();

    try {
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer.slice(0));
      const sampleRate = audioBuffer.sampleRate;
      const frameSize = Math.max(1, Math.floor(sampleRate * (VAD_SETTINGS.frameMs / 1000)));
      const channelData = audioBuffer.getChannelData(0);
      const frames: Array<{ start: number; end: number; rms: number }> = [];

      for (let offset = 0; offset < channelData.length; offset += frameSize) {
        const endOffset = Math.min(channelData.length, offset + frameSize);
        let sumSquares = 0;
        for (let index = offset; index < endOffset; index += 1) {
          sumSquares += channelData[index] * channelData[index];
        }
        const rms = Math.sqrt(sumSquares / Math.max(1, endOffset - offset));
        frames.push({
          start: offset / sampleRate,
          end: endOffset / sampleRate,
          rms
        });
      }

      const sortedRms = frames.map((frame) => frame.rms).sort((a, b) => a - b);
      const percentile = (ratio: number) => sortedRms[Math.min(sortedRms.length - 1, Math.floor(sortedRms.length * ratio))] ?? 0;
      const noiseFloor = percentile(0.2);
      const activeLevel = percentile(0.9);
      const threshold = Math.max(noiseFloor * 2.5, noiseFloor + (activeLevel - noiseFloor) * 0.28, 0.005);
      const speechFrames = frames.map((frame) => ({ ...frame, speech: frame.rms >= threshold }));
      const speechSegments: SilenceSegment[] = [];
      let currentSpeechStart: number | null = null;
      let currentSpeechEnd = 0;

      speechFrames.forEach((frame) => {
        if (frame.speech) {
          currentSpeechStart ??= frame.start;
          currentSpeechEnd = frame.end;
          return;
        }

        if (currentSpeechStart !== null) {
          speechSegments.push({
            start: currentSpeechStart,
            end: currentSpeechEnd,
            duration: currentSpeechEnd - currentSpeechStart
          });
          currentSpeechStart = null;
        }
      });

      if (currentSpeechStart !== null) {
        speechSegments.push({
          start: currentSpeechStart,
          end: currentSpeechEnd,
          duration: currentSpeechEnd - currentSpeechStart
        });
      }

      const mergedSpeechSegments = speechSegments.reduce<SilenceSegment[]>((segments, segment) => {
        const previous = segments[segments.length - 1];
        if (previous && segment.start - previous.end < VAD_SETTINGS.mergeGapSec) {
          previous.end = segment.end;
          previous.duration = previous.end - previous.start;
          return segments;
        }
        segments.push({ ...segment });
        return segments;
      }, []).filter((segment) => segment.duration >= VAD_SETTINGS.minSpeechSec);

      const silenceSegments: SilenceSegment[] = [];
      for (let index = 0; index < mergedSpeechSegments.length - 1; index += 1) {
        const current = mergedSpeechSegments[index];
        const next = mergedSpeechSegments[index + 1];
        const duration = next.start - current.end;
        if (duration >= VAD_SETTINGS.minPauseSec) {
          silenceSegments.push({
            start: current.end,
            end: next.start,
            duration
          });
        }
      }

      const actualSpeechDuration = mergedSpeechSegments.reduce((sum, segment) => sum + segment.duration, 0);
      const totalPauseDuration = silenceSegments.reduce((sum, segment) => sum + segment.duration, 0);
      const firstSpeechStartSec = mergedSpeechSegments[0]?.start ?? null;
      const lastSpeechEnd = mergedSpeechSegments[mergedSpeechSegments.length - 1]?.end ?? null;
      const trailingSilenceSec = lastSpeechEnd === null ? 0 : Math.max(0, audioBuffer.duration - lastSpeechEnd);

      return {
        audioDuration: audioBuffer.duration,
        firstSpeechStartSec,
        trailingSilenceSec,
        actualSpeechDuration,
        totalPauseDuration,
        pauseCount: silenceSegments.length,
        longPauseCount: silenceSegments.filter((segment) => segment.duration >= VAD_SETTINGS.longPauseSec).length,
        speechSegments: mergedSpeechSegments,
        silenceSegments,
        settings: {
          ...VAD_SETTINGS,
          threshold
        }
      };
    } finally {
      await audioContext.close();
    }
  };

  const handleRunComparison = async () => {
    if (!recordedBlob) {
      setComparisonError('녹음 파일이 없습니다. 먼저 녹음을 진행하세요.');
      return;
    }

    setComparisonLoading(true);
    setComparisonError(null);

    try {
      const selectedQuestionType = questionType;
      const whisperTotalStart = performance.now();
      const whisperSttStart = performance.now();
      const whisperResult = await requestOpenAiStt(OPENAI_STT_WHISPER_MODEL);
      const whisperSttMs = performance.now() - whisperSttStart;
      const whisperWordsForDisplay = (whisperResult.words ?? []).map((item, index, words) => {
        const nextWord = words[index + 1];
        const gapToNext = nextWord ? Math.max(0, nextWord.start - item.end) : 0;
        return {
          ...item,
          duration: Math.max(0, item.end - item.start),
          gapToNext
        };
      });
      const whisperTotalMs = performance.now() - whisperTotalStart;
      const technicalCorrection = await requestTechnicalTermCorrection(whisperResult.text, selectedQuestionType);

      const gptTotalStart = performance.now();
      const gptSttPromise = (async () => {
        const gptSttStart = performance.now();
        const result = await requestOpenAiStt(OPENAI_STT_QUALITY_MODEL);
        return {
          result,
          ms: performance.now() - gptSttStart
        };
      })();
      const vadPromise = (async () => {
        const vadStart = performance.now();
        const result = await analyzeVadFromBlob(recordedBlob);
        return {
          result,
          ms: performance.now() - vadStart
        };
      })();
      const [{ result: gptResult, ms: gptSttMs }, { result: vadResult, ms: vadMs }] = await Promise.all([
        gptSttPromise,
        vadPromise
      ]);
      const gptTotalMs = performance.now() - gptTotalStart;

      const whisperPauseRows = whisperWordsForDisplay.slice(0, -1).filter((item) => item.gapToNext >= 0.5);
      setComparisonResult({
        questionType: selectedQuestionType,
        technicalCorrection,
        whisper: {
          text: whisperResult.text,
          sttMs: whisperSttMs,
          totalMs: whisperTotalMs,
          audioDuration: whisperResult.duration ?? vadResult.audioDuration,
          words: whisperWordsForDisplay,
          totalPauseDuration: whisperPauseRows.reduce((sum, item) => sum + item.gapToNext, 0),
          pauseCount: whisperPauseRows.length,
          longPauseCount: whisperPauseRows.filter((item) => item.gapToNext >= 3).length,
          fillers: getFillerCounts(whisperResult.text)
        },
        gpt4oVad: {
          text: gptResult.text,
          sttMs: gptSttMs,
          vadMs,
          totalMs: gptTotalMs,
          audioDuration: vadResult.audioDuration,
          firstSpeechStartSec: vadResult.firstSpeechStartSec,
          trailingSilenceSec: vadResult.trailingSilenceSec,
          actualSpeechDuration: vadResult.actualSpeechDuration,
          totalPauseDuration: vadResult.totalPauseDuration,
          pauseCount: vadResult.pauseCount,
          longPauseCount: vadResult.longPauseCount,
          speechSegments: vadResult.speechSegments,
          silenceSegments: vadResult.silenceSegments,
          fillers: getFillerCounts(gptResult.text),
          settings: vadResult.settings
        }
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : '알 수 없는 오류';
      setComparisonError(`비교 실행 실패: ${message}`);
    } finally {
      setComparisonLoading(false);
    }
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
        setActiveTimestampSource(null);
        setStatusMessage('브라우저 STT 결과를 최종 답변으로 가져왔습니다.');
        return;
      }

      if (sttMode === 'clova') {
        const clovaResult = await requestClovaStt();
        setClovaText(clovaResult);
        setFinalText(clovaResult || browserText);
        setActiveTimestampSource(null);
        setStatusMessage('CLOVA STT 변환이 완료되었습니다.');
        return;
      }

      const model =
        sttMode === 'quality'
          ? OPENAI_STT_QUALITY_MODEL
          : sttMode === 'mini'
            ? OPENAI_STT_MINI_MODEL
            : OPENAI_STT_WHISPER_MODEL;
      const openAiResult = await requestOpenAiStt(model);

      if (sttMode === 'quality') {
        setOpenAiQualityText(openAiResult.text);
        setActiveTimestampSource(null);
      } else if (sttMode === 'mini') {
        setOpenAiMiniText(openAiResult.text);
        setActiveTimestampSource(null);
      } else {
        setOpenAiWhisperText(openAiResult.text);
        setWhisperWords(openAiResult.words ?? []);
        setWhisperDuration(openAiResult.duration ?? null);
        setActiveTimestampSource('whisper');
      }

      setFinalText(openAiResult.text || browserText);
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

  const handleStartInterview = () => {
    if (!canStartInterview) {
      setInterviewStartMessage('마이크 입력이 정상으로 확인되면 면접을 시작할 수 있습니다.');
      return;
    }

    setInterviewStartMessage('세션 생성 API가 아직 없어 현재 POC 음성 면접 테스트 화면으로 이동합니다.');
    voiceTestSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
    setOpenAiWhisperText('');
    setWhisperWords([]);
    setWhisperDuration(null);
    setActiveTimestampSource(null);
    setBrowserText('');
    setClovaText('');
    setFinalText('');
    setSttError(null);
    setBrowserSttError(null);
    setTtsError(null);
    setComparisonError(null);
    setComparisonResult(null);
    setAnswerStartedAt(null);
    setAnswerEndedAt(null);
    setTtsAudioUrl((previousUrl) => {
      if (previousUrl) {
        URL.revokeObjectURL(previousUrl);
      }
      return null;
    });
    setTimer(0);
    setRecording(false);
    setMicReadyForInterview(false);
    micReadyStartedAtRef.current = null;
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
    const averageLevel =
      dataArray.reduce((sum, value) => sum + Math.abs(value - 128), 0) / dataArray.length / 128;
    const normalizedLevel = Math.min(1, averageLevel * 5);
    const smoothedLevel = smoothedMicLevelRef.current * 0.82 + normalizedLevel * 0.18;
    smoothedMicLevelRef.current = smoothedLevel;
    setMicLevel(smoothedLevel);

    const nextStatus: MicInputStatus = smoothedLevel > 0.16 ? 'normal' : smoothedLevel > 0.035 ? 'low' : 'none';
    const now = performance.now();
    if (!micReadyForInterview) {
      if (smoothedLevel >= 0.16) {
        micReadyStartedAtRef.current ??= now;
        if (now - micReadyStartedAtRef.current >= 1000) {
          setMicReadyForInterview(true);
          setInterviewStartMessage('마이크 입력 확인이 완료되었습니다. 면접을 시작할 수 있습니다.');
        }
      } else {
        micReadyStartedAtRef.current = null;
      }
    }

    if (nextStatus === 'normal') {
      micStatusRef.current = 'normal';
      micStatusHoldUntilRef.current = now + 1200;
    } else if (micStatusRef.current === 'normal' && now < micStatusHoldUntilRef.current) {
      // 짧은 숨 고르기나 단어 사이 공백 때문에 상태가 즉시 떨어지지 않도록 유지합니다.
    } else if (nextStatus !== micStatusRef.current) {
      micStatusRef.current = nextStatus;
      micStatusHoldUntilRef.current = nextStatus === 'low' ? now + 800 : 0;
    }
    setMicInputStatus(micStatusRef.current);

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
    <div className="min-h-screen bg-[#eeeeee] px-4 py-10 text-[#000000]">
      <div className="mx-auto w-full max-w-5xl">
        <header className="rounded-lg bg-[#253900] p-6 text-white shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#08CB00] text-lg font-bold text-white">C</div>
            <div>
              <p className="text-sm font-semibold text-[#08CB00]">CareerZip</p>
              <h1 className="text-3xl font-semibold">면접 준비</h1>
            </div>
          </div>
          <p className="mt-4 max-w-2xl text-sm text-[#eeeeee]">
            면접을 시작하기 전에 마이크 권한과 입력 상태를 확인합니다. 실제 답변 녹음과 면접 기록 저장은 면접 시작 이후에만 진행됩니다.
          </p>
        </header>

        <section className="mt-6 rounded-lg border border-[#c8f5c8] bg-white p-6 shadow-sm">
          <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <div>
              <p className="text-sm font-semibold text-[#08CB00]">STEP 01</p>
              <h2 className="mt-2 text-2xl font-bold text-[#000000]">마이크 입력 확인</h2>
              <p className="mt-3 text-sm text-slate-600">
                Chrome 권한 요청을 허용한 뒤 입력 장치를 선택하고 테스트를 시작해 주세요. 입력이 정상으로 잡히면 면접 시작 버튼이 활성화됩니다.
              </p>

              <label className="mt-5 block">
                <span className="text-sm font-semibold text-[#253900]">입력 장치 선택</span>
                <select
                  className="mt-2 w-full rounded-lg border border-[#c8f5c8] bg-white px-3 py-3 text-sm text-[#000000] outline-none transition focus:border-[#08CB00] disabled:cursor-not-allowed disabled:bg-[#eeeeee]"
                  value={selectedAudioInputId}
                  onChange={(event) => {
                    setSelectedAudioInputId(event.target.value);
                    setMicTestActive(false);
                    setMicLevel(0);
                    setMicInputStatus('none');
                    setMicReadyForInterview(false);
                    micReadyStartedAtRef.current = null;
                    stopWaveform();
                    if (mediaStream) {
                      mediaStream.getTracks().forEach((track) => track.stop());
                      setMediaStream(null);
                    }
                  }}
                  disabled={permission !== 'granted' || audioInputDevices.length === 0}
                >
                  {audioInputDevices.length === 0 ? (
                    <option value="">권한 요청 후 마이크 장치를 선택할 수 있습니다.</option>
                  ) : (
                    audioInputDevices.map((device, index) => (
                      <option key={device.deviceId || index} value={device.deviceId}>
                        {device.label || `마이크 ${index + 1}`}
                      </option>
                    ))
                  )}
                </select>
              </label>

              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg bg-[#eeeeee] p-4">
                  <p className="text-xs font-semibold text-slate-500">권한 상태</p>
                  <p className="mt-2 text-lg font-bold text-[#253900]">{getMicPermissionLabel(permission)}</p>
                </div>
                <div className="rounded-lg bg-[#eeeeee] p-4">
                  <p className="text-xs font-semibold text-slate-500">입력 상태</p>
                  <p className="mt-2 text-lg font-bold text-[#253900]">{getMicInputLabel(micInputStatus)}</p>
                </div>
                <div className="rounded-lg bg-[#eeeeee] p-4">
                  <p className="text-xs font-semibold text-slate-500">테스트 상태</p>
                  <p className="mt-2 text-lg font-bold text-[#253900]">
                    {micReadyForInterview ? '준비 완료' : micTestActive ? '진행 중' : '대기 중'}
                  </p>
                </div>
              </div>

              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg bg-[#eeeeee] p-4">
                  <p className="text-xs font-semibold text-slate-500">입력 레벨</p>
                  <p className="mt-2 text-lg font-bold text-[#253900]">{Math.round(micLevel * 100)}%</p>
                </div>
              </div>

              <div className="mt-5 rounded-lg bg-[#f7fff7] p-4">
                <div className="h-3 overflow-hidden rounded-full bg-[#d9ead9]">
                  <div
                    className="h-full rounded-full bg-[#08CB00] transition-all"
                    style={{ width: `${Math.round(micLevel * 100)}%` }}
                  />
                </div>
                <canvas ref={waveformCanvasRef} className="mt-4 h-32 w-full rounded-lg bg-white" width={900} height={180} />
              </div>

              {error ? (
                <div className="mt-4 rounded-lg border border-rose-100 bg-rose-50 p-4 text-sm text-rose-700">
                  <p className="font-semibold">마이크 확인이 필요합니다.</p>
                  <p className="mt-1">{error}</p>
                </div>
              ) : null}

              <div className="mt-5 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded-lg bg-[#253900] px-5 py-3 text-sm font-semibold text-white transition hover:bg-black"
                  onClick={requestMicrophonePermission}
                >
                  마이크 권한 요청
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-[#08CB00] px-5 py-3 text-sm font-semibold text-[#253900] transition hover:bg-[#f0fff0]"
                  onClick={requestMicrophonePermission}
                >
                  다시 시도
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-[#253900] px-5 py-3 text-sm font-semibold text-[#253900] transition hover:bg-[#f0fff0] disabled:cursor-not-allowed disabled:border-slate-300 disabled:text-slate-400"
                  onClick={startMicrophoneTest}
                  disabled={permission === 'unsupported'}
                >
                  테스트 시작
                </button>
                <button
                  type="button"
                  className="rounded-lg bg-[#08CB00] px-5 py-3 text-sm font-semibold text-white transition hover:brightness-95 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
                  onClick={handleStartInterview}
                  disabled={!canStartInterview}
                >
                  면접 시작
                </button>
              </div>
              {interviewStartMessage ? <p className="mt-3 text-sm text-[#253900]">{interviewStartMessage}</p> : null}
            </div>

            <div className="rounded-lg bg-[#253900] p-5 text-white">
              <p className="text-sm font-semibold text-[#08CB00]">안내</p>
              <h3 className="mt-2 text-xl font-bold">음성 답변 기록 안내</h3>
              <ul className="mt-4 space-y-3 text-sm text-[#eeeeee]">
                <li>마이크 테스트 단계에서는 녹음 파일을 서버나 DB에 저장하지 않습니다.</li>
                <li>면접 시작 후 답변 녹음이 진행되며, 면접 기록 저장 흐름에 연결됩니다.</li>
                <li>주변 소음을 줄이고 마이크를 일정한 거리에 두면 STT 결과가 더 안정적입니다.</li>
              </ul>
            </div>
          </div>
        </section>

        <section ref={voiceTestSectionRef} className="mt-8 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">음성 비교 테스트 설정</h2>
            <p className="mt-2 text-sm text-slate-600">아래 영역은 기존 STT/TTS 비교 POC입니다.</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h2 className="text-lg font-semibold text-slate-950">STT 방식 선택</h2>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                {[
                  ['quality', 'gpt-4o STT'],
                  ['mini', 'gpt-4o mini STT'],
                  ['whisper', 'whisper-1 STT'],
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

          <div className="mt-5 rounded-lg border border-emerald-100 bg-emerald-50 p-4 text-sm text-emerald-900">
            <p className="font-semibold">녹음 품질 안내</p>
            <p className="mt-2">
              마이크를 입에서 일정한 거리로 유지하고, 말하기 직전에 녹음을 시작하세요. 스피커 소리와 주변 잡음을 줄이면 STT 비교 결과가 더 안정적입니다.
            </p>
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
            <div className="mt-3 rounded-lg bg-white p-4 text-sm text-slate-500">
              파형은 상단 면접 준비 영역에서 실시간으로 확인할 수 있습니다.
            </div>
          </div>

          <div className="mt-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <p className="text-sm text-slate-600">
              {sttMode === 'browser'
                ? 'Browser STT 결과를 최종 답변으로 가져옵니다.'
                : sttMode === 'clova'
                  ? '녹음 파일을 CLOVA STT API로 전송해 변환합니다.'
                : `녹음 파일을 ${
                    sttMode === 'quality'
                      ? OPENAI_STT_QUALITY_MODEL
                      : sttMode === 'mini'
                        ? OPENAI_STT_MINI_MODEL
                        : OPENAI_STT_WHISPER_MODEL
                  } 모델로 변환합니다.`}
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
              <p className="mt-2 text-sm text-slate-500">
                면접 답변 분석을 위해 “음”, “아”, 머뭇거림 같은 구어 표현은 제거하지 않고 STT 원문 그대로 비교합니다.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  setFinalText(openAiQualityText);
                  setActiveTimestampSource(null);
                }}
                disabled={!openAiQualityText}
              >
                gpt-4o 결과 사용
              </button>
              <button
                type="button"
                className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  setFinalText(openAiMiniText);
                  setActiveTimestampSource(null);
                }}
                disabled={!openAiMiniText}
              >
                mini 결과 사용
              </button>
              <button
                type="button"
                className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  setFinalText(openAiWhisperText);
                  setActiveTimestampSource('whisper');
                }}
                disabled={!openAiWhisperText}
              >
                whisper 결과 사용
              </button>
              <button
                type="button"
                className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  setFinalText(browserText);
                  setActiveTimestampSource(null);
                }}
                disabled={!browserText}
              >
                Browser 결과 사용
              </button>
              <button
                type="button"
                className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  setFinalText(clovaText);
                  setActiveTimestampSource(null);
                }}
                disabled={!clovaText}
              >
                CLOVA 결과 사용
              </button>
            </div>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
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
              <p className="text-sm font-semibold text-slate-950">OpenAI Whisper STT</p>
              <p className="mt-1 text-xs text-slate-500">whisper-1</p>
              <p className="mt-3 min-h-24 whitespace-pre-wrap text-sm text-slate-700">
                {openAiWhisperText || 'whisper-1 변환 전입니다.'}
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

          {showWhisperTimestamps ? (
            <div className="mt-5 rounded-lg border border-slate-200 p-4">
              <div className="flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-slate-950">Whisper 단어별 타임스탬프</h3>
                  <p className="mt-1 text-xs text-slate-500">whisper-1 verbose_json의 words 결과를 기준으로 계산합니다.</p>
                </div>
                <p className="text-xs text-slate-500">공백 시간 = 다음 단어 start - 현재 단어 end</p>
              </div>

              <div className="mt-4 max-h-80 overflow-auto rounded-lg border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                  <thead className="sticky top-0 bg-slate-50 text-xs font-semibold text-slate-600">
                    <tr>
                      <th className="px-3 py-2">단어</th>
                      <th className="px-3 py-2">시작 시간</th>
                      <th className="px-3 py-2">종료 시간</th>
                      <th className="px-3 py-2">발화 시간</th>
                      <th className="px-3 py-2">다음 단어까지의 공백 시간</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                    {whisperTimestampRows.map((item, index) => (
                      <tr key={`${item.word}-${item.start}-${index}`}>
                        <td className="px-3 py-2 font-medium text-slate-900">{item.word}</td>
                        <td className="px-3 py-2">{formatSeconds(item.start)}</td>
                        <td className="px-3 py-2">{formatSeconds(item.end)}</td>
                        <td className="px-3 py-2">{formatSeconds(item.duration)}</td>
                        <td className="px-3 py-2">{index === whisperTimestampRows.length - 1 ? '-' : formatSeconds(item.gapToNext)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <div className="rounded-lg bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">전체 답변 시간</p>
                  <p className="mt-1 font-semibold text-slate-950">{formatSeconds(whisperTimestampSummary.answerDuration)}</p>
                </div>
                <div className="rounded-lg bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">총 단어 사이 공백 시간</p>
                  <p className="mt-1 font-semibold text-slate-950">{formatSeconds(whisperTimestampSummary.totalGap)}</p>
                </div>
                <div className="rounded-lg bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">3초 이상 긴 공백 횟수</p>
                  <p className="mt-1 font-semibold text-slate-950">{whisperTimestampSummary.longGapCount}회</p>
                </div>
              </div>
            </div>
          ) : null}

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
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="font-semibold text-slate-950">OpenAI STT 고품질</p>
              <dl className="mt-3 space-y-2 text-sm text-slate-700">
                <div><dt className="font-semibold text-slate-900">모델</dt><dd>gpt-4o-transcribe</dd></div>
                <div><dt className="font-semibold text-slate-900">처리 방식</dt><dd>백엔드에서 OpenAI STT API 호출</dd></div>
                <div><dt className="font-semibold text-slate-900">비용 여부</dt><dd>비용 발생</dd></div>
                <div><dt className="font-semibold text-slate-900">장점</dt><dd>면접 답변처럼 긴 문장 품질과 안정성 우선</dd></div>
                <div><dt className="font-semibold text-slate-900">주의점</dt><dd>API 키는 백엔드 환경변수로만 관리</dd></div>
              </dl>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="font-semibold text-slate-950">OpenAI STT mini</p>
              <dl className="mt-3 space-y-2 text-sm text-slate-700">
                <div><dt className="font-semibold text-slate-900">모델</dt><dd>gpt-4o-mini-transcribe</dd></div>
                <div><dt className="font-semibold text-slate-900">처리 방식</dt><dd>백엔드에서 OpenAI STT API 호출</dd></div>
                <div><dt className="font-semibold text-slate-900">비용 여부</dt><dd>비용 발생, 고품질 모델 대비 절감 목적</dd></div>
                <div><dt className="font-semibold text-slate-900">장점</dt><dd>MVP와 반복 테스트에 적합</dd></div>
                <div><dt className="font-semibold text-slate-900">주의점</dt><dd>한국어 면접 답변 품질은 직접 비교 필요</dd></div>
              </dl>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="font-semibold text-slate-950">OpenAI Whisper STT</p>
              <dl className="mt-3 space-y-2 text-sm text-slate-700">
                <div><dt className="font-semibold text-slate-900">모델</dt><dd>whisper-1</dd></div>
                <div><dt className="font-semibold text-slate-900">처리 방식</dt><dd>백엔드에서 OpenAI STT API 호출</dd></div>
                <div><dt className="font-semibold text-slate-900">비용 여부</dt><dd>비용 발생</dd></div>
                <div><dt className="font-semibold text-slate-900">장점</dt><dd>자료와 예제가 많아 레퍼런스 비교에 적합</dd></div>
                <div><dt className="font-semibold text-slate-900">주의점</dt><dd>최신 gpt-4o 계열과 품질 차이 확인 필요</dd></div>
              </dl>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="font-semibold text-slate-950">CLOVA Speech STT</p>
              <dl className="mt-3 space-y-2 text-sm text-slate-700">
                <div><dt className="font-semibold text-slate-900">처리 방식</dt><dd>CLOVA Speech Invoke URL로 서버 업로드</dd></div>
                <div><dt className="font-semibold text-slate-900">비용 여부</dt><dd>네이버 클라우드 과금 정책 적용</dd></div>
                <div><dt className="font-semibold text-slate-900">장점</dt><dd>한국어 음성 인식 비교 대상으로 적합</dd></div>
                <div><dt className="font-semibold text-slate-900">주의점</dt><dd>Invoke URL과 Secret Key 설정 필요</dd></div>
              </dl>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="font-semibold text-slate-950">Browser STT</p>
              <dl className="mt-3 space-y-2 text-sm text-slate-700">
                <div><dt className="font-semibold text-slate-900">처리 방식</dt><dd>Chrome Web Speech API</dd></div>
                <div><dt className="font-semibold text-slate-900">비용 여부</dt><dd>별도 API 비용 없음</dd></div>
                <div><dt className="font-semibold text-slate-900">장점</dt><dd>빠른 시연 가능, API 키 불필요</dd></div>
                <div><dt className="font-semibold text-slate-900">주의점</dt><dd>브라우저 환경 의존, 녹음 파일 기반 재처리와 분리됨</dd></div>
              </dl>
            </div>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="font-semibold text-slate-950">OpenAI TTS</p>
              <dl className="mt-3 space-y-2 text-sm text-slate-700">
                <div><dt className="font-semibold text-slate-900">모델</dt><dd>gpt-4o-mini-tts</dd></div>
                <div><dt className="font-semibold text-slate-900">음성 선택</dt><dd>alloy, ash, nova 등 OpenAI voice 드롭다운</dd></div>
                <div><dt className="font-semibold text-slate-900">비용 여부</dt><dd>비용 발생</dd></div>
              </dl>
            </div>
            <div className="rounded-lg border border-slate-200 p-4">
              <p className="font-semibold text-slate-950">Browser TTS</p>
              <dl className="mt-3 space-y-2 text-sm text-slate-700">
                <div><dt className="font-semibold text-slate-900">처리 방식</dt><dd>SpeechSynthesis 브라우저 내장 기능</dd></div>
                <div><dt className="font-semibold text-slate-900">음성 선택</dt><dd>브라우저가 제공하는 ko-KR 음성 우선 표시</dd></div>
                <div><dt className="font-semibold text-slate-900">비용 여부</dt><dd>별도 API 비용 없음</dd></div>
              </dl>
            </div>
          </div>
          <div className="hidden">
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

        <section className="mt-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-950">Whisper vs GPT-4o + VAD 비교</h2>
              <p className="mt-2 text-sm text-slate-600">
                현재 녹음된 동일한 음성 파일로 Whisper 단어 타임스탬프와 GPT-4o STT + VAD 침묵 구간을 비교합니다.
              </p>
            </div>
            <button
              type="button"
              className="rounded-lg bg-[#253900] px-5 py-3 text-sm font-semibold text-white transition hover:bg-black disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
              onClick={handleRunComparison}
              disabled={!recordedBlob || comparisonLoading}
            >
              {comparisonLoading ? '비교 실행 중...' : '두 방식 비교 실행'}
            </button>
          </div>

          <div className="mt-4 rounded-lg border border-emerald-100 bg-emerald-50 p-4">
            <p className="text-sm font-semibold text-slate-950">질문 유형</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {(['technical', 'general'] as QuestionType[]).map((type) => (
                <button
                  key={type}
                  type="button"
                  className={`rounded-lg border px-4 py-2 text-sm font-semibold transition ${
                    questionType === type
                      ? 'border-emerald-500 bg-white text-emerald-700 shadow-sm'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-emerald-300'
                  }`}
                  onClick={() => setQuestionType(type)}
                  disabled={comparisonLoading}
                >
                  {type}
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs text-slate-600">
              technical은 Whisper 직후 기술용어 표기 보정을 실행하고, general은 LLM 호출 없이 Whisper 원문을 그대로 사용합니다.
            </p>
          </div>

          {comparisonError ? <div className="mt-4 rounded-lg bg-rose-50 p-4 text-sm text-rose-700">{comparisonError}</div> : null}
          {!recordedBlob ? (
            <p className="mt-4 rounded-lg bg-slate-50 p-4 text-sm text-slate-600">녹음 파일이 생성되면 비교를 실행할 수 있습니다.</p>
          ) : null}

          {comparisonResult ? (
            <div className="mt-5 grid gap-4 xl:grid-cols-2">
              <div className="rounded-lg border border-emerald-200 bg-white p-4 xl:col-span-2">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-slate-950">Whisper 원문 vs 기술용어 보정본</p>
                    <p className="mt-1 text-xs text-slate-500">
                      질문 유형: {comparisonResult.questionType} / 모델:{' '}
                      {comparisonResult.technicalCorrection.model ?? 'LLM 미호출'}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">
                      Whisper {formatMilliseconds(comparisonResult.whisper.sttMs)}
                    </span>
                    <span className="rounded-full bg-emerald-100 px-3 py-1 text-emerald-700">
                      LLM {formatMilliseconds(comparisonResult.technicalCorrection.processingMs)}
                    </span>
                    <span
                      className={`rounded-full px-3 py-1 ${
                        comparisonResult.technicalCorrection.fallback
                          ? 'bg-amber-100 text-amber-800'
                          : comparisonResult.technicalCorrection.skipped
                            ? 'bg-slate-100 text-slate-700'
                            : 'bg-emerald-100 text-emerald-700'
                      }`}
                    >
                      {comparisonResult.technicalCorrection.fallback
                        ? 'fallback'
                        : comparisonResult.technicalCorrection.skipped
                          ? 'skipped'
                          : 'normalized'}
                    </span>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Whisper original</p>
                    <p className="mt-2 min-h-24 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
                      {comparisonResult.whisper.text || '변환 텍스트가 없습니다.'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Normalized text</p>
                    <p className="mt-2 min-h-24 whitespace-pre-wrap rounded-lg bg-emerald-50 p-3 text-sm text-slate-800">
                      {comparisonResult.technicalCorrection.normalizedText || comparisonResult.whisper.text || '보정 텍스트가 없습니다.'}
                    </p>
                  </div>
                </div>

                <div className="mt-4 rounded-lg border border-slate-200">
                  <div className="border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600">
                    replacements
                  </div>
                  {comparisonResult.technicalCorrection.replacements.length === 0 ? (
                    <p className="px-3 py-3 text-sm text-slate-500">변경된 기술용어가 없습니다.</p>
                  ) : (
                    <ul className="divide-y divide-slate-100 text-sm">
                      {comparisonResult.technicalCorrection.replacements.map((item, index) => (
                        <li key={`${item.before}-${item.after}-${index}`} className="flex flex-wrap gap-2 px-3 py-2">
                          <span className="font-medium text-slate-900">{item.before || '-'}</span>
                          <span className="text-slate-400">-&gt;</span>
                          <span className="font-semibold text-emerald-700">{item.after || '-'}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {comparisonResult.technicalCorrection.warnings.length > 0 ? (
                  <div className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
                    {comparisonResult.technicalCorrection.warnings.join(' / ')}
                  </div>
                ) : null}
              </div>

              <div className="rounded-lg border border-slate-200 p-4">
                <p className="text-sm font-semibold text-slate-950">A안 Whisper</p>
                <p className="mt-1 text-xs text-slate-500">whisper-1 / verbose_json / word timestamp</p>
                <p className="mt-4 min-h-24 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
                  {comparisonResult.whisper.text || '변환 텍스트가 없습니다.'}
                </p>
                <dl className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">STT 처리 시간</dt><dd className="mt-1 font-semibold">{formatMilliseconds(comparisonResult.whisper.sttMs)}</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">전체 분석 완료 시간</dt><dd className="mt-1 font-semibold">{formatMilliseconds(comparisonResult.whisper.totalMs)}</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">답변 전체 길이</dt><dd className="mt-1 font-semibold">{formatSeconds(comparisonResult.whisper.audioDuration)}</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">총 휴지 시간</dt><dd className="mt-1 font-semibold">{formatSeconds(comparisonResult.whisper.totalPauseDuration)}</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">휴지 횟수</dt><dd className="mt-1 font-semibold">{comparisonResult.whisper.pauseCount}회</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">긴 휴지 횟수</dt><dd className="mt-1 font-semibold">{comparisonResult.whisper.longPauseCount}회</dd></div>
                </dl>
                <p className="mt-4 text-sm text-slate-700">
                  추임새: 음 {comparisonResult.whisper.fillers['음']}회, 어 {comparisonResult.whisper.fillers['어']}회, 아 {comparisonResult.whisper.fillers['아']}회
                  <span className="ml-2 text-xs text-slate-500">총 {getTotalFillerCount(comparisonResult.whisper.fillers)}회</span>
                </p>

                <div className="mt-4 max-h-72 overflow-auto rounded-lg border border-slate-200">
                  <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                    <thead className="sticky top-0 bg-slate-50 text-xs font-semibold text-slate-600">
                      <tr>
                        <th className="px-3 py-2">단어</th>
                        <th className="px-3 py-2">start</th>
                        <th className="px-3 py-2">end</th>
                        <th className="px-3 py-2">공백</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {comparisonResult.whisper.words.map((item, index) => (
                        <tr key={`${item.word}-${item.start}-${index}`}>
                          <td className="px-3 py-2 font-medium text-slate-900">{item.word}</td>
                          <td className="px-3 py-2">{formatSeconds(item.start)}</td>
                          <td className="px-3 py-2">{formatSeconds(item.end)}</td>
                          <td className="px-3 py-2">{index === comparisonResult.whisper.words.length - 1 ? '-' : formatSeconds(item.gapToNext)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 p-4">
                <p className="text-sm font-semibold text-slate-950">B안 GPT-4o + VAD</p>
                <p className="mt-1 text-xs text-slate-500">gpt-4o-transcribe / adaptive RMS VAD</p>
                <p className="mt-4 min-h-24 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
                  {comparisonResult.gpt4oVad.text || '변환 텍스트가 없습니다.'}
                </p>
                <dl className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">STT 처리 시간</dt><dd className="mt-1 font-semibold">{formatMilliseconds(comparisonResult.gpt4oVad.sttMs)}</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">전체 분석 완료 시간</dt><dd className="mt-1 font-semibold">{formatMilliseconds(comparisonResult.gpt4oVad.totalMs)}</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">답변 전체 길이</dt><dd className="mt-1 font-semibold">{formatSeconds(comparisonResult.gpt4oVad.audioDuration)}</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">첫 발화 시작</dt><dd className="mt-1 font-semibold">{comparisonResult.gpt4oVad.firstSpeechStartSec === null ? '-' : formatSeconds(comparisonResult.gpt4oVad.firstSpeechStartSec)}</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">마지막 침묵</dt><dd className="mt-1 font-semibold">{formatSeconds(comparisonResult.gpt4oVad.trailingSilenceSec)}</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">실제 발화 시간</dt><dd className="mt-1 font-semibold">{formatSeconds(comparisonResult.gpt4oVad.actualSpeechDuration)}</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">총 휴지 시간</dt><dd className="mt-1 font-semibold">{formatSeconds(comparisonResult.gpt4oVad.totalPauseDuration)}</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">휴지 횟수</dt><dd className="mt-1 font-semibold">{comparisonResult.gpt4oVad.pauseCount}회</dd></div>
                  <div className="rounded-lg bg-slate-50 p-3"><dt className="text-xs text-slate-500">긴 휴지 횟수</dt><dd className="mt-1 font-semibold">{comparisonResult.gpt4oVad.longPauseCount}회</dd></div>
                </dl>
                <p className="mt-4 text-sm text-slate-700">
                  추임새: 음 {comparisonResult.gpt4oVad.fillers['음']}회, 어 {comparisonResult.gpt4oVad.fillers['어']}회, 아 {comparisonResult.gpt4oVad.fillers['아']}회
                  <span className="ml-2 text-xs text-slate-500">총 {getTotalFillerCount(comparisonResult.gpt4oVad.fillers)}회</span>
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  VAD 기준: frame {comparisonResult.gpt4oVad.settings.frameMs}ms, threshold {comparisonResult.gpt4oVad.settings.threshold.toFixed(4)}, 최소 발화 {formatSeconds(comparisonResult.gpt4oVad.settings.minSpeechSec)}, 병합 {formatSeconds(comparisonResult.gpt4oVad.settings.mergeGapSec)}, 최소 휴지 {formatSeconds(comparisonResult.gpt4oVad.settings.minPauseSec)}, 긴 휴지 {formatSeconds(comparisonResult.gpt4oVad.settings.longPauseSec)}
                </p>

                <div className="mt-4 max-h-72 overflow-auto rounded-lg border border-slate-200">
                  <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                    <thead className="sticky top-0 bg-slate-50 text-xs font-semibold text-slate-600">
                      <tr>
                        <th className="px-3 py-2">start</th>
                        <th className="px-3 py-2">end</th>
                        <th className="px-3 py-2">duration</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {comparisonResult.gpt4oVad.silenceSegments.length === 0 ? (
                        <tr>
                          <td className="px-3 py-3 text-slate-500" colSpan={3}>감지된 침묵 구간이 없습니다.</td>
                        </tr>
                      ) : (
                        comparisonResult.gpt4oVad.silenceSegments.map((segment, index) => (
                          <tr key={`${segment.start}-${segment.end}-${index}`}>
                            <td className="px-3 py-2">{formatSeconds(segment.start)}</td>
                            <td className="px-3 py-2">{formatSeconds(segment.end)}</td>
                            <td className="px-3 py-2 font-medium text-slate-900">{formatSeconds(segment.duration)}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : null}

          {normalizedAnalysisPayloads ? (
            <div className="mt-5 rounded-lg border border-slate-200 bg-slate-950 p-4 text-slate-100">
              <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p className="text-sm font-semibold">Normalized answer payload</p>
                  <p className="mt-1 text-xs text-slate-400">
                    DB save preview. Browser object URL is intentionally not used as audio_url.
                  </p>
                </div>
                <p className="text-xs text-slate-400">session_id / question_id / audio_url: null</p>
              </div>
              <pre className="mt-4 max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-black p-4 text-xs leading-relaxed text-emerald-100">
                {JSON.stringify(normalizedAnalysisPayloads, null, 2)}
              </pre>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}

export default App;
