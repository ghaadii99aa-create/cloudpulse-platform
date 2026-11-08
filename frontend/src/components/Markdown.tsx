import { Fragment, type ReactNode } from 'react';

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? <strong key={index} className="font-semibold">{part.slice(2, -2)}</strong> : <Fragment key={index}>{part}</Fragment>,
  );
}

/** Renders the small subset of Markdown the advisor produces, without injecting HTML. */
export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(<ul key={`l${blocks.length}`} className="list-disc space-y-1.5 pl-5">{list.map((item, i) => <li key={i}>{inline(item)}</li>)}</ul>);
      list = [];
    }
  };
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    const bullet = /^[-*]\s+(.*)/.exec(line);
    if (bullet) {
      list.push(bullet[1]);
      continue;
    }
    flush();
    if (!line) continue;
    const heading = /^#{1,4}\s+(.*)/.exec(line);
    blocks.push(heading ? <p key={blocks.length} className="font-semibold">{inline(heading[1])}</p> : <p key={blocks.length}>{inline(line)}</p>);
  }
  flush();
  return <div className="space-y-3 leading-relaxed">{blocks}</div>;
}
