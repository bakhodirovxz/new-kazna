import type { ReactNode } from 'react';

function inline(text: string): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .filter((part) => part !== '')
    .map((part, i) => (part.startsWith('**') && part.endsWith('**') && part.length > 4 ? <b key={i}>{part.slice(2, -2)}</b> : part));
}

const BULLET = /^\s*(?:[-*•]|\d+[.)])\s+/;

/** Model javobi: `## ` — sarlavha, `- `/`1. ` — ro'yxat, `**…**` — qalin. HTML hech qachon kiritilmaydi. */
export function AiAnswer({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let items: ReactNode[] = [];
  const flush = () => {
    if (items.length) blocks.push(<ul key={`list-${blocks.length}`}>{items}</ul>);
    items = [];
  };
  text.split('\n').forEach((raw, i) => {
    const line = raw.trimEnd();
    if (line.startsWith('## ')) {
      flush();
      blocks.push(<h3 key={i}>{inline(line.slice(3))}</h3>);
    } else if (BULLET.test(line)) {
      items.push(<li key={i}>{inline(line.replace(BULLET, ''))}</li>);
    } else if (line.trim() === '') {
      flush();
    } else {
      flush();
      blocks.push(<p key={i}>{inline(line)}</p>);
    }
  });
  flush();
  return <div className="ai-answer">{blocks}</div>;
}
