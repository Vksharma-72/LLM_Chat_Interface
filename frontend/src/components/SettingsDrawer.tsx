import { useEffect, useState } from "react";
import { api } from "../services/api";
import { useUiStore } from "../stores/uiStore";

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
  onClearConversation: () => void;
  canClear: boolean;
}

export default function SettingsDrawer({
  open,
  onClose,
  onClearConversation,
  canClear,
}: SettingsDrawerProps) {
  const settings = useUiStore((state) => state.settings);
  const updateSettings = useUiStore((state) => state.updateSettings);
  const [models, setModels] = useState<string[] | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || models !== null) {
      return;
    }
    let cancelled = false;
    api
      .get<{ models: string[] }>("/chat/models")
      .then((response) => {
        if (!cancelled) {
          setModels(response.data.models);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setModelsError("Could not load models (is the LLM server up?)");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, models]);

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/40" onClick={onClose} />}
      <aside
        aria-label="Chat settings"
        className={`fixed inset-y-0 right-0 z-40 w-80 overflow-y-auto border-l border-gray-200 bg-white p-6 transition-transform dark:border-gray-800 dark:bg-gray-900 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Settings</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close settings"
            className="rounded p-1 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
          >
            ✕
          </button>
        </div>

        <div className="space-y-6">
          <div>
            <label htmlFor="model" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Model
            </label>
            {modelsError ? (
              <p className="mt-1 text-xs text-red-500">{modelsError}</p>
            ) : models === null ? (
              <p className="mt-1 text-xs text-gray-500">Loading models…</p>
            ) : (
              <select
                id="model"
                value={settings.model}
                onChange={(event) => updateSettings({ model: event.target.value })}
                className="mt-1 w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
              >
                <option value="">(server default)</option>
                {models.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label htmlFor="temperature" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Temperature: {settings.temperature.toFixed(1)}
            </label>
            <input
              id="temperature"
              type="range"
              min={0}
              max={2}
              step={0.1}
              value={settings.temperature}
              onChange={(event) => updateSettings({ temperature: Number(event.target.value) })}
              className="mt-1 w-full"
            />
          </div>

          <div>
            <label htmlFor="max-tokens" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Max tokens
            </label>
            <input
              id="max-tokens"
              type="number"
              min={1}
              value={settings.maxTokens}
              onChange={(event) =>
                updateSettings({ maxTokens: Math.max(1, Number(event.target.value) || 1) })
              }
              className="mt-1 w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            />
          </div>

          <div>
            <label htmlFor="system-prompt" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              System prompt
            </label>
            <textarea
              id="system-prompt"
              rows={4}
              value={settings.systemPrompt}
              onChange={(event) => updateSettings({ systemPrompt: event.target.value })}
              placeholder="Optional instructions for the assistant"
              className="mt-1 w-full resize-y rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            />
          </div>

          <div className="border-t border-gray-200 pt-4 dark:border-gray-800">
            <button
              type="button"
              onClick={onClearConversation}
              disabled={!canClear}
              className="w-full rounded-md border border-red-300 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
            >
              Clear conversation
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
