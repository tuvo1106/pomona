"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

/** `containerClassName` styles the scroll container, not the table. It matters for a sticky
 * header: this wrapper sets `overflow-x`, which computes `overflow-y` to `auto` as well, so
 * it -- not any outer element -- is the scrollport a sticky `<th>` resolves `top: 0` against.
 * A height cap applied outside it scrolls the whole wrapper past the viewport and the header
 * rides along; applied here, the header actually sticks.
 */
function Table({
  className,
  containerClassName,
  ...props
}: React.ComponentProps<"table"> & { containerClassName?: string }) {
  return (
    <div
      data-slot="table-container"
      className={cn("relative w-full overflow-x-auto", containerClassName)}
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("[&_tr]:border-b", className)}
      {...props}
    />
  )
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  )
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b transition-colors hover:bg-muted/50 has-aria-expanded:bg-muted/50 data-[state=selected]:bg-muted",
        className
      )}
      {...props}
    />
  )
}

/** `numeric` right-aligns the column and gives it tabular figures, so digits line up in a
 * column and a magnitude can be compared down the page rather than read. Set it on the
 * header and the cells together -- a right-aligned column under a left-aligned header is
 * worse than either on its own -- which is why it lives on the primitive instead of being
 * spelled out as classes at each call site.
 */
type NumericColumn = { numeric?: boolean }

const NUMERIC_COLUMN = "text-right tabular-nums"

function TableHead({
  className,
  numeric,
  ...props
}: React.ComponentProps<"th"> & NumericColumn) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-10 px-2 text-left align-middle font-medium whitespace-nowrap text-foreground [&:has([role=checkbox])]:pr-0",
        numeric && NUMERIC_COLUMN,
        className
      )}
      {...props}
    />
  )
}

function TableCell({
  className,
  numeric,
  ...props
}: React.ComponentProps<"td"> & NumericColumn) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "p-2 align-middle whitespace-nowrap [&:has([role=checkbox])]:pr-0",
        numeric && NUMERIC_COLUMN,
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
