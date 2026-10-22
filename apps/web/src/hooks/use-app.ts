import { useQuery } from "@tanstack/react-query"

import { api, type AppSettings } from "@/lib/api"

const FALLBACK: AppSettings = {
  owner_name: "the owner",
  owner_email: null,
  people: [],
  properties: [],
  categories: [],
  systems: [],
  pipeline: {
    poll_interval_minutes: 10,
    quiet_minutes: 15,
    gmail_sync_minutes: 30,
    max_attempts: 3,
    raw_text_days: 30,
    internal_domains: [],
    sensitive_topics: [],
    reminders_enabled: false,
    reminder_hour: 8,
    weekly_digest_enabled: true,
    digest_weekday: 0,
    digest_hour: 8,
    skip_rules: 0,
    channels: 0,
  },
  dictation: false,
}

/** The owner's name, the properties, the categories, the systems and how the pipeline runs, as Bide set them in Admin. */
export function useApp(): AppSettings {
  const { data } = useQuery({ queryKey: ["app"], queryFn: api.app, staleTime: 5 * 60_000 })
  return data ?? FALLBACK
}
