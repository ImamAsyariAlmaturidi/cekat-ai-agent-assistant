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
  "Selamat datang di Cekat AI Assistant! Saya siap membantu Anda dengan platform Cekat AI.";

export const STARTER_PROMPTS = [
  {
    label: "Apa itu Cekat AI?",
    prompt: "Apa itu Cekat AI dan fitur-fiturnya?",
    icon: "circle-question",
  },
  {
    label: "Buka Dashboard",
    prompt: "Buka dashboard Cekat",
    icon: "book-open",
  },
  {
    label: "Setup Chatbot",
    prompt: "Bagaimana cara setup chatbot di Cekat AI?",
    icon: "search",
  },
  {
    label: "Integrasi Platform",
    prompt: "Platform apa saja yang bisa diintegrasikan dengan Cekat AI?",
    icon: "sparkle",
  },
];

export const PLACEHOLDER_INPUT =
  "Tanyakan tentang Cekat AI atau platform omnichannel...";
