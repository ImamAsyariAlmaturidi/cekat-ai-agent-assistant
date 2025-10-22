import { useRef } from "react";
import { ChatKit, useChatKit } from "@openai/chatkit-react";
import {
  CHATKIT_API_URL,
  CHATKIT_API_DOMAIN_KEY,
  STARTER_PROMPTS,
  PLACEHOLDER_INPUT,
  GREETING,
} from "../lib/config";
import type { FactAction } from "../hooks/useFacts";
import type { ColorScheme } from "../hooks/useColorScheme";

type ChatKitPanelProps = {
  theme: ColorScheme;
  onWidgetAction: (action: FactAction) => Promise<void>;
  onResponseEnd: () => void;
  onThemeRequest: (scheme: ColorScheme) => void;
};

export function ChatKitPanel({
  theme,
  onWidgetAction,
  onResponseEnd,
  onThemeRequest,
}: ChatKitPanelProps) {
  const processedFacts = useRef(new Set<string>());

  const chatkit = useChatKit({
    api: {
      url: CHATKIT_API_URL,
      domainKey: CHATKIT_API_DOMAIN_KEY,
      uploadStrategy: {
        type: "direct",
        uploadUrl: `${CHATKIT_API_URL}/files`,
      },
    },
    theme: {
      colorScheme: theme,
      color: {
        grayscale: {
          hue: 220,
          tint: 6,
          shade: theme === "dark" ? -1 : -4,
        },
        accent: {
          primary: theme === "dark" ? "#f1f5f9" : "#0f172a",
          level: 1,
        },
      },
      radius: "round",
    },
    startScreen: {
      greeting: GREETING,
      prompts: STARTER_PROMPTS,
    },
    composer: {
      placeholder: PLACEHOLDER_INPUT,
      attachments: {
        enabled: true,
        maxSize: 20 * 1024 * 1024, // 20MB per file
        maxCount: 3,
        accept: { "application/pdf": [".pdf"], "image/*": [".png", ".jpg"] },
      },
    },
    threadItemActions: {
      feedback: false,
    },
    onClientTool: async (invocation) => {
      if (invocation.name === "switch_theme") {
        const requested = invocation.params.theme;
        if (requested === "light" || requested === "dark") {
          if (import.meta.env.DEV) {
            console.debug("[ChatKitPanel] switch_theme", requested);
          }
          onThemeRequest(requested);
          return { success: true };
        }
        return { success: false };
      }

      if (invocation.name === "record_fact") {
        const id = String(invocation.params.fact_id ?? "");
        const text = String(invocation.params.fact_text ?? "");
        if (!id || processedFacts.current.has(id)) {
          return { success: true };
        }
        processedFacts.current.add(id);
        void onWidgetAction({
          type: "save",
          factId: id,
          factText: text.replace(/\s+/g, " ").trim(),
        });
        return { success: true };
      }

      if (invocation.name === "navigate_to_url") {
        const url = String(invocation.params.url ?? "");
        const openInNewTab = Boolean(invocation.params.open_in_new_tab ?? true);
        const description = String(invocation.params.description ?? "");

        if (!url) {
          return { success: false };
        }

        if (import.meta.env.DEV) {
          console.debug("[ChatKitPanel] navigate_to_url", {
            url,
            openInNewTab,
            description,
          });
        }

        try {
          // Always navigate in the same tab/window
          window.location.href = url;
          return { success: true };
        } catch (error) {
          console.error("[ChatKitPanel] Navigation failed", error);
          return { success: false };
        }
      }

      return { success: false };
    },
    onResponseEnd: () => {
      onResponseEnd();
    },
    onThreadChange: () => {
      processedFacts.current.clear();
    },
    onError: ({ error }) => {
      // ChatKit handles displaying the error to the user
      console.error("ChatKit error", error);
    },
    widgets: {
      async onAction(action, item) {
        console.log("[ChatKitPanel] Widget action received:", { action, item });

        try {
          const response = await fetch("/api/widget-action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, itemId: item.id }),
          });

          const result = await response.json();
          console.log("[ChatKitPanel] Widget action response:", result);

          // Handle specific action types
          if (action.type === "navigation.open") {
            const url = action.payload?.url;
            if (url) {
              console.log("[ChatKitPanel] Opening URL:", url);
              window.open(url, "_blank", "noopener,noreferrer");
            }
          }

          return result;
        } catch (error) {
          console.error("[ChatKitPanel] Widget action failed:", error);
          return { success: false, error: error.message };
        }
      },
    },
  });

  return (
    <div className="relative h-full w-full overflow-hidden border border-slate-200/60 bg-white shadow-card dark:border-slate-800/70 dark:bg-slate-900">
      <ChatKit control={chatkit.control} className="block h-full w-full" />
    </div>
  );
}
