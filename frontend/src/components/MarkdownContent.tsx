import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div
      data-testid="code-block"
      className="my-2 overflow-hidden rounded-md border border-gray-700"
    >
      <div className="flex items-center justify-between bg-gray-800 px-3 py-1 text-xs text-gray-300">
        <span>{language}</span>
        <button
          type="button"
          onClick={handleCopy}
          aria-label="Copy code"
          className="rounded px-2 py-0.5 hover:bg-gray-700"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{ margin: 0, borderRadius: 0 }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

export default function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        pre: ({ children }) => <>{children}</>,
        code({ className, children }) {
          const text = String(children).replace(/\n$/, "");
          const match = /language-(\w+)/.exec(className ?? "");
          if (!match && !text.includes("\n")) {
            return (
              <code className="rounded bg-gray-100 px-1 py-0.5 text-[0.85em] dark:bg-gray-800">
                {text}
              </code>
            );
          }
          return <CodeBlock language={match?.[1] ?? "text"} code={text} />;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
