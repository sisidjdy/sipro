import * as React from "react"

import { cn } from "@/lib/utils"

const Input = React.forwardRef(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      // `bg-background` (bukan `bg-transparent` bawaan shadcn): field harus SELALU punya
      // latar sendiri. Dengan latar transparan, setiap kotak isian yang berada di atas
      // panel berwarna (bg-secondary, bg-sky-50, bg-amber-50, kartu peringatan, dialog
      // bertingkat) terlihat "tanpa background" — inilah keluhan nyata pemakai bahwa
      // banyak kartu/field terlihat rusak di berbagai halaman.
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-base shadow-sm transition-[border-color,box-shadow] duration-150 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground/80 hover:border-input/70 focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        className
      )}
      ref={ref}
      {...props} />
  );
})
Input.displayName = "Input"

export { Input }
