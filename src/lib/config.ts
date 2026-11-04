export interface StandaloneConfig {
  deploymentUrl: string;
  assistantId: string;
  langsmithApiKey?: string;
}

const CONFIG_KEY = "deep-agent-config";

export const DEFAULT_CONFIG: StandaloneConfig = {
  deploymentUrl:
    process.env.NEXT_PUBLIC_DEPLOYMENT_URL || "http://100.108.226.67:2024",
  assistantId: process.env.NEXT_PUBLIC_ASSISTANT_ID || "social_agent",
  langsmithApiKey: process.env.NEXT_PUBLIC_LANGSMITH_API_KEY || "",
};

export function getConfig(): StandaloneConfig | null {
  // Server render uses the same defaults so first paint IS the app,
  // never a setup screen (Julie/Justin just open the link and chat).
  if (typeof window === "undefined") return DEFAULT_CONFIG;

  const stored = localStorage.getItem(CONFIG_KEY);
  if (!stored) return DEFAULT_CONFIG;

  try {
    const parsed = JSON.parse(stored) as StandaloneConfig;
    if (!parsed.deploymentUrl || !parsed.assistantId) return DEFAULT_CONFIG;
    return parsed;
  } catch {
    return DEFAULT_CONFIG;
  }
}

export function saveConfig(config: StandaloneConfig): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}
