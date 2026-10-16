import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"

import { SpiralPin, Wordmark } from "@/components/brand"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api, HttpError, links } from "@/lib/api"

const LOGIN_ERRORS: Record<string, string> = {
  not_registered: "That account isn't on the list. Ask Kyle to add you.",
  domain_not_allowed: "Sign in with your Bide Google account.",
  invalid_state: "The sign-in took too long or was opened in another tab. Try again.",
  invalid_token: "Google's answer couldn't be checked. Try again.",
  google_error: "Google didn't complete the sign-in. Try again.",
}

export default function SignInPage() {
  const [params] = useSearchParams()
  const queryClient = useQueryClient()
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers })
  const [email, setEmail] = useState("")
  const [devError, setDevError] = useState<string | null>(null)
  const loginError = params.get("login_error")

  return (
    <div className="flex min-h-dvh items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <SpiralPin className="size-10 text-primary" />
          <Wordmark className="text-4xl" />
          <p className="eyebrow tracking-[0.16em] text-muted-foreground">Meeting follow-up</p>
        </div>
        {loginError ? (
          <Alert variant="destructive">
            <AlertDescription>{LOGIN_ERRORS[loginError] ?? "Sign-in failed. Try again."}</AlertDescription>
          </Alert>
        ) : null}
        {providers.data?.google ? (
          <Button asChild size="lg" className="w-full">
            <a href={links.googleSignIn(params.get("next") ?? "/")}>Sign in with Google</a>
          </Button>
        ) : providers.isSuccess ? (
          <p className="text-center text-sm text-muted-foreground">Google sign-in isn't configured yet.</p>
        ) : null}
        {providers.data?.dev ? (
          <form
            className="space-y-3 rounded-lg border border-dashed p-4"
            onSubmit={async (e) => {
              e.preventDefault()
              setDevError(null)
              try {
                await api.devLogin(email)
                await queryClient.invalidateQueries({ queryKey: ["me"] })
              } catch (err) {
                setDevError(err instanceof HttpError ? err.message : "Sign-in failed")
              }
            }}
          >
            <Label htmlFor="dev-email">Local development: sign in as</Label>
            <Input id="dev-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            {devError ? <p className="text-sm text-destructive">{devError}</p> : null}
            <Button type="submit" variant="outline" className="w-full">
              Sign in
            </Button>
          </form>
        ) : null}
      </div>
    </div>
  )
}
