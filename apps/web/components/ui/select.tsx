"use client"

import * as React from "react"
import { cn } from "cn"
import { Select as SelectPrimitive } from "radix-ui"
import { IconCaretDown, IconCaretUp, IconCheck, type Icon } from "@/lib/icons";

/*
 * The one dropdown of Checky, desk and public site alike: a round button whose caret sits right
 * after its label, and a floating menu (18 px, the one shadow) with 44 px options and a check on
 * the choice. Radix Select underneath: keyboard, typeahead and screen readers as a native select.
 */

function Select({
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Root>) {
  return <SelectPrimitive.Root data-slot="select" {...props} />
}

function SelectGroup({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Group>) {
  return (
    <SelectPrimitive.Group
      data-slot="select-group"
      className={cn("scroll-my-1 p-1", className)}
      {...props}
    />
  )
}

function SelectValue({
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Value>) {
  return <SelectPrimitive.Value data-slot="select-value" {...props} />
}

function SelectTrigger({
  className,
  size = "default",
  icon: Glyph,
  children,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Trigger> & {
  /** `default` 48 px (public pages), `sm` 40 px (the desk's toolbars and forms). */
  size?: "sm" | "default"
  icon?: Icon
}) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      data-size={size}
      className={cn(
        "group inline-flex max-w-full items-center gap-2 rounded-full border border-input bg-card text-left font-medium whitespace-nowrap text-foreground outline-none transition-colors select-none hover:border-foreground hover:bg-card hover:text-foreground focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background data-[state=open]:border-foreground disabled:cursor-not-allowed disabled:border-border disabled:text-muted-foreground disabled:hover:border-border disabled:hover:text-muted-foreground aria-invalid:border-destructive data-placeholder:text-muted-foreground data-[size=default]:h-12 data-[size=default]:pr-4 data-[size=default]:pl-5 data-[size=sm]:h-10 data-[size=sm]:pr-3.5 data-[size=sm]:pl-4 data-[size=sm]:text-sm *:data-[slot=select-value]:min-w-0 *:data-[slot=select-value]:truncate [&_svg]:pointer-events-none [&_svg]:shrink-0",
        className
      )}
      {...props}
    >
      {Glyph && <Glyph className="size-5" aria-hidden />}
      {children}
      <SelectPrimitive.Icon asChild>
        <IconCaretDown className="size-4 transition-transform duration-300 group-data-[state=open]:rotate-180" aria-hidden />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  )
}

function SelectContent({
  className,
  children,
  position = "popper",
  align = "start",
  sideOffset = 8,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        data-slot="select-content"
        className={cn(
          "z-50 max-h-(--radix-select-content-available-height) min-w-(--radix-select-trigger-width) origin-(--radix-select-content-transform-origin) overflow-x-hidden overflow-y-auto rounded-[18px] border border-border bg-popover p-1.5 text-popover-foreground shadow-(--shadow-float) duration-200 ease-(--ease-out) data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-98 data-[state=open]:slide-in-from-top-1.5",
          className
        )}
        position={position}
        align={align}
        sideOffset={sideOffset}
        {...props}
      >
        <SelectScrollUpButton />
        <SelectPrimitive.Viewport data-position={position}>{children}</SelectPrimitive.Viewport>
        <SelectScrollDownButton />
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  )
}

function SelectLabel({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Label>) {
  return (
    <SelectPrimitive.Label
      data-slot="select-label"
      className={cn("px-3 py-1.5 text-xs text-muted-foreground", className)}
      {...props}
    />
  )
}

function SelectItem({
  className,
  children,
  hint,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Item> & {
  /** A second line under the option, left out of the button's label. */
  hint?: React.ReactNode
}) {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cn(
        "relative flex min-h-11 w-full cursor-pointer items-center gap-3 rounded-xl py-2 pr-10 pl-3 text-[0.9375rem] text-foreground outline-none select-none data-[highlighted]:bg-raised data-[highlighted]:text-foreground data-[state=checked]:bg-active data-[state=checked]:font-semibold data-[state=checked]:text-foreground data-disabled:cursor-not-allowed data-disabled:text-muted-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      {...props}
    >
      <span className="min-w-0">
        <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
        {hint && <span className="block text-sm font-normal text-muted-foreground">{hint}</span>}
      </span>
      <SelectPrimitive.ItemIndicator className="absolute right-3 inline-flex">
        <IconCheck className="size-4" aria-hidden />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  )
}

function SelectSeparator({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Separator>) {
  return (
    <SelectPrimitive.Separator
      data-slot="select-separator"
      className={cn("pointer-events-none -mx-1.5 my-1.5 h-px bg-border", className)}
      {...props}
    />
  )
}

function SelectScrollUpButton({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.ScrollUpButton>) {
  return (
    <SelectPrimitive.ScrollUpButton
      data-slot="select-scroll-up-button"
      className={cn(
        "z-10 flex cursor-default items-center justify-center bg-popover py-1 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      {...props}
    >
      <IconCaretUp aria-hidden />
    </SelectPrimitive.ScrollUpButton>
  )
}

function SelectScrollDownButton({
  className,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.ScrollDownButton>) {
  return (
    <SelectPrimitive.ScrollDownButton
      data-slot="select-scroll-down-button"
      className={cn(
        "z-10 flex cursor-default items-center justify-center bg-popover py-1 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      {...props}
    >
      <IconCaretDown aria-hidden />
    </SelectPrimitive.ScrollDownButton>
  )
}

export type Option = { value: string; label: string; hint?: string }

// Radix refuses an empty value on an item: the empty choice travels as « __all ».
const EMPTY = "__all"
const wire = (v: string) => (v === "" ? EMPTY : v)
const unwire = (v: string) => (v === EMPTY ? "" : v)

/**
 * The dropdown from a list of options, controlled (`value`) or inside a form (`name` +
 * `defaultValue`). An empty value is a real choice (« Toutes », « Aucune »); in a form it is
 * sent as an empty string and the choice comes back to `defaultValue` when the form resets.
 */
function ThemedSelect({
  value,
  defaultValue = "",
  onValueChange,
  options,
  label,
  icon,
  className,
  id,
  name,
  disabled,
  size = "default",
}: {
  value?: string
  defaultValue?: string
  onValueChange?: (v: string) => void
  options: Option[]
  /** The accessible name; leave it out when a `<Label htmlFor={id}>` names the button. */
  label?: string
  icon?: Icon
  className?: string
  id?: string
  name?: string
  disabled?: boolean
  size?: "sm" | "default"
}) {
  const [inner, setInner] = React.useState(defaultValue)
  const current = value ?? inner
  const field = React.useRef<HTMLInputElement>(null)

  React.useEffect(() => {
    const form = field.current?.form
    if (!form || value !== undefined) return
    const reset = () => setInner(defaultValue)
    form.addEventListener("reset", reset)
    return () => form.removeEventListener("reset", reset)
  }, [value, defaultValue])

  return (
    <>
      <Select
        value={wire(current)}
        disabled={disabled}
        onValueChange={(v) => {
          setInner(unwire(v))
          onValueChange?.(unwire(v))
        }}
      >
        <SelectTrigger id={id} aria-label={label} size={size} icon={icon} className={className}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={wire(o.value)} value={wire(o.value)} hint={o.hint}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {name && <input ref={field} type="hidden" name={name} value={current} disabled={disabled} />}
    </>
  )
}

export {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectScrollDownButton,
  SelectScrollUpButton,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
  ThemedSelect,
}
