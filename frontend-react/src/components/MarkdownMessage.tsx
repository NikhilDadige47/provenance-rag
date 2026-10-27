import React from 'react';

interface MarkdownMessageProps {
  content: string;
}

export const MarkdownMessage: React.FC<MarkdownMessageProps> = ({ content }) => {
  const scrollToSource = (num: string) => {
    window.dispatchEvent(new CustomEvent('open-source-card', { detail: { citation: num } }));

    const tryScroll = () => {
      const card = document.getElementById(`source-card-${num}`);
      const btn = document.getElementById(`source-btn-${num}`);
      const el = card || btn;
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('ring-2', 'ring-primary', 'bg-primary/10');
        setTimeout(() => el.classList.remove('ring-2', 'ring-primary', 'bg-primary/10'), 2500);
        return true;
      }
      return false;
    };

    if (!tryScroll()) {
      setTimeout(tryScroll, 70);
      setTimeout(tryScroll, 180);
      setTimeout(tryScroll, 350);
    }
  };

  // Helper to parse inline tokens: citations [1], bold **text**, italic *text*, code `code`, and <br>
  const renderInline = (text: string): React.ReactNode => {
    // Regex splits text by: citations [1] or 【1】, bold **text**, italic *text*, code `code`, and <br> tags
    const tokenRegex = /((?:\[|【)\s*\d+(?:\s*,\s*\d+)*\s*(?:\]|】)|\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|<br\s*\/?>)/gi;
    const parts = text.split(tokenRegex);

    return parts.map((part, idx) => {
      if (!part) return null;

      // Handle <br> / <br/> / <br /> tags
      if (/^<br\s*\/?>$/i.test(part)) {
        return <br key={idx} />;
      }

      // Citations like [1], 【1】, [1, 2], or 【1, 2】
      const citationMatch = part.match(/^(?:\[|【)\s*(\d+(?:\s*,\s*\d+)*)\s*(?:\]|】)$/);
      if (citationMatch) {
        const nums = citationMatch[1].split(',').map((n) => n.trim());

        // Find previous non-empty part to ensure space precedes citation
        let prevNonEmpty = '';
        for (let p = idx - 1; p >= 0; p--) {
          if (parts[p]) {
            prevNonEmpty = parts[p];
            break;
          }
        }
        const hasPrecedingSpace = /\s$/.test(prevNonEmpty);

        return (
          <React.Fragment key={idx}>
            {!hasPrecedingSpace && <span>&nbsp;</span>}
            <span className="inline-block ml-1 mr-0.5 align-baseline">
              {nums.map((num, nIdx) => (
                <button
                  key={nIdx}
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    scrollToSource(num);
                  }}
                  style={{ color: 'var(--citation-blue, #2563eb)' }}
                  className="inline font-semibold text-[length:inherit] leading-inherit hover:underline cursor-pointer transition-colors select-none p-0 bg-transparent border-none mx-0.5 text-blue-600 dark:text-blue-400"
                  title={`Jump to Source [${num}]`}
                >
                  [{num}]
                </button>
              ))}
            </span>
          </React.Fragment>
        );
      }

      // Bold text: **content**
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        const boldContent = part.slice(2, -2);
        return (
          <strong key={idx} className="font-semibold text-foreground">
            {renderInline(boldContent)}
          </strong>
        );
      }

      // Italic text: *content* (not **)
      if (part.startsWith('*') && part.endsWith('*') && part.length > 2 && !part.startsWith('**')) {
        const italicContent = part.slice(1, -1);
        return (
          <em key={idx} className="italic text-foreground/90">
            {renderInline(italicContent)}
          </em>
        );
      }

      // Inline code: `code`
      if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
        const codeContent = part.slice(1, -1);
        return (
          <code
            key={idx}
            className="px-1.5 py-0.5 rounded bg-muted font-mono text-[12px] border border-border/60 text-foreground"
          >
            {codeContent}
          </code>
        );
      }

      return <span key={idx}>{part}</span>;
    });
  };

  // Block parser: processes lines into headers, tables, lists, codeblocks, and paragraphs
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let currentList: { type: 'ul' | 'ol'; items: string[] } | null = null;
  let codeBlockBuffer: string[] | null = null;
  let tableBuffer: string[] | null = null;

  const flushList = (key: string) => {
    if (!currentList) return;
    if (currentList.type === 'ul') {
      elements.push(
        <ul key={key} className="my-2.5 space-y-1.5 pl-1">
          {currentList.items.map((item, iIdx) => (
            <li key={iIdx} className="flex items-start gap-2.5 text-sm leading-relaxed">
              <span className="size-1.5 rounded-full bg-primary/70 mt-2 shrink-0" />
              <div className="flex-1">{renderInline(item)}</div>
            </li>
          ))}
        </ul>
      );
    } else {
      elements.push(
        <ol key={key} className="my-2.5 space-y-1.5 pl-1">
          {currentList.items.map((item, iIdx) => (
            <li key={iIdx} className="flex items-start gap-2 text-sm leading-relaxed">
              <span className="font-mono text-xs font-bold text-primary shrink-0 mt-0.5 min-w-[18px]">
                {iIdx + 1}.
              </span>
              <div className="flex-1">{renderInline(item)}</div>
            </li>
          ))}
        </ol>
      );
    }
    currentList = null;
  };

  const flushTable = (key: string) => {
    if (!tableBuffer || tableBuffer.length < 2) {
      if (tableBuffer) {
        tableBuffer.forEach((line, lIdx) => {
          elements.push(
            <p key={`${key}-fallback-${lIdx}`} className="my-2 text-sm leading-relaxed text-foreground/90">
              {renderInline(line)}
            </p>
          );
        });
      }
      tableBuffer = null;
      return;
    }

    const headerLine = tableBuffer[0];
    const delimiterLine = tableBuffer[1];

    // Delimiter must consist of hyphens, colons, spaces, and pipes (e.g. |---|---|)
    const isDelimiter = delimiterLine.replace(/[\s|:-]/g, '').length === 0;
    if (!isDelimiter) {
      tableBuffer.forEach((line, lIdx) => {
        elements.push(
          <p key={`${key}-fallback-${lIdx}`} className="my-2 text-sm leading-relaxed text-foreground/90">
            {renderInline(line)}
          </p>
        );
      });
      tableBuffer = null;
      return;
    }

    const parseCells = (line: string): string[] => {
      let trimmed = line.trim();
      if (trimmed.startsWith('|')) trimmed = trimmed.slice(1);
      if (trimmed.endsWith('|')) trimmed = trimmed.slice(0, -1);
      return trimmed.split('|').map((c) => c.trim());
    };

    const headers = parseCells(headerLine);
    const bodyRows = tableBuffer.slice(2).map(parseCells);

    elements.push(
      <div key={key} className="my-3.5 overflow-x-auto rounded-lg border border-border shadow-xs">
        <table className="w-full text-left text-xs sm:text-sm border-collapse">
          <thead className="bg-muted/80 text-foreground font-semibold border-b border-border">
            <tr>
              {headers.map((h, hIdx) => (
                <th key={hIdx} className="px-3.5 py-2.5 font-semibold text-foreground/90 whitespace-nowrap">
                  {renderInline(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60 bg-card">
            {bodyRows.map((row, rIdx) => (
              <tr key={rIdx} className="hover:bg-muted/30 transition-colors">
                {row.map((cell, cIdx) => (
                  <td key={cIdx} className="px-3.5 py-2.5 text-foreground/85 leading-relaxed align-top">
                    {renderInline(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );

    tableBuffer = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const trimmed = rawLine.trim();

    // Handle Code Blocks ```
    if (trimmed.startsWith('```')) {
      flushList(`list-before-code-${i}`);
      flushTable(`table-before-code-${i}`);
      if (codeBlockBuffer === null) {
        codeBlockBuffer = [];
      } else {
        elements.push(
          <pre
            key={`code-${i}`}
            className="my-3 p-3.5 rounded-lg bg-muted/70 border border-border font-mono text-xs overflow-x-auto text-foreground"
          >
            <code>{codeBlockBuffer.join('\n')}</code>
          </pre>
        );
        codeBlockBuffer = null;
      }
      continue;
    }

    if (codeBlockBuffer !== null) {
      codeBlockBuffer.push(rawLine);
      continue;
    }

    // Blank line
    if (!trimmed) {
      flushList(`list-flush-${i}`);
      flushTable(`table-flush-${i}`);
      continue;
    }

    // Handle Markdown Tables (| ... |)
    const isTableLine = trimmed.startsWith('|') && trimmed.includes('|', 1);
    if (isTableLine) {
      flushList(`flush-list-before-table-${i}`);
      if (tableBuffer === null) {
        tableBuffer = [];
      }
      tableBuffer.push(trimmed);
      continue;
    } else {
      flushTable(`flush-table-before-other-${i}`);
    }

    // Headings
    if (trimmed.startsWith('### ')) {
      flushList(`list-h3-${i}`);
      elements.push(
        <h3
          key={`h3-${i}`}
          className="text-sm sm:text-base font-bold text-foreground mt-4 mb-2 flex items-center gap-2 border-b border-border/40 pb-1"
        >
          <span className="w-1 h-3.5 rounded-full bg-primary shrink-0" />
          <span>{renderInline(trimmed.slice(4))}</span>
        </h3>
      );
      continue;
    }

    if (trimmed.startsWith('## ')) {
      flushList(`list-h2-${i}`);
      elements.push(
        <h2
          key={`h2-${i}`}
          className="text-base sm:text-lg font-bold text-foreground mt-4 mb-2 flex items-center gap-2 border-b border-border/50 pb-1"
        >
          <span className="w-1.5 h-4 rounded-full bg-primary shrink-0" />
          <span>{renderInline(trimmed.slice(3))}</span>
        </h2>
      );
      continue;
    }

    if (trimmed.startsWith('# ')) {
      flushList(`list-h1-${i}`);
      elements.push(
        <h1 key={`h1-${i}`} className="text-lg sm:text-xl font-bold text-foreground mt-5 mb-2.5">
          {renderInline(trimmed.slice(2))}
        </h1>
      );
      continue;
    }

    // Blockquote >
    if (trimmed.startsWith('> ')) {
      flushList(`list-quote-${i}`);
      elements.push(
        <blockquote
          key={`quote-${i}`}
          className="my-2.5 border-l-3 border-primary/60 bg-muted/30 px-3.5 py-2 rounded-r-md text-xs sm:text-sm italic text-muted-foreground"
        >
          {renderInline(trimmed.slice(2))}
        </blockquote>
      );
      continue;
    }

    // Unordered list item (- or * or •)
    const ulMatch = trimmed.match(/^[-*•]\s+(.+)/);
    if (ulMatch) {
      if (!currentList || currentList.type !== 'ul') {
        flushList(`flush-before-ul-${i}`);
        currentList = { type: 'ul', items: [] };
      }
      currentList.items.push(ulMatch[1]);
      continue;
    }

    // Ordered list item (1. or 2.)
    const olMatch = trimmed.match(/^\d+\.\s+(.+)/);
    if (olMatch) {
      if (!currentList || currentList.type !== 'ol') {
        flushList(`flush-before-ol-${i}`);
        currentList = { type: 'ol', items: [] };
      }
      currentList.items.push(olMatch[1]);
      continue;
    }

    // Standard paragraph
    flushList(`flush-before-p-${i}`);
    elements.push(
      <p key={`p-${i}`} className="my-2 text-sm leading-relaxed text-foreground/90">
        {renderInline(trimmed)}
      </p>
    );
  }

  flushList('final-list-flush');
  flushTable('final-table-flush');

  return <div className="space-y-1 text-sm leading-relaxed">{elements}</div>;
};
