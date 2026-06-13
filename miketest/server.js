import express from 'express';
import cors from 'cors';
import multer from 'multer';
import dotenv from 'dotenv';

dotenv.config();

const app = express();
const upload = multer({ storage: multer.memoryStorage() });
const port = process.env.PORT || 4000;
const allowedSttModels = new Set(['gpt-4o-transcribe', 'gpt-4o-mini-transcribe', 'whisper-1']);
const allowedTtsVoices = new Set([
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
]);
const textCorrectionModel =
  process.env.OPENAI_TEXT_MODEL || process.env.OPENAI_CORRECTION_MODEL || 'gpt-4o-mini';

const buildCorrectionFallback = ({
  text,
  questionType,
  warning,
  processingTimeMs = 0,
  skipped = false
}) => ({
  question_type: questionType,
  normalized_text: text,
  replacements: [],
  warnings: warning ? [warning] : [],
  fallback: !skipped,
  skipped,
  model: skipped ? null : textCorrectionModel,
  processing_time_ms: processingTimeMs
});

const extractJsonObject = (rawText) => {
  const trimmed = String(rawText || '').trim();
  if (!trimmed) {
    throw new Error('Empty LLM response');
  }

  const withoutFence = trimmed
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/i, '')
    .trim();

  try {
    return JSON.parse(withoutFence);
  } catch {
    const start = withoutFence.indexOf('{');
    const end = withoutFence.lastIndexOf('}');
    if (start === -1 || end === -1 || end <= start) {
      throw new Error('LLM response is not JSON');
    }
    return JSON.parse(withoutFence.slice(start, end + 1));
  }
};

const sanitizeCorrectionResult = (parsed, originalText) => {
  const normalizedText =
    typeof parsed?.normalized_text === 'string' && parsed.normalized_text.trim()
      ? parsed.normalized_text
      : originalText;
  const replacements = Array.isArray(parsed?.replacements)
    ? parsed.replacements
        .map((item) => ({
          before: typeof item?.before === 'string' ? item.before : '',
          after: typeof item?.after === 'string' ? item.after : ''
        }))
        .filter((item) => item.before || item.after)
    : [];
  const warnings = Array.isArray(parsed?.warnings)
    ? parsed.warnings.filter((item) => typeof item === 'string')
    : [];

  return {
    normalized_text: normalizedText,
    replacements,
    warnings
  };
};

console.log('Voice server starting. OPENAI_API_KEY loaded:', !!process.env.OPENAI_API_KEY);

app.use(cors());
app.use(express.json({ limit: '1mb' }));
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok' });
});

app.post('/api/normalize-technical-terms', async (req, res) => {
  const text = typeof req.body?.text === 'string' ? req.body.text : '';
  const questionType = req.body?.questionType === 'technical' ? 'technical' : 'general';

  if (!text.trim()) {
    return res.status(400).json({ error: 'No text provided' });
  }

  if (questionType !== 'technical') {
    return res.json(
      buildCorrectionFallback({
        text,
        questionType,
        warning: 'Question type is general, so technical normalization was skipped.',
        skipped: true
      })
    );
  }

  const startedAt = Date.now();
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return res.json(
      buildCorrectionFallback({
        text,
        questionType,
        warning: 'OPENAI_API_KEY is not configured. Used Whisper text as fallback.',
        processingTimeMs: Date.now() - startedAt
      })
    );
  }

  try {
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: textCorrectionModel,
        temperature: 0,
        response_format: { type: 'json_object' },
        messages: [
          {
            role: 'system',
            content:
              'You normalize Korean speech transcription only for technical term notation. Return JSON only.'
          },
          {
            role: 'user',
            content: [
              'Correct only technology term spelling or notation in this Korean interview answer.',
              'Rules:',
              '- Do not change sentence meaning.',
              '- Do not add correct answers or facts.',
              '- Do not fix factual mistakes.',
              '- Do not change negation words.',
              '- Do not change numbers.',
              '- Do not summarize.',
              '- Do not remove fillers, repetitions, or hesitations.',
              '- Preserve non-technical wording as much as possible.',
              'Return exactly this JSON shape:',
              '{"normalized_text":"...","replacements":[{"before":"도커","after":"Docker"}],"warnings":[]}',
              'Examples of allowed notation changes: 마이 에스큐엘 -> MySQL, 도커 -> Docker, 파이토치 -> PyTorch, 크로스 엔트로피 -> cross entropy.',
              `Text:\n${text}`
            ].join('\n')
          }
        ]
      })
    });

    const responseText = await response.text();
    if (!response.ok) {
      return res.json(
        buildCorrectionFallback({
          text,
          questionType,
          warning: `LLM request failed: ${responseText}`,
          processingTimeMs: Date.now() - startedAt
        })
      );
    }

    const data = JSON.parse(responseText);
    const content = data?.choices?.[0]?.message?.content;
    const parsed = extractJsonObject(content);
    const sanitized = sanitizeCorrectionResult(parsed, text);

    return res.json({
      question_type: questionType,
      ...sanitized,
      fallback: false,
      skipped: false,
      model: textCorrectionModel,
      processing_time_ms: Date.now() - startedAt
    });
  } catch (error) {
    console.error('Technical term normalization error:', error);
    const message = error instanceof Error ? error.message : 'Unknown error';
    return res.json(
      buildCorrectionFallback({
        text,
        questionType,
        warning: `LLM normalization failed: ${message}`,
        processingTimeMs: Date.now() - startedAt
      })
    );
  }
});

