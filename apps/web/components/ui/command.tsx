"use client"

import * as React from "react"
import { Command as CommandPrimitive } from "cmdk"
import { cn } from "@/lib/utils"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Kbd } from "@/components/ui/kbd"
import { SearchIcon, CheckIcon, Loader2Icon } from "@/components/icons"

/*
 * Command palette primitives on cmdk, styled for the Notely glass system.
 *
 * cmdk marks the highlighted row with data-selected="true" and every other row with
 * data-selected="false", so styles must target the value (`data-[selected=true]`), never the
 * attribute's presence — otherwise every row lights up at once.
 */

function Command({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive>) {
  return (
    <CommandPrimitive
      data-slot="command"
      className={cn(
        "flex size-full flex-col overflow-hidden bg-transparent text-popover-foreground",
        className
      )}
      {...props}
    />
  )
}

function CommandDialog({
  title = "Command Palette",
  description = "Search for a command to run...",
  children,
  className,
  showCloseButton = false,
  ...props
}: React.ComponentProps<typeof Dialog> & {
  title?: string
  description?: string
  className?: string
  showCloseButton?: boolean
}) {
  return (
    <Dialog {...props}>
      <DialogHeader className="sr-only">
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>
      <DialogContent
        className={cn(
          // Anchored near the top like a spotlight, full-width with gutters on phones.
          "glass-3 top-[12vh] w-[calc(100%-1.5rem)] max-w-xl translate-y-0 overflow-hidden rounded-2xl! p-0 sm:top-[16vh] sm:w-full sm:max-w-xl",
          className
        )}
        showCloseButton={showCloseButton}
      >
        {/* cmdk's Input/List/Item read a store from Command's context; without this wrapper they
            throw "Cannot read properties of undefined (reading 'subscribe')". */}
        <Command>{children}</Command>
      </DialogContent>
    </Dialog>
  )
}

function CommandInput({
  className,
  loading = false,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Input> & { loading?: boolean }) {
  return (
    <div
      data-slot="command-input-wrapper"
      className="flex h-13 items-center gap-3 border-b border-glass-border pl-4 pr-3"
    >
      {loading ? (
        <Loader2Icon className="size-4 shrink-0 animate-spin text-ai" aria-hidden />
      ) : (
        <SearchIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      )}
      <CommandPrimitive.Input
        data-slot="command-input"
        className={cn(
          "h-full min-w-0 flex-1 bg-transparent text-base outline-hidden placeholder:text-placeholder disabled:cursor-not-allowed disabled:opacity-(--disabled-opacity)",
          className
        )}
        {...props}
      />
      <Kbd className="hidden sm:inline-flex">Esc</Kbd>
    </div>
  )
}

function CommandList({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.List>) {
  return (
    <CommandPrimitive.List
      data-slot="command-list"
      className={cn(
        "scrollbar-thin max-h-[min(60vh,26rem)] scroll-py-1.5 overflow-x-hidden overflow-y-auto px-1.5 py-1.5 outline-none",
        className
      )}
      {...props}
    />
  )
}

function CommandEmpty({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Empty>) {
  return (
    <CommandPrimitive.Empty
      data-slot="command-empty"
      className={cn("px-3 py-10 text-center text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

function CommandGroup({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Group>) {
  return (
    <CommandPrimitive.Group
      data-slot="command-group"
      className={cn(
        "overflow-hidden text-foreground **:[[cmdk-group-heading]]:px-2.5 **:[[cmdk-group-heading]]:pt-2 **:[[cmdk-group-heading]]:pb-1 **:[[cmdk-group-heading]]:text-[11px] **:[[cmdk-group-heading]]:font-medium **:[[cmdk-group-heading]]:uppercase **:[[cmdk-group-heading]]:tracking-[0.1em] **:[[cmdk-group-heading]]:text-tertiary",
        className
      )}
      {...props}
    />
  )
}

function CommandSeparator({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Separator>) {
  return (
    <CommandPrimitive.Separator
      data-slot="command-separator"
      className={cn("mx-2.5 my-1 h-px bg-glass-border", className)}
      {...props}
    />
  )
}

function CommandItem({
  className,
  children,
  checkable = false,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Item> & { checkable?: boolean }) {
  return (
    <CommandPrimitive.Item
      data-slot="command-item"
      className={cn(
        // icon | text | metadata: the same three columns in every row, so labels and the
        // secondary column line up across sections instead of floating on auto margins.
        "group/command-item relative grid min-h-10 cursor-pointer grid-cols-[1rem_minmax(0,1fr)_auto] items-center gap-x-3 rounded-lg py-2 pl-2.5 pr-3 text-sm outline-hidden select-none transition-colors duration-200 ease-liquid",
        "data-[disabled=true]:cursor-not-allowed data-[disabled=true]:opacity-50",
        // Highlight: soft accent fill, a thin emerald bar on the left, icon tinted.
        "data-[selected=true]:bg-ai-soft data-[selected=true]:text-foreground data-[selected=true]:before:absolute data-[selected=true]:before:left-0 data-[selected=true]:before:top-1/2 data-[selected=true]:before:h-5 data-[selected=true]:before:w-0.5 data-[selected=true]:before:-translate-y-1/2 data-[selected=true]:before:rounded-full data-[selected=true]:before:bg-ai",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 [&>svg:first-child]:text-muted-foreground data-[selected=true]:[&>svg:first-child]:text-ai",
        className
      )}
      {...props}
    >
      {children}
      {checkable ? <CheckIcon className="col-start-3 opacity-0 group-data-[checked=true]/command-item:opacity-100" /> : null}
    </CommandPrimitive.Item>
  )
}

function CommandShortcut({
  className,
  ...props
}: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="command-shortcut"
      className={cn(
        "col-start-3 text-xs tracking-widest text-muted-foreground group-data-[selected=true]/command-item:text-foreground",
        className
      )}
      {...props}
    />
  )
}

/** Primary text (and optional secondary line) of an item; occupies the middle column. */
function CommandItemText({
  className,
  title,
  description,
  ...props
}: Omit<React.ComponentProps<"span">, "title"> & { title: React.ReactNode; description?: React.ReactNode }) {
  return (
    <span data-slot="command-item-text" className={cn("col-start-2 min-w-0", className)} {...props}>
      <span className="block truncate leading-5">{title}</span>
      {description ? (
        <span className="block truncate text-xs leading-4 text-muted-foreground">{description}</span>
      ) : null}
    </span>
  )
}

/** Quiet right-hand metadata (kind, shortcut hint). Hidden on phones where width is scarce. */
function CommandItemMeta({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="command-item-meta"
      className={cn(
        "col-start-3 hidden justify-self-end text-[11px] text-tertiary group-data-[selected=true]/command-item:text-muted-foreground sm:inline",
        className
      )}
      {...props}
    />
  )
}

/** Keyboard legend under the list. */
function CommandFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="command-footer"
      className={cn(
        "flex items-center gap-3 border-t border-glass-border px-3 py-1.5 text-[11px] text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

export {
  Command,
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandItemText,
  CommandItemMeta,
  CommandShortcut,
  CommandSeparator,
  CommandFooter,
}
