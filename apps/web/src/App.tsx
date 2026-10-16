import { Loader2 } from "lucide-react"
import { Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { useMe } from "@/hooks/use-me"
import ConnectionsPage from "@/pages/admin/connections"
import PeoplePage from "@/pages/admin/people"
import SignInPage from "@/pages/sign-in"

export default function App() {
  const me = useMe()

  if (me.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center" aria-busy>
        <Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading" />
      </div>
    )
  }
  if (me.isError) {
    // A server that can't answer is not the same as being signed out: sign-in needs the same server.
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="text-xl">The server is having trouble</h1>
        <p className="max-w-md text-sm text-muted-foreground">It isn't something you did. Try again in a moment.</p>
        <Button onClick={() => me.refetch()}>Try again</Button>
      </div>
    )
  }
  if (!me.data) return <SignInPage />

  const isAdmin = me.data.role === "admin"
  return (
    <Routes>
      <Route element={<AppShell me={me.data} />}>
        {isAdmin ? (
          <>
            <Route path="/admin/connections" element={<ConnectionsPage />} />
            <Route path="/admin/people" element={<PeoplePage />} />
            <Route path="*" element={<Navigate to="/admin/connections" replace />} />
          </>
        ) : (
          // Until the review pages land (Phase 4), only Admin has anything to do here.
          <Route
            path="*"
            element={
              <p className="text-muted-foreground">Your meeting follow-ups will appear here once the app is live.</p>
            }
          />
        )}
      </Route>
    </Routes>
  )
}
