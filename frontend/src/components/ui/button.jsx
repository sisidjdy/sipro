import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

/**
 * Button — HIERARKI AKSI (Fase 67).
 *
 * Keluhan nyata: "action button atau beberapa hal penting seharusnya bisa di-improve
 * supaya mudah dipahami". Sebelumnya tombol utama, sekunder, dan outline hampir sama
 * beratnya, dan `ghost` tanpa hover terlihat seperti teks biasa. Sekarang:
 *   default     → aksi UTAMA: solid, berbayang, sedikit turun saat ditekan
 *   secondary   → aksi pendukung: permukaan abu dengan garis batas
 *   outline     → aksi netral di atas kartu: punya LATAR sendiri (bukan menembus)
 *   destructive → merah penuh, hanya untuk aksi yang menghapus/membatalkan
 *   ghost/link  → aksi tersier
 * Cincin fokus 2px dipakai semua varian supaya pemakai papan tunjuk tidak kehilangan posisi.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-semibold transition-[background-color,box-shadow,border-color,color,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-45 active:translate-y-[0.5px] [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-sm hover:bg-[hsl(var(--primary-hover))] hover:shadow-md",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-[hsl(var(--destructive-hover))] hover:shadow-md",
        outline:
          "border border-input bg-card text-foreground shadow-sm hover:border-primary/40 hover:bg-accent hover:text-accent-foreground",
        secondary:
          "border border-border bg-secondary text-secondary-foreground shadow-sm hover:bg-[hsl(var(--secondary-hover))]",
        ghost:
          "text-foreground/80 hover:bg-secondary hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-lg px-6 text-[15px]",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const Button = React.forwardRef(({ className, variant, size, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "button"
  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props} />
  );
})
Button.displayName = "Button"

export { Button, buttonVariants }
