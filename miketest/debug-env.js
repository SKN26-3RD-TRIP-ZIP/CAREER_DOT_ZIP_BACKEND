import dotenv from 'dotenv';
import { resolve } from 'path';

const result = dotenv.config({ path: resolve('.env') });
console.log('dotenv result:', result);
console.log('OPENAI_API_KEY exists:', !!process.env.OPENAI_API_KEY);
console.log('OPENAI_API_KEY sample:', process.env.OPENAI_API_KEY ? `${process.env.OPENAI_API_KEY.slice(0, 5)}...${process.env.OPENAI_API_KEY.slice(-5)}` : 'none');
console.log('cwd:', process.cwd());
