import { useState } from 'react';

interface CodeBlockProps {
  language: string;
  code: string;
}

function CodeBlock({ language, code }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-3 rounded-xl overflow-hidden border border-white/10 bg-surface-950 font-mono text-xs shadow-lg">
      <div className="flex items-center justify-between px-4 py-2 bg-surface-900 border-b border-white/8 text-surface-400">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-forge-300">
          {language || 'text'}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] hover:text-white hover:bg-white/5 transition-colors"
        >
          {copied ? (
            <>
              <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <span className="text-emerald-400">Copied!</span>
            </>
          ) : (
            <>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="p-4 overflow-x-auto text-surface-200 leading-relaxed font-mono selection:bg-forge-700/60">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/**
 * Lightweight, zero-dependency Markdown parser for AI messages, code blocks,
 * and test suggestions.
 */
export function MarkdownRenderer({ content }: { content: string }) {
  if (!content) return null;

  // Split by code block fences: ```lang ... ```
  const codeBlockRegex = /```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g;
  const elements: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    const textBefore = content.substring(lastIndex, match.index);
    if (textBefore.trim()) {
      elements.push(
        <div key={`text-${lastIndex}`} className="space-y-2">
          {renderTextContent(textBefore)}
        </div>
      );
    }

    const language = match[1] || 'code';
    const code = match[2];
    elements.push(
      <CodeBlock key={`code-${match.index}`} language={language} code={code} />
    );

    lastIndex = match.index + match[0].length;
  }

  const remaining = content.substring(lastIndex);
  if (remaining.trim()) {
    elements.push(
      <div key={`text-${lastIndex}`} className="space-y-2">
        {renderTextContent(remaining)}
      </div>
    );
  }

  return <div className="text-sm leading-relaxed text-surface-200">{elements}</div>;
}

function renderTextContent(raw: string): React.ReactNode[] {
  const lines = raw.split('\n');
  const rendered: React.ReactNode[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Headers
    if (line.startsWith('### ')) {
      rendered.push(
        <h4 key={`h3-${i}`} className="text-sm font-bold text-white mt-3 mb-1">
          {formatInline(line.slice(4))}
        </h4>
      );
      continue;
    }
    if (line.startsWith('## ')) {
      rendered.push(
        <h3 key={`h2-${i}`} className="text-base font-bold text-white mt-4 mb-2 border-b border-white/5 pb-1">
          {formatInline(line.slice(3))}
        </h3>
      );
      continue;
    }
    if (line.startsWith('# ')) {
      rendered.push(
        <h2 key={`h1-${i}`} className="text-lg font-extrabold text-white mt-5 mb-2">
          {formatInline(line.slice(2))}
        </h2>
      );
      continue;
    }

    // Bullet points
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      rendered.push(
        <li key={`li-${i}`} className="ml-5 list-disc text-surface-300">
          {formatInline(line.trim().slice(2))}
        </li>
      );
      continue;
    }

    // Numbered lists
    const numMatch = line.trim().match(/^(\d+)\.\s+(.*)/);
    if (numMatch) {
      rendered.push(
        <div key={`num-${i}`} className="flex gap-2 ml-2 text-surface-300">
          <span className="font-mono text-forge-400 text-xs">{numMatch[1]}.</span>
          <span>{formatInline(numMatch[2])}</span>
        </div>
      );
      continue;
    }

    // Blockquote
    if (line.startsWith('> ')) {
      rendered.push(
        <blockquote key={`quote-${i}`} className="border-l-2 border-forge-500 pl-3 py-0.5 text-surface-300 italic bg-forge-500/5 my-1 rounded-r">
          {formatInline(line.slice(2))}
        </blockquote>
      );
      continue;
    }

    // Empty lines
    if (!line.trim()) {
      rendered.push(<div key={`sp-${i}`} className="h-1" />);
      continue;
    }

    // Normal paragraph line
    rendered.push(
      <p key={`p-${i}`} className="text-surface-200">
        {formatInline(line)}
      </p>
    );
  }

  return rendered;
}

function formatInline(text: string): React.ReactNode {
  // Replace bold **text** and inline `code`
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);

  return parts.map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={index}
          className="bg-surface-800 border border-white/10 text-forge-300 px-1.5 py-0.5 rounded text-xs font-mono"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={index} className="font-semibold text-white">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part;
  });
}
