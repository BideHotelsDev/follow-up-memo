import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet"

/**
 * On a phone a list's detail would land below the whole list, out of sight, so it opens over the list instead,
 * almost full height, and closes back to the same place in the list.
 */
export function DetailSheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
}) {
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="bottom"
        className="max-h-[92dvh] gap-0 overflow-y-auto rounded-t-2xl bg-background p-3 pt-10 pb-[calc(env(safe-area-inset-bottom)+0.75rem)]"
      >
        <span aria-hidden className="absolute top-3 left-1/2 h-1 w-10 -translate-x-1/2 rounded-full bg-border" />
        <SheetTitle className="sr-only">{title}</SheetTitle>
        <SheetDescription className="sr-only">Details</SheetDescription>
        {children}
      </SheetContent>
    </Sheet>
  )
}
