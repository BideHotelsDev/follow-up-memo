import { Lock, Shapes, UserRound } from "lucide-react"

import { FilterPicker, type PickerOption } from "@/components/filter-picker"
import { CategoryDot } from "@/components/tags"
import { useApp } from "@/hooks/use-app"

/** Filter by meeting category: in-use categories first with their colours and descriptions, switched-off ones after. */
export function CategoryFilter({
  value,
  onChange,
  className,
}: {
  value: string | null
  onChange: (value: string | null) => void
  className?: string
}) {
  const { categories } = useApp()
  const options: PickerOption[] = categories.map((c) => ({
    value: c.name,
    label: c.name,
    hint: c.description,
    lead: <CategoryDot slot={c.color} />,
    trail: c.is_sensitive ? (
      <>
        <Lock className="size-3 text-muted-foreground" aria-hidden />
        <span className="sr-only">(sensitive)</span>
      </>
    ) : null,
    group: c.is_active ? "Categories" : "Switched off",
  }))
  options.sort((a, b) => Number(a.group === "Switched off") - Number(b.group === "Switched off"))
  return (
    <FilterPicker
      label="Category"
      icon={Shapes}
      allLabel="Every category"
      search="Search categories"
      value={value}
      onChange={onChange}
      options={options}
      className={className}
    />
  )
}

/** Filter by person: a letter for each, so names scan quickly. */
export function PersonFilter({
  people,
  allLabel,
  value,
  onChange,
  className,
}: {
  people: { id: string; name: string }[]
  allLabel: string
  value: string | null
  onChange: (value: string | null) => void
  className?: string
}) {
  return (
    <FilterPicker
      label="Employee"
      icon={UserRound}
      allLabel={allLabel}
      search="Search people"
      value={value}
      onChange={onChange}
      className={className}
      options={people.map((p) => ({
        value: p.id,
        label: p.name,
        lead: (
          <span
            aria-hidden
            className="font-display grid size-5 place-items-center rounded-full border bg-secondary text-[11px]"
          >
            {p.name.slice(0, 1).toUpperCase()}
          </span>
        ),
      }))}
    />
  )
}
