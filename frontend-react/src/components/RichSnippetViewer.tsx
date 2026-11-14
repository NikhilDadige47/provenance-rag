import React from 'react';

interface RichSnippetViewerProps {
  text: string;
}

const TABLE_REGEX = /(<table[\s\S]*?<\/table>)/gi;

function renderHtmlTableNode(node: Node, key: string | number): React.ReactNode {
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return null;
  const el = node as HTMLElement;
  const tag = el.tagName.toLowerCase();
  const children = Array.from(el.childNodes).map((c, i) => renderHtmlTableNode(c, `${key}-${i}`));

  switch (tag) {
    case 'b':
    case 'strong':
      return (
        <strong key={key} className="font-semibold text-foreground">
          {children}
        </strong>
      );
    case 'i':
    case 'em':
      return (
        <em key={key} className="italic text-foreground/90">
          {children}
        </em>
      );
    case 'sup':
      return (
        <sup key={key} className="text-[10px] text-muted-foreground align-super ml-0.5">
          {children}
        </sup>
      );
    case 'sub':
      return (
        <sub key={key} className="text-[10px] text-muted-foreground align-sub ml-0.5">
          {children}
        </sub>
      );
    case 'br':
      return <br key={key} />;
    case 'th':
      return (
        <th
          key={key}
          className="px-2.5 py-1.5 text-left font-semibold text-foreground border border-border/70 bg-muted/70 text-[11px]"
        >
          {children}
        </th>
      );
    case 'td':
      return (
        <td
          key={key}
          className="px-2.5 py-1.5 text-foreground/90 border border-border/50 text-[11px] align-top"
        >
          {children}
        </td>
      );
    case 'tr':
      return (
        <tr key={key} className="hover:bg-muted/30 transition-colors">
          {children}
        </tr>
      );
    case 'thead':
      return <thead key={key} className="bg-muted/50">{children}</thead>;
    case 'tbody':
      return <tbody key={key} className="divide-y divide-border/40">{children}</tbody>;
    case 'table':
      return (
        <div
          key={key}
          className="w-full my-2.5 overflow-x-auto rounded-lg border border-border bg-card/40 shadow-2xs"
        >
          <table className="w-full text-left border-collapse">{children}</table>
        </div>
      );
    default:
      return <React.Fragment key={key}>{children}</React.Fragment>;
  }
}

function parseHtmlTable(html: string, keyPrefix: string): React.ReactNode {
  if (typeof window === 'undefined' || !window.DOMParser) {
    return <pre className="text-xs whitespace-pre-wrap">{html}</pre>;
  }
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const table = doc.querySelector('table');
    if (!table) return <span className="whitespace-pre-wrap">{html}</span>;
    return renderHtmlTableNode(table, `${keyPrefix}-table`);
  } catch {
    return <pre className="text-xs whitespace-pre-wrap">{html}</pre>;
  }
}

function renderInlineTokens(text: string): React.ReactNode {
  const tokenRegex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|<br\s*\/?>)/gi;
  const parts = text.split(tokenRegex);

  return parts.map((part, idx) => {
    if (!part) return null;
    if (/^<br\s*\/?>$/i.test(part)) return <br key={idx} />;
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return (
        <em key={idx} className="italic text-foreground/90">
          {part.slice(1, -1)}
        </em>
      );
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code
          key={idx}
          className="px-1.5 py-0.5 rounded bg-muted font-mono text-[11px] border border-border/60 text-foreground"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={idx}>{part}</span>;
  });
}

