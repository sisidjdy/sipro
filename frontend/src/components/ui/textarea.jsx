import * as React from "react"

import { cn } from "@/lib/utils"

const Textarea = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <textarea
      // `bg-background`: sama seperti Input — area tulis wajib punya latar sendiri supaya
      // tetap terlihat sebagai tempat mengisi saat berada di atas panel berwarna.
      className={cn(
        "flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-base shadow-sm transition-[border-color,box-shadow] duration-150 placeholder:text-muted-foreground/80 focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        className
      )}
      ref={ref}
      {...props} />
  );
})
Textarea.displayName = "Textarea"

export { Textarea }