app.post('/api/stt', upload.single('audio'), async (req, res) => {
  console.log('STT request received. OPENAI_API_KEY exists:', !!process.env.OPENAI_API_KEY);
  console.log('STT request file present:', !!req.file, 'fieldname:', req.file?.fieldname, 'mimetype:', req.file?.mimetype);
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'OPENAI_API_KEY is not configured' });
  }

  if (!req.file) {
    return res.status(400).json({ error: 'No audio file uploaded' });
  }

  try {
    const requestedModel = typeof req.body?.model === 'string' ? req.body.model : '';
    const sttModel = allowedSttModels.has(requestedModel)
      ? requestedModel
      : process.env.OPENAI_STT_MODEL || 'whisper-1';

    const formData = new FormData();
    formData.append('file', new Blob([req.file.buffer], { type: req.file.mimetype }), req.file.originalname);
    formData.append('model', sttModel);
    formData.append('language', sttModel === 'whisper-1' ? 'ko' : process.env.OPENAI_STT_LANGUAGE || 'ko');

    if (sttModel === 'whisper-1') {
      formData.append('response_format', 'verbose_json');
      formData.append('timestamp_granularities[]', 'word');
    }

    const response = await fetch('https://api.openai.com/v1/audio/transcriptions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`
      },
      body: formData
    });

    if (!response.ok) {
      const errorText = await response.text();
      try {
        const parsed = JSON.parse(errorText);
        return res.status(response.status).json({
          error: parsed.error?.message || parsed.error || errorText
        });
      } catch {
        return res.status(response.status).json({ error: errorText });
      }
    }

    const data = await response.json();
    return res.json({
      text: data.text,
      model: sttModel,
      ...(sttModel === 'whisper-1'
        ? {
            duration: data.duration,
            language: data.language,
            words: Array.isArray(data.words) ? data.words : []
          }
        : {})
    });
  } catch (error) {
    console.error('STT request error:', error);
    return res.status(500).json({ error: 'Failed to request STT from OpenAI' });
  }
});