function renderMarkdownSegment(segmentText: string, segKey: string): React.ReactNode {
  const lines = segmentText.split('\n');
  const elements: React.ReactNode[] = [];
  let tableBuffer: string[] | null = null;
  let currentList: { type: 'ul' | 'ol'; items: string[] } | null = null;

  const flushList = (key: string) => {
    if (!currentList || currentList.items.length === 0) {
      currentList = null;
      return;
    }
    if (currentList.type === 'ul') {
      elements.push(
        <ul key={key} className="my-2 space-y-1 pl-4 list-disc marker:text-primary/70 text-xs text-foreground/90">
          {currentList.items.map((item, idx) => (
            <li key={idx} className="leading-relaxed">
              {renderInlineTokens(item)}
            </li>
          ))}
        </ul>
      );
    } else {
      elements.push(
        <ol key={key} className="my-2 space-y-1 pl-4 list-decimal marker:text-primary/70 text-xs text-foreground/90">
          {currentList.items.map((item, idx) => (
            <li key={idx} className="leading-relaxed">
              {renderInlineTokens(item)}
            </li>
          ))}
        </ol>
      );
    }
    currentList = null;
  };

  const flushTable = (key: string) => {
    if (!tableBuffer || tableBuffer.length === 0) {
      tableBuffer = null;
      return;
    }
    const cleanLines = tableBuffer.filter((l) => l.trim().length > 0);
    tableBuffer = null;
    if (cleanLines.length === 0) return;

    const parseRow = (line: string): string[] => {
      let trimmed = line.trim();
      if (trimmed.startsWith('|')) trimmed = trimmed.slice(1);
      if (trimmed.endsWith('|')) trimmed = trimmed.slice(0, -1);
      return trimmed.split('|').map((c) => c.trim());
    };

    const isSeparatorRow = (row: string[]): boolean =>
      row.every((c) => /^:?-+:?$/.test(c.replace(/\s+/g, '')));

    let headerRow: string[] | null = null;
    const bodyRows: string[][] = [];

    cleanLines.forEach((line, idx) => {
      const row = parseRow(line);
      if (idx === 0) {
        headerRow = row;
      } else if (idx === 1 && isSeparatorRow(row)) {
        // separator row, skip
      } else {
        bodyRows.push(row);
      }
    });

    elements.push(
      <div key={key} className="w-full my-2.5 overflow-x-auto rounded-lg border border-border bg-card/40 shadow-2xs">
        <table className="w-full text-left border-collapse text-xs">
          {headerRow && (
            <thead className="bg-muted/70 text-foreground font-semibold">
              <tr>
                {headerRow.map((cell, cIdx) => (
                  <th
                    key={cIdx}
                    className="px-2.5 py-1.5 text-left border border-border/70 text-[11px] font-semibold text-foreground"
                  >
                    {renderInlineTokens(cell)}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody className="divide-y divide-border/40">
            {bodyRows.map((row, rIdx) => (
              <tr key={rIdx} className="hover:bg-muted/30 transition-colors">
                {row.map((cell, cIdx) => (
                  <td key={cIdx} className="px-2.5 py-1.5 border border-border/50 text-[11px] text-foreground/90">
                    {renderInlineTokens(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const trimmed = rawLine.trim();

    if (!trimmed) {
      flushTable(`table-flush-${segKey}-${i}`);
      continue;
    }

    // Markdown Table line (| ... |)
    const isTableLine = trimmed.startsWith('|') && trimmed.includes('|', 1);
    if (isTableLine) {
      flushList(`list-before-table-${segKey}-${i}`);
      if (tableBuffer === null) tableBuffer = [];
      tableBuffer.push(trimmed);
      continue;
    } else {
      flushTable(`table-before-text-${segKey}-${i}`);
    }

    // Headings
    if (trimmed.startsWith('### ')) {
      flushList(`list-h3-${segKey}-${i}`);
      elements.push(
        <h4 key={`h3-${segKey}-${i}`} className="text-xs font-bold text-foreground mt-3 mb-1 border-b border-border/50 pb-0.5">
          {renderInlineTokens(trimmed.slice(4))}
        </h4>
      );
      continue;
    }
    if (trimmed.startsWith('## ') || trimmed.startsWith('# ')) {
      flushList(`list-h2-${segKey}-${i}`);
      elements.push(
        <h3 key={`h2-${segKey}-${i}`} className="text-sm font-bold text-foreground mt-3 mb-1.5 border-b border-border pb-0.5">
          {renderInlineTokens(trimmed.replace(/^#+\s*/, ''))}
        </h3>
      );
      continue;
    }

    // Unordered list
    const ulMatch = trimmed.match(/^[-*•]\s+(.+)/);
    if (ulMatch) {
      if (!currentList || currentList.type !== 'ul') {
        flushList(`flush-before-ul-${segKey}-${i}`);
        currentList = { type: 'ul', items: [] };
      }
      currentList.items.push(ulMatch[1]);
      continue;
    }

    // Ordered list
    const olMatch = trimmed.match(/^\d+\.\s+(.+)/);
    if (olMatch) {
      if (!currentList || currentList.type !== 'ol') {
        flushList(`flush-before-ol-${segKey}-${i}`);
        currentList = { type: 'ol', items: [] };
      }
      currentList.items.push(olMatch[1]);
      continue;
    }

    // Standard paragraph
    flushList(`flush-before-p-${segKey}-${i}`);
    elements.push(
      <p key={`p-${segKey}-${i}`} className="my-1.5 text-xs sm:text-[12.5px] leading-relaxed text-foreground/90">
        {renderInlineTokens(trimmed)}
      </p>
    );
  }

  flushList(`final-list-${segKey}`);
  flushTable(`final-table-${segKey}`);

  return <React.Fragment key={segKey}>{elements}</React.Fragment>;
}

export const RichSnippetViewer: React.FC<RichSnippetViewerProps> = ({ text }) => {
  if (!text || !text.trim()) {
    return <span className="text-xs text-muted-foreground italic">No snippet content.</span>;
  }

  // Split text by HTML <table>...</table> blocks
  const parts = text.split(TABLE_REGEX);

  return (
    <div className="space-y-1.5 text-xs sm:text-[12.5px] leading-relaxed select-text">
      {parts.map((part, idx) => {
        if (!part) return null;
        if (/^<table[\s\S]*<\/table>$/i.test(part.trim())) {
          return parseHtmlTable(part.trim(), `table-part-${idx}`);
        }
        return renderMarkdownSegment(part, `md-part-${idx}`);
      })}
    </div>
  );
};
