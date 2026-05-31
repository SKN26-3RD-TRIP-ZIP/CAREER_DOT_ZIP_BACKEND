import fs from 'fs';
import path from 'path';

const filePath = path.resolve('test.wav');
const samples = 16000;
const freq = 440;
const buffer = Buffer.alloc(44 + samples * 2);
buffer.write('RIFF', 0);
buffer.writeUInt32LE(36 + samples * 2, 4);
buffer.write('WAVE', 8);
buffer.write('fmt ', 12);
buffer.writeUInt32LE(16, 16);
buffer.writeUInt16LE(1, 20);
buffer.writeUInt16LE(1, 22);
buffer.writeUInt32LE(16000, 24);
buffer.writeUInt32LE(16000 * 2, 28);
buffer.writeUInt16LE(2, 32);
buffer.writeUInt16LE(16, 34);
buffer.write('data', 36);
buffer.writeUInt32LE(samples * 2, 40);
for (let i = 0; i < samples; i += 1) {
  const t = i / 16000;
  const s = Math.round(Math.sin(2 * Math.PI * freq * t) * 32767);
  buffer.writeInt16LE(s, 44 + i * 2);
}
fs.writeFileSync(filePath, buffer);

const formData = new FormData();
formData.append('audio', new Blob([fs.readFileSync(filePath)], { type: 'audio/wav' }), 'test.wav');

const response = await fetch('http://localhost:4000/api/stt', {
  method: 'POST',
  body: formData,
});
console.log('status', response.status);
console.log('headers', Object.fromEntries(response.headers.entries()));
console.log(await response.text());
