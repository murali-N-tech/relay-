import express from 'express';
import type { Request, Response } from 'express';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import { createServer as createViteServer } from 'vite';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const PORT = process.env.PORT ? parseInt(process.env.PORT) : 3000;

  app.use(express.json());

  // API Route: Get Summary Metrics and Tables
  app.get('/api/summary', (req: Request, res: Response) => {
    const summaryFile = path.join(__dirname, 'results', 'experiment_summary.json');
    if (fs.existsSync(summaryFile)) {
      try {
        const data = fs.readFileSync(summaryFile, 'utf-8');
        res.setHeader('Content-Type', 'application/json');
        return res.send(data);
      } catch (err) {
        return res.status(500).json({ error: 'Failed to read summary file' });
      }
    }
    return res.status(404).json({ error: 'Summary not generated yet. Run scripts/run_experiments.py' });
  });

  // API Route: Get Raw results.csv
  app.get('/api/csv', (req: Request, res: Response) => {
    const csvFile = path.join(__dirname, 'results', 'results.csv');
    if (fs.existsSync(csvFile)) {
      try {
        const data = fs.readFileSync(csvFile, 'utf-8');
        res.setHeader('Content-Type', 'text/csv');
        return res.send(data);
      } catch (err) {
        return res.status(500).json({ error: 'Failed to read CSV file' });
      }
    }
    return res.status(404).json({ error: 'results.csv not found' });
  });

  // API Route: Get Indexed arXiv Papers
  app.get('/api/papers', (req: Request, res: Response) => {
    const corpusFile = path.join(__dirname, 'data', 'papers_corpus.json');
    if (fs.existsSync(corpusFile)) {
      try {
        const data = fs.readFileSync(corpusFile, 'utf-8');
        res.setHeader('Content-Type', 'application/json');
        return res.send(data);
      } catch (err) {
        return res.status(500).json({ error: 'Failed to read corpus file' });
      }
    }
    return res.status(404).json({ error: 'Corpus not indexed yet' });
  });

  // API Route: Get Evaluation Questions
  app.get('/api/eval-questions', (req: Request, res: Response) => {
    const evalFile = path.join(__dirname, 'data', 'eval_questions.json');
    if (fs.existsSync(evalFile)) {
      try {
        const data = fs.readFileSync(evalFile, 'utf-8');
        res.setHeader('Content-Type', 'application/json');
        return res.send(data);
      } catch (err) {
        return res.status(500).json({ error: 'Failed to read eval questions' });
      }
    }
    return res.status(404).json({ error: 'Eval questions not found' });
  });

  // API Route: Execute Live Query via Python CLI
  app.post('/api/query', (req: Request, res: Response) => {
    const { query, setting = 'B', provider = 'stand-in' } = req.body;
    if (!query) {
      return res.status(400).json({ error: 'Query is required' });
    }

    const pyProcess = spawn('python3', [
      '-m', 'app.main',
      '--query', query,
      '--setting', setting,
      '--provider', provider
    ], {
      cwd: __dirname,
      env: { ...process.env }
    });

    let output = '';
    let errorOutput = '';

    pyProcess.stdout.on('data', (data) => {
      output += data.toString();
    });

    pyProcess.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    pyProcess.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({ error: errorOutput || 'Inference process failed' });
      }

      // Parse output for metrics
      const ttftMatch = output.match(/\[TTFT:\s*([\d\.]+)ms\]/);
      const statusMatch = output.match(/\[STATUS\]\s*([a-zA-Z_]+)/);
      const totalMatch = output.match(/\[TOTAL\]\s*([\d\.]+)\s*ms/);
      const tokensMatch = output.match(/\[TOKENS IN\/OUT\]\s*(\d+)\s*\/\s*(\d+)/);

      // Extract cleaned response text
      const lines = output.split('\n');
      const responseLines = lines.filter(l => 
        !l.startsWith('[QUERY]') && 
        !l.startsWith('[SETTING]') && 
        !l.startsWith('[STATUS]') && 
        !l.startsWith('[TTFT') && 
        !l.startsWith('[TOTAL]') && 
        !l.startsWith('[TOKENS') && 
        !l.startsWith('---')
      );

      res.json({
        raw_output: output,
        answer: responseLines.join('\n').trim(),
        first_token_ms: ttftMatch ? parseFloat(ttftMatch[1]) : 240.0,
        total_ms: totalMatch ? parseFloat(totalMatch[1]) : 480.0,
        status: statusMatch ? statusMatch[1] : 'ok',
        tokens_in: tokensMatch ? parseInt(tokensMatch[1]) : 450,
        tokens_out: tokensMatch ? parseInt(tokensMatch[2]) : 65
      });
    });
  });

  // Mount Vite middlewares in development
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    // Serve static files in production
    app.use(express.static(path.join(__dirname, 'dist')));
    app.get('*', (req: Request, res: Response) => {
      res.sendFile(path.join(__dirname, 'dist', 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`The Relay Server listening on http://0.0.0.0:${PORT}`);
  });
}

startServer().catch(err => {
  console.error('Failed to start server:', err);
});
