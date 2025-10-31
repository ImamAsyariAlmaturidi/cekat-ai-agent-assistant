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
          if (openInNewTab) {
            console.log(
              "[ChatKitPanel] Attempting to open URL in new tab:",
              url
            );
            const newWindow = window.open(url, "_blank", "noopener,noreferrer");

            if (newWindow) {
              console.log("[ChatKitPanel] Successfully opened new tab");
              // Focus the new window
              newWindow.focus();
            } else {
              console.warn(
                "[ChatKitPanel] Failed to open new tab - popup blocked? Falling back to same-tab navigation"
              );
              // Fallback: redirect in same tab instead of trying to open new tab
              window.location.href = url;
            }
          } else {
            console.log("[ChatKitPanel] Navigating in current tab:", url);
            window.location.href = url;
          }
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
        console.log("[ChatKitPanel] 🔵 Widget action received:", action.type);
        console.log("[ChatKitPanel] 🔵 Action payload:", action.payload);
        console.log("[ChatKitPanel] 🔵 Full action object:", { action, item });

        // Handle navigation.open
        if (action.type === "navigation.open") {
          console.log("[Widget] Handling navigation.open");
          const url = action.payload?.url;
          if (url) {
            console.log("[Widget] Opening URL:", url);
            const newWindow = window.open(url, "_blank", "noopener,noreferrer");

            if (newWindow) {
              console.log("[Widget] Successfully opened new tab");
              newWindow.focus();
            } else {
              console.warn("[Widget] Failed to open new tab - popup blocked?");
              // Try alternative method: create link and click it
              const link = document.createElement("a");
              link.href = url;
              link.target = "_blank";
              link.rel = "noopener noreferrer";
              link.style.display = "none";
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
            }
          }
          return;
        }

        // Handle image.download or image_generation.download
        if (
          action.type === "image.download" ||
          action.type === "image_generation.download"
        ) {
          console.log(`[Widget] Handling ${action.type}`);
          const url = action.payload?.url;
          console.log("[Widget] Download URL:", url);

          if (!url) {
            console.error("[Widget] No URL provided");
            return;
          }

          try {
            console.log("[Widget] Fetching image from:", url);
            const response = await fetch(url);

            if (!response.ok) {
              throw new Error(`Failed to fetch image: ${response.status}`);
            }

            const blob = await response.blob();
            console.log("[Widget] Blob created, size:", blob.size);

            // Create download link
            const blobUrl = window.URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = blobUrl;

            // Extract filename from URL or use default
            const urlObj = new URL(url);
            const pathname = urlObj.pathname;
            const filename = pathname.split("/").pop() || "generated-image.png";
            link.download = filename;

            // Trigger download
            document.body.appendChild(link);
            link.click();

            // Cleanup
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);

            console.log("[Widget] Image downloaded successfully:", filename);
          } catch (error) {
            console.error("[Widget] Failed to download image:", error);
            alert(
              "Failed to download image. Please try right-clicking the image and selecting 'Save Image As'."
            );
          }
          return;
        }

        // For other actions, send to backend
        try {
          console.log("[Widget] Sending action to backend:", action.type);
          const response = await fetch("/api/widget-action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, itemId: item.id }),
          });

          const result = await response.json();
          console.log("[ChatKitPanel] Widget action response:", result);
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
