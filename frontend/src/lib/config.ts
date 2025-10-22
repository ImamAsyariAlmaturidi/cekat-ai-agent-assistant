export const CHATKIT_API_URL =
  import.meta.env.VITE_CHATKIT_API_URL ?? "/chatkit";

/**
 * ChatKit still expects a domain key at runtime. Use any placeholder locally,
 * but register your production domain at
 * https://platform.openai.com/settings/organization/security/domain-allowlist
 * and deploy the real key.
 */
export const CHATKIT_API_DOMAIN_KEY =
  import.meta.env.VITE_CHATKIT_API_DOMAIN_KEY ?? "domain_pk_localhost_dev";

export const FACTS_API_URL = import.meta.env.VITE_FACTS_API_URL ?? "/facts";

export const THEME_STORAGE_KEY = "chatkit-boilerplate-theme";

export const GREETING =
  "Welcome to Cekat AI Assistant! Ask me anything about Cekat AI platform.";

export const STARTER_PROMPTS = [
  {
    label: "What is Cekat AI?",
    prompt: "What is Cekat AI and its features?",
    icon: "circle-question",
  },
  {
    label: "Open Dashboard",
    prompt: "Open Cekat dashboard",
    icon: "book-open",
  },
  {
    label: "Setup Chatbot",
    prompt: "How to setup chatbot in Cekat AI?",
    icon: "search",
  },
  {
    label: "Platform Integration",
    prompt: "What platforms can be integrated with Cekat AI?",
    icon: "sparkle",
  },
];

export const PLACEHOLDER_INPUT =
  "Ask about Cekat AI or omnichannel platform...";