app.post('/api/clova/stt', upload.single('audio'), async (req, res) => {
  const invokeUrl = process.env.CLOVA_SPEECH_INVOKE_URL;
  const secretKey = process.env.CLOVA_SPEECH_SECRET_KEY;
  if (!invokeUrl) {
    return res.status(500).json({ error: 'CLOVA_SPEECH_INVOKE_URL is not configured' });
  }
  if (!secretKey) {
    return res.status(500).json({ error: 'CLOVA_SPEECH_SECRET_KEY is not configured' });
  }
  if (!/^https?:\/\//i.test(invokeUrl)) {
    return res.status(500).json({
      error: 'CLOVA_SPEECH_INVOKE_URL must be a full URL that starts with http:// or https://'
    });
  }

  if (!req.file) {
    return res.status(400).json({ error: 'No audio file uploaded' });
  }

  const supportedAudioTypes = new Set([
    'audio/mpeg',
    'audio/mp3',
    'audio/aac',
    'audio/ac3',
    'audio/ogg',
    'audio/flac',
    'audio/wav',
    'audio/x-wav',
    'audio/mp4'
  ]);
  if (!supportedAudioTypes.has(req.file.mimetype)) {
    return res.status(400).json({
      error: `Unsupported audio format for CLOVA Speech Domain: ${req.file.mimetype || 'unknown'}`
    });
  }

  try {
    const normalizedInvokeUrl = invokeUrl.replace(/\/+$/, '');
    const isShortRecognitionUrl = normalizedInvokeUrl.endsWith('/recog/v1/stt');
    const uploadUrl =
      isShortRecognitionUrl || normalizedInvokeUrl.endsWith('/recognizer/upload')
        ? normalizedInvokeUrl
        : `${normalizedInvokeUrl}/recognizer/upload`;
    const rawLanguage = process.env.CLOVA_SPEECH_LANG || 'Kor';
    const language = isShortRecognitionUrl ? rawLanguage : rawLanguage === 'Kor' ? 'ko-KR' : rawLanguage;
    const params = {
      language,
      completion: 'sync',
      callback: '',
      fullText: true,
      wordAlignment: false,
      diarization: {
        enable: false
      }
    };

    const body = isShortRecognitionUrl
      ? req.file.buffer
      : (() => {
          const formData = new FormData();
          formData.append('params', JSON.stringify(params));
          formData.append('media', new Blob([req.file.buffer], { type: req.file.mimetype }), req.file.originalname || 'voice.wav');
          return formData;
        })();

    const response = await fetch(
      isShortRecognitionUrl ? `${uploadUrl}?lang=${encodeURIComponent(language)}` : uploadUrl,
      {
      method: 'POST',
      headers: {
        'X-CLOVASPEECH-API-KEY': secretKey,
        ...(isShortRecognitionUrl ? { 'Content-Type': 'application/octet-stream' } : {})
      },
      body
      }
    );

    const responseText = await response.text();
    if (!response.ok) {
      return res.status(response.status).json({ error: `CLOVA API call failed: ${responseText}` });
    }

    let data;
    try {
      data = JSON.parse(responseText);
    } catch {
      return res.status(502).json({ error: 'CLOVA response parsing failed' });
    }

    const segmentText = Array.isArray(data.segments)
      ? data.segments.map((segment) => segment?.text).filter(Boolean).join(' ')
      : '';
    const text = typeof data.text === 'string' && data.text.trim() ? data.text : segmentText;

    if (!text) {
      return res.status(502).json({ error: 'CLOVA response parsing failed: recognized text is empty' });
    }

    return res.json({ text, result: data.result, message: data.message });
  } catch (error) {
    console.error('CLOVA STT request error:', error);
    const message = error instanceof Error ? error.message : 'Unknown error';
    return res.status(500).json({ error: `CLOVA API call failed: ${message}` });
  }
});

app.post('/api/tts', async (req, res) => {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'OPENAI_API_KEY is not configured' });
  }

  const text = typeof req.body?.text === 'string' ? req.body.text.trim() : '';
  if (!text) {
    return res.status(400).json({ error: 'No text provided' });
  }

  try {
    const requestedVoice = typeof req.body?.voice === 'string' ? req.body.voice : '';
    const fallbackVoice = process.env.OPENAI_TTS_VOICE || 'alloy';
    const ttsVoice = allowedTtsVoices.has(requestedVoice)
      ? requestedVoice
      : allowedTtsVoices.has(fallbackVoice)
        ? fallbackVoice
        : 'alloy';

    const response = await fetch('https://api.openai.com/v1/audio/speech', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: process.env.OPENAI_TTS_MODEL || 'gpt-4o-mini-tts',
        voice: ttsVoice,
        input: text,
        response_format: 'mp3'
      })
    });

    if (!response.ok) {
      const errorText = await response.text();
      try {
        const parsed = JSON.parse(errorText);
        return res.status(response.status).json({
          error: parsed.error?.message || parsed.error || errorText
        });
      } catch {
        return res.status(response.status).json({ error: errorText });
      }
    }

    const audioBuffer = Buffer.from(await response.arrayBuffer());
    res.setHeader('Content-Type', 'audio/mpeg');
    res.setHeader('Cache-Control', 'no-store');
    return res.send(audioBuffer);
  } catch (error) {
    console.error('TTS request error:', error);
    return res.status(500).json({ error: 'Failed to request TTS from OpenAI' });
  }
});

app.listen(port, () => {
  console.log(`STT backend listening on http://localhost:${port}`);
});
