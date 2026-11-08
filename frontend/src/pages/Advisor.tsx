import { useMutation } from '@tanstack/react-query';
import { Bot, Send } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Markdown } from '../components/Markdown';
import { Button, ErrorNote, PageHeader, Panel, Query } from '../components/ui';
import { api } from '../lib/api';
import { dateTime, usd } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { Advice } from '../lib/types';

const SUGGESTED = ['Where can I save the most?', 'Why did spending change?', 'Which resources may run out of capacity?', 'Is the Kubernetes cluster healthy?'];

function ModeLabel({ advice }: { advice: Advice }) {
  return (
    <p className="flex flex-wrap items-center gap-x-2 text-sm text-muted">
      <Bot size={15} aria-hidden />
      <span className={advice.mode === 'ai' ? 'font-medium text-accent' : 'font-medium text-warn'}>{advice.mode === 'ai' ? `AI answer${advice.model ? `, ${advice.model}` : ''}` : 'Rule-based fallback'}</span>
      <span>Generated {dateTime(advice.generated_at)}</span>
    </p>
  );
}

export default function Advisor() {
  const summary = useApi<Advice>('/advisor/summary');
  const [question, setQuestion] = useState('');
  const [thread, setThread] = useState<Advice[]>([]);
  const ask = useMutation({
    mutationFn: (text: string) => api<Advice>('/advisor/ask', { method: 'POST', body: { question: text } }),
    onSuccess: (advice) => { setThread((items) => [advice, ...items]); setQuestion(''); },
  });
  const trimmed = question.trim();
  const valid = trimmed.length >= 3 && trimmed.length <= 1000;
  const submit = (event: FormEvent) => { event.preventDefault(); if (valid) ask.mutate(trimmed); };

  return (
    <div className="space-y-5">
      <PageHeader heading="Cloud Advisor" intro="Ask about performance and spend. Answers use only the figures CloudPulse computed." source={summary.data?.data_source} />
      {summary.data?.mode === 'fallback' && <p role="status" className="rounded-lg bg-panel p-4 text-sm"><span className="font-medium text-warn">Fallback mode.</span> <span className="text-muted">{summary.data.notice}</span></p>}
      <Panel>
        <form onSubmit={submit}>
          <label htmlFor="q" className="font-display text-lg font-semibold">Ask a question</label>
          <div className="mt-2 flex gap-2">
            <input id="q" value={question} maxLength={1000} onChange={(e) => setQuestion(e.target.value)} placeholder="Where can I save the most?" className="min-h-11 min-w-0 flex-1 rounded-md border border-line bg-panel px-3 text-base" />
            <Button type="submit" variant="primary" disabled={!valid || ask.isPending} className="min-h-11" aria-label="Ask"><Send size={16} aria-hidden /><span className="hidden sm:inline">{ask.isPending ? 'Asking' : 'Ask'}</span></Button>
          </div>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTED.map((text) => <Button key={text} disabled={ask.isPending} onClick={() => ask.mutate(text)}>{text}</Button>)}
        </div>
      </Panel>
      {ask.isError && <ErrorNote error={ask.error} />}
      {thread.map((advice, index) => (
        <Panel key={thread.length - index} heading={advice.question ?? 'Answer'}>
          <ModeLabel advice={advice} />
          <div className="mt-3 max-w-3xl"><Markdown text={advice.answer} /></div>
        </Panel>
      ))}
      <Panel heading="Infrastructure summary" note={summary.data ? `Estimated savings ${usd(summary.data.estimated_monthly_savings_usd)} per month` : undefined}>
        <Query q={summary}>
          {(advice) => (
            <>
              <ModeLabel advice={advice} />
              <div className="mt-3 max-w-3xl"><Markdown text={advice.answer} /></div>
            </>
          )}
        </Query>
      </Panel>
    </div>
  );
}
